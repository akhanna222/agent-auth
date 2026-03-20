"""Verification route — supports both real JWT tokens and sandbox test tokens."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from ..config import settings
from ..dependencies import get_platform_keys
from ..redis_client import cache
from ..sandbox import (
    SANDBOX_AGENTS,
    SANDBOX_TOKENS,
    get_sandbox_agent,
    is_sandbox_token,
    resolve_sandbox_delegation_for_agent,
    wrap_response,
)
from ..schemas.api.verify import VerifyRequest, VerifyResponse
from ..services.audit import audit_service
from ..services.policy import evaluate_policy
from ..services.risk import DEFAULT_THRESHOLDS
from ..services.verification import verification_service
from ..utils.crypto import hash_payload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["verify"])


@router.post("/v1/verify-agent-action")
async def verify_agent_action(request: Request, body: VerifyRequest):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    tenant_id = request.state.tenant_id

    # Check if this is a sandbox token
    if is_sandbox_token(body.signed_token):
        result = await _sandbox_verify(tenant_id, body)
        return wrap_response(result, request_id, start_time)

    # Real JWT verification flow
    public_key, _ = get_platform_keys()
    verify_result = await verification_service.verify(tenant_id, body, public_key)
    result = verify_result.model_dump()
    result["processed_at"] = result["processed_at"].isoformat() if isinstance(result["processed_at"], datetime) else result["processed_at"]

    # Add constraints_verified for allow decisions
    if result["decision"] == "allow":
        result["constraints_verified"] = {
            "amount_within_limit": True,
            "delegation_active": True,
            "token_valid": True,
            "time_window_valid": True,
        }

    return wrap_response(result, request_id, start_time)


async def _sandbox_verify(tenant_id: str, body: VerifyRequest) -> dict:
    """Handle sandbox test token verification using pre-seeded data."""
    now = datetime.now(timezone.utc)
    decision_id = f"dec_sandbox_{uuid.uuid4().hex[:6]}"
    agent_id = str(body.agent_id)

    # Fetch sandbox data
    agent = get_sandbox_agent(agent_id)
    token_data = SANDBOX_TOKENS.get(body.signed_token)
    delegation = resolve_sandbox_delegation_for_agent(agent_id) if agent else None

    # Check revocations in parallel
    async def _false():
        return False

    agent_revoked, deleg_revoked, token_revoked = await asyncio.gather(
        cache.exists(f"kya:revoked:agent:{agent_id}"),
        cache.exists(f"kya:revoked:delegation:{delegation['delegation_id']}") if delegation else _false(),
        cache.exists(f"kya:revoked:token:{body.signed_token}"),
    )

    revocations = {
        "agent_revoked": agent_revoked,
        "delegation_revoked": deleg_revoked,
        "token_revoked": token_revoked,
    }

    # Compute payload hash (for sandbox, the token "knows" the action hash)
    payload_hash = hash_payload(body.action_payload)

    # Build policy input
    opa_input = {
        "agent": {
            "agent_id": agent["agent_id"],
            "status": agent["status"],
            "environment": agent["environment"],
            "trust_tier": agent["trust_tier"],
        } if agent else None,
        "delegation": {
            "delegation_id": delegation["delegation_id"],
            "status": delegation["status"],
            "granted_scopes": delegation["granted_scopes"],
            "expires_at": delegation["expires_at"],
        } if delegation else None,
        "token": {
            "token_id": body.signed_token,
            "jti": body.signed_token,
            "status": token_data["status"] if token_data else "unknown",
            "action": token_data["action"] if token_data else body.action,
            "action_hash": payload_hash,  # sandbox tokens auto-match
            "expires_at": token_data["expires_at"] if token_data else now.isoformat(),
            "use_count": token_data["use_count"] if token_data else 0,
            "max_uses": token_data["max_uses"] if token_data else 1,
        } if token_data else None,
        "action": body.action,
        "payload": body.action_payload,
        "payload_hash": payload_hash,
        "revocations": revocations,
        "context": {
            "ip_address": body.request_context.ip_address,
            "environment": agent["environment"] if agent else "sandbox",
            "day_of_week": now.strftime("%a").lower(),
            "hour_utc": now.hour,
        },
        "current_time": now.isoformat() + "Z",
    }

    result = evaluate_policy(opa_input)

    # Risk score — sandbox agents get low scores since they are "established"
    risk_score = 0.0
    if agent:
        tier_scores = {"certified": 0, "verified": 5, "unverified": 10}
        risk_score = tier_scores.get(agent["trust_tier"], 10)
        # Add payload deviation for large amounts
        amount = body.action_payload.get("amount_usd")
        if amount and float(amount) > 5000:
            risk_score += 12

    # Risk override
    outcome = "deny"
    if result["allow"]:
        outcome = "allow"
    elif result["step_up"]:
        outcome = "step_up"

    if outcome == "allow" and risk_score > DEFAULT_THRESHOLDS["auto_deny"]:
        outcome = "deny"
        result["deny_reason"] = "RISK_SCORE_TOO_HIGH"
    elif outcome == "allow" and risk_score > DEFAULT_THRESHOLDS["auto_allow"]:
        outcome = "step_up"

    # Build response
    resp: dict = {
        "is_agent_valid": agent is not None and agent["status"] == "active",
        "is_authorized": outcome == "allow",
        "risk_score": risk_score,
        "decision": outcome,
        "decision_id": decision_id,
        "processed_at": now.isoformat() + "Z",
    }

    if outcome == "allow":
        resp["constraints_verified"] = {
            "amount_within_limit": True,
            "delegation_active": True,
            "token_valid": True,
            "time_window_valid": True,
        }
        # Mark sandbox token as used
        if token_data:
            token_data["status"] = "used"
            token_data["use_count"] = 1

    elif outcome == "step_up":
        challenge_id = f"chal_sandbox_{uuid.uuid4().hex[:8]}"
        resp["challenge_id"] = challenge_id
        resp["challenge_type"] = "push_notification"
        resp["poll_url"] = f"/v1/stepup/{challenge_id}/status"
        resp["expires_at"] = (now + timedelta(seconds=300)).isoformat() + "Z"
        # Create a real challenge in the DB for polling
        from ..services.stepup import stepup_service
        try:
            await stepup_service.create_challenge(
                tenant_id="mastercard-sandbox",
                agent_id=agent_id,
                token_id=body.signed_token,
                principal_id="principal_mc_sandbox_001",
                action_payload=body.action_payload,
            )
        except Exception:
            logger.warning("Failed to create step-up challenge for sandbox token %s", body.signed_token, exc_info=True)

    elif outcome == "deny":
        resp["denial_reason"] = result.get("deny_reason")

    # Audit
    try:
        await audit_service.log(
            tenant_id=tenant_id,
            event_type=f"action.{outcome}",
            agent_id=agent_id,
            action=body.action,
            decision=outcome,
            risk_score=risk_score,
            denial_reason=result.get("deny_reason"),
            request_payload=body.action_payload,
        )
    except Exception:
        logger.warning("Failed to write audit log for sandbox verification", exc_info=True)

    return resp

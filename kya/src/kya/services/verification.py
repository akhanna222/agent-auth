"""Verification service — orchestrates policy evaluation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..config import settings
from ..models.db.agent import Agent
from ..models.db.delegation import Delegation
from ..models.db.intent_token import IntentToken
from ..redis_client import cache
from ..schemas.api.verify import VerifyRequest, VerifyResponse
from ..services.audit import audit_service
from ..services.intent import intent_service
from ..services.policy import evaluate_policy
from ..services.risk import DEFAULT_THRESHOLDS, risk_engine
from ..utils.crypto import hash_payload, verify_jwt


class VerificationService:
    async def verify(self, tenant_id: str, request: VerifyRequest, platform_public_key: str) -> VerifyResponse:
        decision_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        agent_id = str(request.agent_id)

        # Step 1: Decode token to get delegation_id and jti
        try:
            claims = verify_jwt(request.signed_token, platform_public_key)
        except Exception:
            return VerifyResponse(
                is_agent_valid=False,
                is_authorized=False,
                risk_score=100.0,
                decision="deny",
                decision_id=decision_id,
                denial_reason="TOKEN_INVALID_SIGNATURE",
                processed_at=now,
            )

        delegation_id = claims.get("delegation_id")
        jti = claims.get("jti")

        # Step 2: Fetch data
        from ..services.identity import identity_service
        from ..services.delegation import delegation_service

        agent = await identity_service.get_agent(agent_id)
        delegation = await delegation_service.get_delegation(delegation_id) if delegation_id else None
        token = await intent_service.get_token_by_jti(jti) if jti else None

        # Step 3: Check revocations
        revocations = {
            "agent_revoked": await cache.exists(f"kya:revoked:agent:{agent_id}"),
            "delegation_revoked": await cache.exists(f"kya:revoked:delegation:{delegation_id}") if delegation_id else False,
            "token_revoked": await cache.exists(f"kya:revoked:token:{jti}") if jti else False,
        }

        # Step 4: Compute payload hash
        payload_hash = hash_payload(request.action_payload)

        # Step 5: Build policy input
        def serialize_dt(dt: datetime | None) -> str:
            if dt is None:
                return ""
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        opa_input = {
            "agent": {
                "agent_id": agent.agent_id,
                "status": agent.status,
                "environment": agent.environment,
                "trust_tier": agent.trust_tier,
            } if agent else None,
            "delegation": {
                "delegation_id": delegation.delegation_id,
                "status": delegation.status,
                "granted_scopes": delegation.granted_scopes,
                "expires_at": serialize_dt(delegation.expires_at),
            } if delegation else None,
            "token": {
                "token_id": token.token_id,
                "jti": token.jti,
                "status": token.status,
                "action": token.action,
                "action_hash": hash_payload(token.action_payload),
                "expires_at": serialize_dt(token.expires_at),
                "use_count": token.use_count,
                "max_uses": token.max_uses,
            } if token else None,
            "action": request.action,
            "payload": request.action_payload,
            "payload_hash": payload_hash,
            "revocations": revocations,
            "context": {
                "ip_address": request.request_context.ip_address,
                "environment": agent.environment if agent else settings.ENVIRONMENT,
                "day_of_week": now.strftime("%a").lower(),
                "hour_utc": now.hour,
            },
            "current_time": now.isoformat() + "Z",
        }

        # Step 6: Evaluate policy
        result = evaluate_policy(opa_input)

        # Step 7: Risk score
        risk_score = 0.0
        if agent:
            risk_score = await risk_engine.score(agent, request.action, request.action_payload)

        # Step 8: Risk override
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

        # Step 9: Consume token on allow
        if outcome == "allow" and token:
            await intent_service.consume_token(token.token_id)

        # Step 10: Audit
        await audit_service.log(
            tenant_id=tenant_id,
            event_type=f"action.{outcome}",
            agent_id=agent_id,
            action=request.action,
            decision=outcome,
            risk_score=risk_score,
            denial_reason=result.get("deny_reason"),
            request_payload=request.action_payload,
        )

        return VerifyResponse(
            is_agent_valid=agent is not None and agent.status == "active",
            is_authorized=outcome == "allow",
            risk_score=risk_score,
            decision=outcome,
            decision_id=decision_id,
            denial_reason=result.get("deny_reason"),
            processed_at=now,
        )


verification_service = VerificationService()

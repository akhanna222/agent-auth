"""Step-up challenge routes — supports sandbox challenges."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from ..sandbox import wrap_response
from ..schemas.api.stepup import StepUpRespondRequest, StepUpRespondResponse, StepUpStatusResponse
from ..services.stepup import stepup_service

router = APIRouter(prefix="/v1/stepup", tags=["step-up"])


@router.get("/{challenge_id}/status")
async def get_stepup_status(request: Request, challenge_id: str):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)

    challenge = await stepup_service.get_challenge(challenge_id)
    if not challenge:
        # Return a sandbox-friendly pending response for unknown challenges
        data = {
            "status": "pending",
            "challenge_id": challenge_id,
            "upgraded_token": None,
            "decision_at": None,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(),
        }
        return wrap_response(data, request_id, start_time)

    data = {
        "status": challenge.status,
        "challenge_id": challenge.challenge_id,
        "upgraded_token": None,
        "decision_at": challenge.resolved_at.isoformat() if challenge.resolved_at else None,
        "expires_at": challenge.expires_at.isoformat(),
    }
    return wrap_response(data, request_id, start_time)


@router.post("/{challenge_id}/respond")
async def respond_to_stepup(request: Request, challenge_id: str, body: StepUpRespondRequest):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id

    try:
        challenge = await stepup_service.respond(challenge_id, body.decision, tenant_id)
        data = {
            "status": challenge.status,
            "challenge_id": challenge.challenge_id,
        }
        if body.decision == "approve":
            # Issue an upgraded token (signed JWT for real flow)
            from ..dependencies import get_platform_keys
            from ..utils.crypto import sign_jwt
            _, private_key = get_platform_keys()
            upgraded_payload = {
                "sub": challenge.principal_id,
                "jti": str(uuid.uuid4()),
                "agent_id": challenge.agent_id,
                "type": "upgraded_step_up",
                "original_challenge": challenge_id,
            }
            upgraded_token = sign_jwt(upgraded_payload, private_key, expiry_seconds=300)
            data["upgraded_token"] = upgraded_token
        else:
            data["upgraded_token"] = None

        return wrap_response(data, request_id, start_time)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

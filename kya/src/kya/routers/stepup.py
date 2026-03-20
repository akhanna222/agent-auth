"""Step-up challenge routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas.api.stepup import StepUpRespondRequest, StepUpRespondResponse, StepUpStatusResponse
from ..services.stepup import stepup_service

router = APIRouter(prefix="/v1/stepup", tags=["step-up"])


@router.get("/{challenge_id}/status", response_model=StepUpStatusResponse)
async def get_stepup_status(challenge_id: str):
    challenge = await stepup_service.get_challenge(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return StepUpStatusResponse(
        status=challenge.status,
        challenge_id=challenge.challenge_id,
        upgraded_token=None,
        decision_at=challenge.resolved_at,
        expires_at=challenge.expires_at,
    )


@router.post("/{challenge_id}/respond", response_model=StepUpRespondResponse)
async def respond_to_stepup(request: Request, challenge_id: str, body: StepUpRespondRequest):
    tenant_id = request.state.tenant_id
    try:
        challenge = await stepup_service.respond(challenge_id, body.decision, tenant_id)
        return StepUpRespondResponse(
            status=challenge.status,
            challenge_id=challenge.challenge_id,
            upgraded_token=None,  # Would be populated with actual upgraded token
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

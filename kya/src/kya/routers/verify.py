"""Verification route."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..dependencies import get_platform_keys
from ..schemas.api.verify import VerifyRequest, VerifyResponse
from ..services.verification import verification_service

router = APIRouter(tags=["verify"])


@router.post("/v1/verify-agent-action", response_model=VerifyResponse)
async def verify_agent_action(request: Request, body: VerifyRequest):
    tenant_id = request.state.tenant_id
    public_key, _ = get_platform_keys()
    return await verification_service.verify(tenant_id, body, public_key)

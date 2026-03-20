"""Revocation routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas.api.revoke import RevokeRequest, RevokeResponse
from ..services.revocation import revocation_service

router = APIRouter(prefix="/v1/revoke", tags=["revocation"])


@router.post("/agent/{agent_id}", response_model=RevokeResponse)
async def revoke_agent(request: Request, agent_id: str, body: RevokeRequest):
    tenant_id = request.state.tenant_id
    try:
        result = await revocation_service.revoke_agent(tenant_id, agent_id, body.reason, body.notes)
        return RevokeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/delegation/{delegation_id}", response_model=RevokeResponse)
async def revoke_delegation(request: Request, delegation_id: str, body: RevokeRequest):
    tenant_id = request.state.tenant_id
    try:
        result = await revocation_service.revoke_delegation(tenant_id, delegation_id, body.reason, body.notes)
        return RevokeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/token/{token_id}", response_model=RevokeResponse)
async def revoke_token(request: Request, token_id: str, body: RevokeRequest):
    tenant_id = request.state.tenant_id
    try:
        result = await revocation_service.revoke_token(tenant_id, token_id, body.reason, body.notes)
        return RevokeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

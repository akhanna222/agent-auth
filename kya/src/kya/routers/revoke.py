"""Revocation routes — supports both real and sandbox entities."""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from ..redis_client import cache
from ..sandbox import SANDBOX_AGENTS, wrap_response
from ..schemas.api.revoke import RevokeRequest, RevokeResponse
from ..services.audit import audit_service
from ..services.revocation import revocation_service

router = APIRouter(prefix="/v1/revoke", tags=["revocation"])


@router.post("/agent/{agent_id}")
async def revoke_agent(request: Request, agent_id: str, body: RevokeRequest):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id

    # Handle sandbox agents
    if agent_id in SANDBOX_AGENTS:
        await cache.set(f"kya:revoked:agent:{agent_id}", body.reason)
        SANDBOX_AGENTS[agent_id]["status"] = "revoked"
        propagation_ms = round((time.time() - start_time) * 1000, 2)

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="agent.revoked",
            agent_id=agent_id,
            metadata={"reason": body.reason},
        )

        data = {
            "revoked": True,
            "propagation_ms": propagation_ms,
            "cascaded_to": [],
            "revoked_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        }
        return wrap_response(data, request_id, start_time)

    try:
        result = await revocation_service.revoke_agent(tenant_id, agent_id, body.reason, body.notes)
        result["revoked_at"] = result["revoked_at"].isoformat()
        return wrap_response(result, request_id, start_time)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/delegation/{delegation_id}")
async def revoke_delegation(request: Request, delegation_id: str, body: RevokeRequest):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id
    try:
        result = await revocation_service.revoke_delegation(tenant_id, delegation_id, body.reason, body.notes)
        result["revoked_at"] = result["revoked_at"].isoformat()
        return wrap_response(result, request_id, start_time)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/token/{token_id}")
async def revoke_token(request: Request, token_id: str, body: RevokeRequest):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id
    try:
        result = await revocation_service.revoke_token(tenant_id, token_id, body.reason, body.notes)
        result["revoked_at"] = result["revoked_at"].isoformat()
        return wrap_response(result, request_id, start_time)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

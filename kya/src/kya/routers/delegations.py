"""Delegation routes."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import get_platform_keys
from ..sandbox import get_sandbox_delegation, wrap_response
from ..schemas.api.delegations import (
    AgentDelegationRequest,
    AgentDelegationResponse,
    DelegationCreateRequest,
    DelegationCreateResponse,
    GrantedScopes,
    PreAuthRequest,
    PreAuthResponse,
)
from ..services.delegation import delegation_service

router = APIRouter(prefix="/v1/delegations", tags=["delegations"])


@router.post("", response_model=DelegationCreateResponse, status_code=201)
async def create_delegation(request: Request, body: DelegationCreateRequest):
    tenant_id = request.state.tenant_id
    principal_id = request.headers.get("X-Principal-ID", "default-principal")
    try:
        deleg = await delegation_service.create_delegation(tenant_id, principal_id, body)
        return DelegationCreateResponse(
            delegation_id=deleg.delegation_id,
            agent_id=deleg.agent_id,
            delegation_type=deleg.delegation_type,
            granted_scopes=GrantedScopes(**deleg.granted_scopes),
            status=deleg.status,
            issued_at=deleg.issued_at,
            expires_at=deleg.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agent-to-agent", response_model=AgentDelegationResponse, status_code=201)
async def create_agent_delegation(request: Request, body: AgentDelegationRequest):
    tenant_id = request.state.tenant_id
    try:
        ad = await delegation_service.create_agent_delegation(tenant_id, body)
        return AgentDelegationResponse(
            agent_delegation_id=ad.agent_delegation_id,
            parent_agent_id=ad.parent_agent_id,
            child_agent_id=ad.child_agent_id,
            depth=ad.depth,
            inherited_scopes=GrantedScopes(**ad.inherited_scopes),
            status=ad.status,
            issued_at=ad.issued_at,
            expires_at=ad.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pre-auth", response_model=PreAuthResponse, status_code=201)
async def create_pre_auth(request: Request, body: PreAuthRequest):
    tenant_id = request.state.tenant_id
    principal_id = request.headers.get("X-Principal-ID", "default-principal")
    _, private_key = get_platform_keys()
    try:
        deleg, mandate_token = await delegation_service.create_pre_auth(
            tenant_id, principal_id, body, private_key
        )
        return PreAuthResponse(
            delegation_id=deleg.delegation_id,
            mandate_token=mandate_token,
            expires_at=deleg.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_delegations(request: Request):
    tenant_id = request.state.tenant_id
    delegations = await delegation_service.list_delegations(tenant_id)
    result = [
        {
            "delegation_id": d.delegation_id,
            "agent_id": d.agent_id,
            "delegation_type": d.delegation_type,
            "status": d.status,
            "granted_scopes": d.granted_scopes,
            "issued_at": d.issued_at.isoformat(),
            "expires_at": d.expires_at.isoformat(),
        }
        for d in delegations
    ]

    # Include sandbox delegations for mastercard-sandbox tenant
    if tenant_id == "mastercard-sandbox":
        from ..sandbox import SANDBOX_DELEGATIONS
        existing_ids = {d["delegation_id"] for d in result}
        for deleg_id, deleg_data in SANDBOX_DELEGATIONS.items():
            if deleg_id not in existing_ids:
                result.append(deleg_data)

    return result


@router.get("/{delegation_id}")
async def get_delegation_detail(request: Request, delegation_id: str):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)

    # Check sandbox delegations first
    sandbox_deleg = get_sandbox_delegation(delegation_id)
    if sandbox_deleg:
        return wrap_response(sandbox_deleg, request_id, start_time)

    deleg = await delegation_service.get_delegation(delegation_id)
    if not deleg:
        raise HTTPException(status_code=404, detail="Delegation not found")

    data = {
        "delegation_id": deleg.delegation_id,
        "agent_id": deleg.agent_id,
        "delegation_type": deleg.delegation_type,
        "status": deleg.status,
        "granted_scopes": deleg.granted_scopes,
        "issued_at": deleg.issued_at.isoformat(),
        "expires_at": deleg.expires_at.isoformat(),
    }
    return wrap_response(data, request_id, start_time)

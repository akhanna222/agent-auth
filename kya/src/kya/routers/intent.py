"""Intent token routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..dependencies import get_platform_keys
from ..schemas.api.intent import (
    IntentFromPreAuthRequest,
    IntentFromPreAuthResponse,
    IntentIssueRequest,
    IntentIssueResponse,
)
from ..services.intent import intent_service

router = APIRouter(prefix="/v1/intent", tags=["intent"])


@router.post("/issue", response_model=IntentIssueResponse, status_code=201)
async def issue_token(request: Request, body: IntentIssueRequest):
    tenant_id = request.state.tenant_id
    principal_id = request.headers.get("X-Principal-ID", "default-principal")
    _, private_key = get_platform_keys()
    try:
        token = await intent_service.issue_token(tenant_id, principal_id, body, private_key)
        return IntentIssueResponse(
            token_id=token.token_id,
            signed_token=token.signed_token,
            action=token.action,
            expires_at=token.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/issue-from-pre-auth", response_model=IntentFromPreAuthResponse, status_code=201)
async def issue_from_pre_auth(request: Request, body: IntentFromPreAuthRequest):
    tenant_id = request.state.tenant_id
    agent_id = request.headers.get("X-Agent-ID", "")
    public_key, private_key = get_platform_keys()
    try:
        token = await intent_service.issue_from_pre_auth(
            tenant_id=tenant_id,
            agent_id=agent_id,
            mandate_token=body.mandate_token,
            action=body.action,
            action_payload=body.action_payload,
            expires_in_seconds=body.expires_in_seconds,
            platform_private_key=private_key,
            platform_public_key=public_key,
        )
        return IntentFromPreAuthResponse(
            token_id=token.token_id,
            signed_token=token.signed_token,
            action=token.action,
            token_mode=token.token_mode,
            expires_at=token.expires_at,
        )
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_tokens(request: Request):
    tenant_id = request.state.tenant_id
    tokens = await intent_service.list_tokens(tenant_id)
    return [
        {
            "token_id": t.token_id,
            "agent_id": t.agent_id,
            "action": t.action,
            "status": t.status,
            "token_mode": t.token_mode,
            "issued_at": t.issued_at.isoformat(),
            "expires_at": t.expires_at.isoformat(),
        }
        for t in tokens
    ]

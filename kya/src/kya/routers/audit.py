"""Audit log routes — includes timeline and chain verification."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..sandbox import wrap_response
from ..schemas.api.audit import AuditEntry, ChainVerificationResponse
from ..services.audit import audit_service

router = APIRouter(prefix="/v1/audit", tags=["audit"])


def _entry_to_dict(e) -> dict:
    return {
        "log_id": e.log_id,
        "tenant_id": e.tenant_id,
        "sequence_num": e.sequence_num,
        "event_type": e.event_type,
        "agent_id": e.agent_id,
        "principal_id": e.principal_id,
        "action": e.action,
        "decision": e.decision,
        "risk_score": float(e.risk_score) if e.risk_score else None,
        "denial_reason": e.denial_reason,
        "entry_hash": e.entry_hash,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/events")
async def get_events(
    request: Request,
    agent_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id
    entries = await audit_service.get_events(tenant_id, agent_id=agent_id, event_type=event_type, limit=limit)
    # Return flat list for UI compatibility
    return [_entry_to_dict(e) for e in entries]


@router.get("/agent/{agent_id}/timeline")
async def get_agent_timeline(
    request: Request,
    agent_id: str,
    limit: int = 20,
):
    """Agent-specific audit timeline — referenced by MPGS Postman collection."""
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id
    entries = await audit_service.get_events(tenant_id, agent_id=agent_id, limit=limit)
    data = {
        "agent_id": agent_id,
        "events": [_entry_to_dict(e) for e in entries],
        "total": len(entries),
    }
    return wrap_response(data, request_id, start_time)


@router.get("/verify-chain")
async def verify_chain(
    request: Request,
    from_seq: int | None = None,
    to_seq: int | None = None,
):
    start_time = time.time()
    request_id = getattr(request.state, "request_id", None)
    tenant_id = request.state.tenant_id
    result = await audit_service.verify_chain(tenant_id, from_seq, to_seq)
    result["verification_timestamp"] = datetime.now(timezone.utc).isoformat()
    return wrap_response(result, request_id, start_time)


@router.get("/decisions")
async def get_decisions(
    request: Request,
    decision: str | None = None,
    limit: int = 100,
):
    """Query audit log by decision type."""
    tenant_id = request.state.tenant_id
    event_type = f"action.{decision}" if decision else None
    entries = await audit_service.get_events(tenant_id, event_type=event_type, limit=limit)
    return [_entry_to_dict(e) for e in entries]

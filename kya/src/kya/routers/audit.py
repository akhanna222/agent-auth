"""Audit log routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..schemas.api.audit import AuditEntry, ChainVerificationResponse, HealthResponse
from ..services.audit import audit_service

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEntry])
async def get_events(
    request: Request,
    agent_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
):
    tenant_id = request.state.tenant_id
    entries = await audit_service.get_events(tenant_id, agent_id=agent_id, event_type=event_type, limit=limit)
    return [
        AuditEntry(
            log_id=e.log_id,
            tenant_id=e.tenant_id,
            sequence_num=e.sequence_num,
            event_type=e.event_type,
            agent_id=e.agent_id,
            principal_id=e.principal_id,
            action=e.action,
            decision=e.decision,
            risk_score=float(e.risk_score) if e.risk_score else None,
            denial_reason=e.denial_reason,
            entry_hash=e.entry_hash,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/verify-chain", response_model=ChainVerificationResponse)
async def verify_chain(
    request: Request,
    from_seq: int | None = None,
    to_seq: int | None = None,
):
    tenant_id = request.state.tenant_id
    result = await audit_service.verify_chain(tenant_id, from_seq, to_seq)
    return ChainVerificationResponse(
        **result,
        verification_timestamp=datetime.now(timezone.utc),
    )

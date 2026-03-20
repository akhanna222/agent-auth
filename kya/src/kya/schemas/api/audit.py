"""Audit schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEntry(BaseModel):
    log_id: str
    tenant_id: str
    sequence_num: int
    event_type: str
    agent_id: str | None
    principal_id: str | None
    action: str | None
    decision: str | None
    risk_score: float | None
    denial_reason: str | None
    entry_hash: str
    created_at: datetime


class ChainVerificationResponse(BaseModel):
    is_valid: bool
    entries_checked: int
    first_sequence: int | None
    last_sequence: int | None
    broken_at_sequence: int | None = None
    verification_timestamp: datetime


class HealthResponse(BaseModel):
    status: str
    dependencies: dict[str, bool]
    version: str
    uptime_seconds: float

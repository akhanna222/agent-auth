"""Verification schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RequestContext(BaseModel):
    ip_address: str = "127.0.0.1"
    user_agent: str | None = None
    timestamp: datetime | None = None


class VerifyRequest(BaseModel):
    agent_id: UUID
    signed_token: str
    action: str
    action_payload: dict
    request_context: RequestContext = RequestContext()


class VerifyResponse(BaseModel):
    is_agent_valid: bool
    is_authorized: bool
    risk_score: float
    decision: Literal["allow", "deny", "step_up"]
    decision_id: str
    denial_reason: str | None = None
    challenge_id: str | None = None
    poll_url: str | None = None
    processed_at: datetime

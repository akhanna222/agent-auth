"""Intent token schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IntentIssueRequest(BaseModel):
    delegation_id: UUID
    action: str
    action_payload: dict
    expires_in_seconds: int = Field(ge=60, le=86400, default=3600)


class IntentIssueResponse(BaseModel):
    token_id: str
    signed_token: str
    action: str
    expires_at: datetime


class IntentFromPreAuthRequest(BaseModel):
    mandate_token: str
    action: str
    action_payload: dict
    expires_in_seconds: int = Field(ge=60, le=86400, default=3600)


class IntentFromPreAuthResponse(BaseModel):
    token_id: str
    signed_token: str
    action: str
    token_mode: str
    expires_at: datetime

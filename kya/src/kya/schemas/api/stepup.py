"""Step-up challenge schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StepUpStatusResponse(BaseModel):
    status: Literal["pending", "approved", "rejected", "expired"]
    challenge_id: str
    upgraded_token: str | None = None
    decision_at: datetime | None = None
    expires_at: datetime


class StepUpRespondRequest(BaseModel):
    decision: Literal["approve", "reject"]
    totp_code: str | None = None


class StepUpRespondResponse(BaseModel):
    status: str
    challenge_id: str
    upgraded_token: str | None = None

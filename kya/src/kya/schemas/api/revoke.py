"""Revocation schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RevokeRequest(BaseModel):
    reason: Literal[
        "SECURITY_INCIDENT",
        "PERMISSION_CHANGE",
        "ACTION_CANCELLED",
        "EXPIRED",
        "USER_REQUEST",
        "ADMIN_ACTION",
    ]
    notes: str | None = None


class RevokeResponse(BaseModel):
    revoked: bool
    propagation_ms: float
    cascaded_to: list[str]
    revoked_at: datetime

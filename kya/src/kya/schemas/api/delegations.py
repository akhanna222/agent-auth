"""Delegation schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RateLimit(BaseModel):
    max_requests: int
    window_seconds: int


class TimeWindow(BaseModel):
    days: list[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]]
    hours_utc_start: int = Field(ge=0, le=23)
    hours_utc_end: int = Field(ge=0, le=23)


class GrantedScopes(BaseModel):
    allowed_actions: list[str]
    denied_actions: list[str] = []
    allowed_domains: list[str] = []
    max_amount_usd: float | None = None
    require_step_up_above_usd: float | None = None
    rate_limit: RateLimit | None = None
    time_window: TimeWindow | None = None


class DelegationCreateRequest(BaseModel):
    agent_id: UUID
    delegation_type: Literal["interactive", "autonomous", "pre_auth"] = "interactive"
    granted_scopes: GrantedScopes
    expires_in_seconds: int = Field(ge=300, le=7776000, default=86400)  # 5min to 90 days
    session_context: dict = {}


class DelegationCreateResponse(BaseModel):
    delegation_id: str
    agent_id: str
    delegation_type: str
    granted_scopes: GrantedScopes
    status: str
    issued_at: datetime
    expires_at: datetime


class AgentDelegationRequest(BaseModel):
    parent_agent_id: UUID
    child_agent_id: UUID
    parent_delegation_id: UUID
    inherited_scopes: GrantedScopes
    expires_in_seconds: int = Field(ge=300, le=7776000, default=86400)


class AgentDelegationResponse(BaseModel):
    agent_delegation_id: str
    parent_agent_id: str
    child_agent_id: str
    depth: int
    inherited_scopes: GrantedScopes
    status: str
    issued_at: datetime
    expires_at: datetime


class PreAuthRequest(BaseModel):
    agent_id: UUID
    workflow_description: str
    granted_scopes: GrantedScopes
    expires_in_seconds: int = Field(ge=300, le=7776000, default=86400)


class PreAuthResponse(BaseModel):
    delegation_id: str
    mandate_token: str
    expires_at: datetime

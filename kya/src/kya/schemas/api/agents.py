"""Agent registration request/response schemas."""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator
from typing import Literal

CAPABILITY_PATTERN = re.compile(r"^[a-z_]+\.[a-z_]+$")


class AgentRegisterRequest(BaseModel):
    display_name: str
    provider: Literal["openai", "anthropic", "custom"]
    model_version: str | None = None
    capabilities: list[str]
    owner_entity_id: UUID
    owner_type: Literal["user", "org"]
    environment: Literal["sandbox", "production"] = "sandbox"
    metadata: dict = {}

    @field_validator("capabilities")
    @classmethod
    def validate_capability_format(cls, v: list[str]) -> list[str]:
        for cap in v:
            if not CAPABILITY_PATTERN.match(cap):
                raise ValueError(
                    f"Capability '{cap}' must match pattern 'domain.action' "
                    f"(e.g., 'payment.create', 'email.send')"
                )
        return v


class AgentRegisterResponse(BaseModel):
    agent_id: str
    public_key: str
    private_key: str  # Returned ONCE only at registration
    trust_tier: str
    status: str
    created_at: datetime


class AgentSummary(BaseModel):
    agent_id: str
    display_name: str
    provider: str
    trust_tier: str
    status: str
    environment: str
    capabilities: list[str]
    created_at: datetime

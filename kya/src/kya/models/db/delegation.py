"""Delegation and AgentDelegation models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.sqlite import JSON

from .base import Base


class Delegation(Base):
    __tablename__ = "delegations"

    delegation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    principal_type: Mapped[str] = mapped_column(Text, nullable=False)
    idp_subject: Mapped[str] = mapped_column(Text, nullable=False)
    delegation_type: Mapped[str] = mapped_column(Text, nullable=False, default="interactive")
    granted_scopes: Mapped[dict] = mapped_column(JSON, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_context: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentDelegation(Base):
    __tablename__ = "agent_delegations"

    agent_delegation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    child_agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_delegation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    inherited_scopes: Mapped[dict] = mapped_column(JSON, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("depth <= 3", name="depth_limit"),
        CheckConstraint("parent_agent_id != child_agent_id", name="no_self_delegation"),
    )

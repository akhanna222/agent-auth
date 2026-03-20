"""Intent Token model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.sqlite import JSON

from .base import Base


class IntentToken(Base):
    __tablename__ = "intent_tokens"

    token_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    delegation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_mode: Mapped[str] = mapped_column(Text, nullable=False, default="single_use")
    action: Mapped[str] = mapped_column(Text, nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signed_token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unused")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("use_count <= max_uses", name="token_use_limit"),
    )

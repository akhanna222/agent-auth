"""Step-Up Challenge model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StepUpChallenge(Base):
    __tablename__ = "stepup_challenges"

    challenge_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_id: Mapped[str] = mapped_column(String(36), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="push")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    challenge_hash: Mapped[str] = mapped_column(Text, nullable=False)
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

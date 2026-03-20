"""Step-up challenge service."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from ..database import get_db_session
from ..models.db.stepup_challenge import StepUpChallenge
from ..redis_client import cache
from ..services.audit import audit_service
from ..utils.crypto import hash_payload


class StepUpService:
    async def create_challenge(
        self,
        tenant_id: str,
        agent_id: str,
        token_id: str,
        principal_id: str,
        action_payload: dict,
        channel: str = "push",
        callback_url: str | None = None,
    ) -> StepUpChallenge:
        challenge_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=300)  # 5 min timeout
        challenge_hash = hash_payload({"action_payload": action_payload, "timestamp": now.isoformat()})

        challenge = StepUpChallenge(
            challenge_id=challenge_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            token_id=token_id,
            principal_id=principal_id,
            channel=channel,
            status="pending",
            challenge_hash=challenge_hash,
            callback_url=callback_url,
            created_at=now,
            expires_at=expires_at,
        )

        async with get_db_session() as session:
            session.add(challenge)
            await session.commit()

        await cache.setex(f"kya:stepup:pending:{challenge_id}", 300, "pending")

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="stepup.initiated",
            agent_id=agent_id,
            principal_id=principal_id,
            token_id=token_id,
        )

        return challenge

    async def get_challenge(self, challenge_id: str) -> StepUpChallenge | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(StepUpChallenge).where(StepUpChallenge.challenge_id == challenge_id)
            )
            return result.scalar_one_or_none()

    async def respond(
        self,
        challenge_id: str,
        decision: str,
        tenant_id: str,
    ) -> StepUpChallenge:
        now = datetime.now(timezone.utc)

        async with get_db_session() as session:
            result = await session.execute(
                select(StepUpChallenge).where(StepUpChallenge.challenge_id == challenge_id)
            )
            challenge = result.scalar_one_or_none()
            if not challenge:
                raise ValueError("Challenge not found")
            if challenge.status != "pending":
                raise ValueError(f"Challenge already resolved: {challenge.status}")

            # Check expiry
            if now > challenge.expires_at.replace(tzinfo=timezone.utc):
                await session.execute(
                    update(StepUpChallenge).where(
                        StepUpChallenge.challenge_id == challenge_id
                    ).values(status="expired", resolved_at=now)
                )
                await session.commit()
                raise ValueError("Challenge has expired")

            new_status = "approved" if decision == "approve" else "rejected"
            await session.execute(
                update(StepUpChallenge).where(
                    StepUpChallenge.challenge_id == challenge_id
                ).values(status=new_status, resolved_at=now)
            )
            await session.commit()

            await cache.set(f"kya:stepup:pending:{challenge_id}", new_status)

            # Re-fetch
            result = await session.execute(
                select(StepUpChallenge).where(StepUpChallenge.challenge_id == challenge_id)
            )
            challenge = result.scalar_one()

        event = f"stepup.{new_status}"
        await audit_service.log(
            tenant_id=tenant_id,
            event_type=event,
            agent_id=challenge.agent_id,
            principal_id=challenge.principal_id,
            token_id=challenge.token_id,
        )

        if decision == "reject":
            # Revoke original token
            from ..services.revocation import revocation_service
            try:
                await revocation_service.revoke_token(
                    tenant_id, challenge.token_id, "STEP_UP_REJECTED"
                )
            except ValueError:
                pass

        return challenge


stepup_service = StepUpService()

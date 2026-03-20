"""Revocation service — Redis-first with cascade."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select, update

from ..database import get_db_session
from ..models.db.agent import Agent
from ..models.db.delegation import Delegation
from ..models.db.intent_token import IntentToken
from ..redis_client import cache
from ..services.audit import audit_service


class RevocationService:
    async def revoke_agent(self, tenant_id: str, agent_id: str, reason: str, notes: str | None = None) -> dict:
        start = time.monotonic()
        cascaded: list[str] = []

        # 1. Redis first
        await cache.set(f"kya:revoked:agent:{agent_id}", reason)
        await cache.delete(f"kya:agent:cache:{agent_id}")

        propagation_ms = (time.monotonic() - start) * 1000

        # 2. Find and cascade to delegations
        async with get_db_session() as session:
            result = await session.execute(
                select(Delegation).where(
                    Delegation.agent_id == agent_id,
                    Delegation.status == "active",
                )
            )
            delegations = result.scalars().all()

            now = datetime.now(timezone.utc)
            for deleg in delegations:
                await cache.set(f"kya:revoked:delegation:{deleg.delegation_id}", reason)
                cascaded.append(f"delegation:{deleg.delegation_id}")

                # Cascade to tokens
                token_result = await session.execute(
                    select(IntentToken).where(
                        IntentToken.delegation_id == deleg.delegation_id,
                        IntentToken.status == "unused",
                    )
                )
                tokens = token_result.scalars().all()
                for token in tokens:
                    ttl = max(1, int((token.expires_at - now.replace(tzinfo=None)).total_seconds()))
                    await cache.setex(f"kya:revoked:token:{token.jti}", ttl, reason)
                    cascaded.append(f"token:{token.jti}")

            # DB updates
            await session.execute(
                update(Agent).where(Agent.agent_id == agent_id).values(
                    status="revoked", revoked_at=now
                )
            )
            await session.execute(
                update(Delegation).where(
                    Delegation.agent_id == agent_id, Delegation.status == "active"
                ).values(status="revoked", revoked_at=now)
            )
            await session.execute(
                update(IntentToken).where(
                    IntentToken.agent_id == agent_id, IntentToken.status == "unused"
                ).values(status="revoked")
            )
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="agent.revoked",
            agent_id=agent_id,
            metadata={"reason": reason, "notes": notes},
        )

        return {
            "revoked": True,
            "propagation_ms": round(propagation_ms, 2),
            "cascaded_to": cascaded,
            "revoked_at": datetime.now(timezone.utc),
        }

    async def revoke_delegation(self, tenant_id: str, delegation_id: str, reason: str, notes: str | None = None) -> dict:
        start = time.monotonic()
        cascaded: list[str] = []

        await cache.set(f"kya:revoked:delegation:{delegation_id}", reason)
        propagation_ms = (time.monotonic() - start) * 1000

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)

            # Cascade to tokens
            result = await session.execute(
                select(IntentToken).where(
                    IntentToken.delegation_id == delegation_id,
                    IntentToken.status == "unused",
                )
            )
            tokens = result.scalars().all()
            for token in tokens:
                ttl = max(1, int((token.expires_at - now.replace(tzinfo=None)).total_seconds()))
                await cache.setex(f"kya:revoked:token:{token.jti}", ttl, reason)
                cascaded.append(f"token:{token.jti}")

            await session.execute(
                update(Delegation).where(Delegation.delegation_id == delegation_id).values(
                    status="revoked", revoked_at=now
                )
            )
            await session.execute(
                update(IntentToken).where(
                    IntentToken.delegation_id == delegation_id, IntentToken.status == "unused"
                ).values(status="revoked")
            )
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="delegation.revoked",
            delegation_id=delegation_id,
            metadata={"reason": reason},
        )

        return {
            "revoked": True,
            "propagation_ms": round(propagation_ms, 2),
            "cascaded_to": cascaded,
            "revoked_at": datetime.now(timezone.utc),
        }

    async def revoke_token(self, tenant_id: str, token_id: str, reason: str, notes: str | None = None) -> dict:
        start = time.monotonic()

        async with get_db_session() as session:
            result = await session.execute(
                select(IntentToken).where(IntentToken.token_id == token_id)
            )
            token = result.scalar_one_or_none()
            if not token:
                raise ValueError("Token not found")

            now = datetime.now(timezone.utc)
            ttl = max(1, int((token.expires_at - now.replace(tzinfo=None)).total_seconds()))
            await cache.setex(f"kya:revoked:token:{token.jti}", ttl, reason)
            propagation_ms = (time.monotonic() - start) * 1000

            await session.execute(
                update(IntentToken).where(IntentToken.token_id == token_id).values(status="revoked")
            )
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="token.revoked",
            token_id=token_id,
            metadata={"reason": reason},
        )

        return {
            "revoked": True,
            "propagation_ms": round(propagation_ms, 2),
            "cascaded_to": [],
            "revoked_at": datetime.now(timezone.utc),
        }


revocation_service = RevocationService()

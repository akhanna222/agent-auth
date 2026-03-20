"""Audit log service with hash chaining."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from ..database import get_db_session
from ..models.db.audit_log import AuditLog
from ..utils.crypto import hash_payload, compute_entry_hash


class AuditService:
    async def log(
        self,
        tenant_id: str,
        event_type: str,
        agent_id: str | None = None,
        principal_id: str | None = None,
        token_id: str | None = None,
        delegation_id: str | None = None,
        action: str | None = None,
        decision: str | None = None,
        risk_score: float | None = None,
        denial_reason: str | None = None,
        request_payload: dict | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        async with get_db_session() as session:
            # Get next sequence number
            result = await session.execute(
                select(func.coalesce(func.max(AuditLog.sequence_num), 0))
            )
            next_seq = result.scalar() + 1

            # Fetch previous entry hash
            prev = await session.execute(
                select(AuditLog.entry_hash)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.sequence_num.desc())
                .limit(1)
            )
            prev_row = prev.scalar_one_or_none()
            previous_hash = prev_row if prev_row else "GENESIS"

            # Build entry dict for hashing
            now = datetime.now(timezone.utc)
            created_at_str = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            entry_dict = {
                "tenant_id": tenant_id,
                "event_type": event_type,
                "agent_id": agent_id or "",
                "principal_id": principal_id or "",
                "action": action or "",
                "decision": decision or "",
                "risk_score": risk_score,
                "created_at": created_at_str,
            }

            request_hash = hash_payload(request_payload or {})
            entry_hash = compute_entry_hash(entry_dict, previous_hash)

            log_entry = AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                sequence_num=next_seq,
                event_type=event_type,
                agent_id=agent_id,
                principal_id=principal_id,
                token_id=token_id,
                delegation_id=delegation_id,
                action=action,
                decision=decision,
                risk_score=risk_score,
                denial_reason=denial_reason,
                request_hash=request_hash,
                previous_hash=previous_hash,
                entry_hash=entry_hash,
                metadata_=metadata or {},
                created_at=now,
            )
            session.add(log_entry)
            await session.commit()
            return log_entry

    async def verify_chain(
        self, tenant_id: str, from_seq: int | None = None, to_seq: int | None = None
    ) -> dict:
        async with get_db_session() as session:
            query = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.sequence_num)
            )
            if from_seq is not None:
                query = query.where(AuditLog.sequence_num >= from_seq)
            if to_seq is not None:
                query = query.where(AuditLog.sequence_num <= to_seq)

            result = await session.execute(query)
            entries = result.scalars().all()

            if not entries:
                return {
                    "is_valid": True,
                    "entries_checked": 0,
                    "first_sequence": None,
                    "last_sequence": None,
                    "broken_at_sequence": None,
                }

            prev_hash = entries[0].previous_hash
            for entry in entries:
                if entry.previous_hash != prev_hash:
                    return {
                        "is_valid": False,
                        "entries_checked": entries.index(entry) + 1,
                        "first_sequence": entries[0].sequence_num,
                        "last_sequence": entry.sequence_num,
                        "broken_at_sequence": entry.sequence_num,
                    }
                # Recompute entry hash
                entry_dict = {
                    "tenant_id": entry.tenant_id,
                    "event_type": entry.event_type,
                    "agent_id": entry.agent_id or "",
                    "principal_id": entry.principal_id or "",
                    "action": entry.action or "",
                    "decision": entry.decision or "",
                    "risk_score": float(entry.risk_score) if entry.risk_score else None,
                    "created_at": entry.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                }
                recomputed = compute_entry_hash(entry_dict, prev_hash)
                if recomputed != entry.entry_hash:
                    return {
                        "is_valid": False,
                        "entries_checked": entries.index(entry) + 1,
                        "first_sequence": entries[0].sequence_num,
                        "last_sequence": entry.sequence_num,
                        "broken_at_sequence": entry.sequence_num,
                    }
                prev_hash = entry.entry_hash

            return {
                "is_valid": True,
                "entries_checked": len(entries),
                "first_sequence": entries[0].sequence_num,
                "last_sequence": entries[-1].sequence_num,
                "broken_at_sequence": None,
            }

    async def get_events(
        self, tenant_id: str, agent_id: str | None = None, event_type: str | None = None, limit: int = 100
    ) -> list[AuditLog]:
        async with get_db_session() as session:
            query = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.sequence_num.desc())
                .limit(limit)
            )
            if agent_id:
                query = query.where(AuditLog.agent_id == agent_id)
            if event_type:
                query = query.where(AuditLog.event_type == event_type)
            result = await session.execute(query)
            return list(result.scalars().all())


audit_service = AuditService()

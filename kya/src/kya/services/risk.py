"""Risk scoring engine with 6 weighted signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from ..database import get_db_session
from ..models.db.agent import Agent
from ..models.db.audit_log import AuditLog

DEFAULT_THRESHOLDS = {
    "auto_allow": 50,   # score <= 50: OPA decision stands
    "step_up": 75,      # 51-75: escalate to step_up even if OPA said allow
    "auto_deny": 76,    # score > 75: deny even if OPA said allow
}


class RiskEngine:
    async def score(self, agent: Agent, action: str, action_payload: dict) -> float:
        signals = [
            await self.velocity_signal(agent.agent_id),
            await self.payload_deviation_signal(agent.agent_id, action_payload),
            await self.action_novelty_signal(agent.agent_id, action),
            self.time_anomaly_signal(),
            self.agent_age_signal(agent),
            self.trust_tier_signal(agent),
        ]
        return min(100.0, sum(signals))

    async def velocity_signal(self, agent_id: str) -> float:
        """Count actions in last 1hr vs 7-day avg. >3x = 25 points."""
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        seven_days_ago = now - timedelta(days=7)

        async with get_db_session() as session:
            # Last hour count
            result = await session.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.agent_id == agent_id,
                    AuditLog.created_at >= one_hour_ago,
                )
            )
            hour_count = result.scalar() or 0

            # 7-day hourly avg
            result = await session.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.agent_id == agent_id,
                    AuditLog.created_at >= seven_days_ago,
                )
            )
            week_count = result.scalar() or 0

        avg_hourly = (week_count / (7 * 24)) if week_count > 0 else 1
        ratio = hour_count / max(avg_hourly, 1)
        if ratio > 3:
            return 25.0
        return min(25.0, (ratio / 3) * 25)

    async def payload_deviation_signal(self, agent_id: str, action_payload: dict) -> float:
        """Amount vs historical avg. >5x = 20 points."""
        amount = action_payload.get("amount_usd")
        if amount is None:
            return 0.0
        # Simplified: just check if amount > 1000 for now
        if float(amount) > 1000:
            return 20.0
        if float(amount) > 500:
            return 10.0
        return 0.0

    async def action_novelty_signal(self, agent_id: str, action: str) -> float:
        """First time this action seen = 20 points."""
        async with get_db_session() as session:
            result = await session.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.agent_id == agent_id,
                    AuditLog.action == action,
                )
            )
            count = result.scalar() or 0
        return 20.0 if count == 0 else 0.0

    def time_anomaly_signal(self) -> float:
        """Outside business hours = 15 points."""
        hour = datetime.now(timezone.utc).hour
        if hour < 6 or hour > 22:
            return 15.0
        return 0.0

    def agent_age_signal(self, agent: Agent) -> float:
        """Agent < 24hrs old = 10 points."""
        age = datetime.now(timezone.utc) - agent.created_at.replace(tzinfo=timezone.utc)
        if age < timedelta(hours=24):
            return 10.0
        return 0.0

    def trust_tier_signal(self, agent: Agent) -> float:
        """unverified=10, verified=5, certified=0."""
        tiers = {"unverified": 10.0, "verified": 5.0, "certified": 0.0}
        return tiers.get(agent.trust_tier, 10.0)


risk_engine = RiskEngine()

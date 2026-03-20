"""Identity service — agent registration and management."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from ..database import get_db_session
from ..models.db.agent import Agent
from ..models.db.tenant import Tenant
from ..schemas.api.agents import AgentRegisterRequest, AgentRegisterResponse
from ..utils.crypto import generate_ed25519_keypair
from ..services.audit import audit_service


class IdentityService:
    async def register_agent(
        self, tenant_id: str, request: AgentRegisterRequest
    ) -> AgentRegisterResponse:
        # Validate: production agents must be verified or higher
        if request.environment == "production":
            raise ValueError("Unverified agents cannot be registered in production environment")

        # Generate Ed25519 keypair
        public_key_pem, private_key_pem = generate_ed25519_keypair()

        now = datetime.now(timezone.utc)
        agent_id = str(uuid.uuid4())

        agent = Agent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            display_name=request.display_name,
            provider=request.provider,
            model_version=request.model_version,
            capabilities=request.capabilities,
            public_key=public_key_pem,
            trust_tier="unverified",
            status="active",
            owner_entity_id=str(request.owner_entity_id),
            owner_type=request.owner_type,
            environment=request.environment,
            created_at=now,
            metadata_=request.metadata,
        )

        async with get_db_session() as session:
            session.add(agent)
            await session.commit()

        # Audit log
        await audit_service.log(
            tenant_id=tenant_id,
            event_type="agent.registered",
            agent_id=agent_id,
            metadata={"provider": request.provider, "environment": request.environment},
        )

        return AgentRegisterResponse(
            agent_id=agent_id,
            public_key=public_key_pem,
            private_key=private_key_pem,  # Returned ONCE only
            trust_tier="unverified",
            status="active",
            created_at=now,
        )

    async def get_agent(self, agent_id: str) -> Agent | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.agent_id == agent_id)
            )
            return result.scalar_one_or_none()

    async def list_agents(self, tenant_id: str) -> list[Agent]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.created_at.desc())
            )
            return list(result.scalars().all())

    async def ensure_tenant(self, tenant_id: str, name: str = "Default", slug: str = "default") -> Tenant:
        """Get or create a tenant."""
        async with get_db_session() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.tenant_id == tenant_id)
            )
            tenant = result.scalar_one_or_none()
            if not tenant:
                tenant = Tenant(
                    tenant_id=tenant_id,
                    name=name,
                    slug=slug,
                    status="active",
                )
                session.add(tenant)
                await session.commit()
            return tenant

    async def list_tenants(self) -> list[Tenant]:
        async with get_db_session() as session:
            result = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
            return list(result.scalars().all())


identity_service = IdentityService()

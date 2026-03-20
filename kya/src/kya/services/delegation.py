"""Delegation service — human→agent and agent→agent delegation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..database import get_db_session
from ..models.db.agent import Agent
from ..models.db.delegation import AgentDelegation, Delegation
from ..schemas.api.delegations import (
    AgentDelegationRequest,
    DelegationCreateRequest,
    GrantedScopes,
    PreAuthRequest,
)
from ..services.audit import audit_service
from ..utils.crypto import sign_jwt


class DelegationService:
    async def create_delegation(
        self, tenant_id: str, principal_id: str, request: DelegationCreateRequest
    ) -> Delegation:
        agent_id = str(request.agent_id)

        # Verify agent exists and belongs to same tenant
        async with get_db_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.agent_id == agent_id, Agent.tenant_id == tenant_id)
            )
            agent = result.scalar_one_or_none()
            if not agent:
                raise ValueError("Agent not found or does not belong to this tenant")
            if agent.status != "active":
                raise ValueError("Agent is not active")

            # Verify all actions are in agent capabilities
            for action in request.granted_scopes.allowed_actions:
                if action not in agent.capabilities:
                    raise ValueError(
                        f"Action '{action}' is not in agent capabilities: {agent.capabilities}"
                    )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=request.expires_in_seconds)

        delegation = Delegation(
            delegation_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            agent_id=agent_id,
            principal_id=principal_id,
            principal_type="user",
            idp_subject=principal_id,
            delegation_type=request.delegation_type,
            granted_scopes=request.granted_scopes.model_dump(),
            constraints=request.session_context,
            status="active",
            issued_at=now,
            expires_at=expires_at,
            session_context=request.session_context,
        )

        async with get_db_session() as session:
            session.add(delegation)
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="delegation.created",
            agent_id=agent_id,
            principal_id=principal_id,
            delegation_id=delegation.delegation_id,
        )

        return delegation

    async def create_agent_delegation(
        self, tenant_id: str, request: AgentDelegationRequest
    ) -> AgentDelegation:
        parent_delegation_id = str(request.parent_delegation_id)

        async with get_db_session() as session:
            # Fetch parent delegation
            result = await session.execute(
                select(Delegation).where(Delegation.delegation_id == parent_delegation_id)
            )
            parent_deleg = result.scalar_one_or_none()
            if not parent_deleg:
                raise ValueError("Parent delegation not found")
            if parent_deleg.status != "active":
                raise ValueError("Parent delegation is not active")

            # Scope contraction: child scopes must be subset of parent
            parent_scopes = GrantedScopes(**parent_deleg.granted_scopes)
            child_actions = set(request.inherited_scopes.allowed_actions)
            parent_actions = set(parent_scopes.allowed_actions)
            if not child_actions.issubset(parent_actions):
                raise ValueError("Child scope exceeds parent scope")

            if (
                request.inherited_scopes.max_amount_usd is not None
                and parent_scopes.max_amount_usd is not None
                and request.inherited_scopes.max_amount_usd > parent_scopes.max_amount_usd
            ):
                raise ValueError("Child amount limit exceeds parent limit")

            # Compute depth
            existing = await session.execute(
                select(AgentDelegation).where(
                    AgentDelegation.parent_delegation_id == parent_delegation_id
                )
            )
            existing_row = existing.scalar_one_or_none()
            depth = (existing_row.depth + 1) if existing_row else 1
            if depth > 3:
                raise ValueError("Agent delegation depth exceeds maximum of 3")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=request.expires_in_seconds)

        # Child cannot outlive parent
        if expires_at > parent_deleg.expires_at:
            expires_at = parent_deleg.expires_at

        agent_deleg = AgentDelegation(
            agent_delegation_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            parent_agent_id=str(request.parent_agent_id),
            child_agent_id=str(request.child_agent_id),
            parent_delegation_id=parent_delegation_id,
            inherited_scopes=request.inherited_scopes.model_dump(),
            depth=depth,
            status="active",
            issued_at=now,
            expires_at=expires_at,
        )

        async with get_db_session() as session:
            session.add(agent_deleg)
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="agent_delegation.created",
            agent_id=str(request.child_agent_id),
            delegation_id=agent_deleg.agent_delegation_id,
        )

        return agent_deleg

    async def create_pre_auth(
        self, tenant_id: str, principal_id: str, request: PreAuthRequest, platform_private_key: str
    ) -> tuple[Delegation, str]:
        """Create pre-auth mandate. Returns (delegation, mandate_token_jwt)."""
        agent_id = str(request.agent_id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=request.expires_in_seconds)

        delegation = Delegation(
            delegation_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            agent_id=agent_id,
            principal_id=principal_id,
            principal_type="user",
            idp_subject=principal_id,
            delegation_type="pre_auth",
            granted_scopes=request.granted_scopes.model_dump(),
            constraints={},
            status="active",
            issued_at=now,
            expires_at=expires_at,
            session_context={"workflow_description": request.workflow_description},
        )

        async with get_db_session() as session:
            session.add(delegation)
            await session.commit()

        mandate_payload = {
            "sub": principal_id,
            "delegation_id": delegation.delegation_id,
            "workflow_description": request.workflow_description,
            "allowed_actions": request.granted_scopes.allowed_actions,
            "constraints": request.granted_scopes.model_dump(),
        }
        mandate_token = sign_jwt(
            mandate_payload,
            platform_private_key,
            expiry_seconds=request.expires_in_seconds,
        )

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="pre_auth.created",
            agent_id=agent_id,
            principal_id=principal_id,
            delegation_id=delegation.delegation_id,
        )

        return delegation, mandate_token

    async def get_delegation(self, delegation_id: str) -> Delegation | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Delegation).where(Delegation.delegation_id == delegation_id)
            )
            return result.scalar_one_or_none()

    async def list_delegations(self, tenant_id: str) -> list[Delegation]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Delegation).where(Delegation.tenant_id == tenant_id).order_by(Delegation.issued_at.desc())
            )
            return list(result.scalars().all())


delegation_service = DelegationService()

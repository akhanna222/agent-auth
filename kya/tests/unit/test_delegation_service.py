"""Tests for delegation service."""
import uuid

import pytest

from kya.schemas.api.agents import AgentRegisterRequest
from kya.schemas.api.delegations import (
    AgentDelegationRequest,
    DelegationCreateRequest,
    GrantedScopes,
)
from kya.services.delegation import delegation_service
from kya.services.identity import identity_service

TENANT_ID = str(uuid.uuid4())
PRINCIPAL_ID = str(uuid.uuid4())


async def _create_agent(capabilities=None):
    caps = capabilities or ["payment.create", "email.send"]
    await identity_service.ensure_tenant(TENANT_ID)
    resp = await identity_service.register_agent(
        TENANT_ID,
        AgentRegisterRequest(
            display_name="Test Agent",
            provider="anthropic",
            capabilities=caps,
            owner_entity_id=uuid.uuid4(),
            owner_type="user",
        ),
    )
    return resp.agent_id


async def test_create_delegation_success():
    agent_id = await _create_agent()
    request = DelegationCreateRequest(
        agent_id=uuid.UUID(agent_id),
        granted_scopes=GrantedScopes(allowed_actions=["payment.create"]),
        expires_in_seconds=3600,
    )
    deleg = await delegation_service.create_delegation(TENANT_ID, PRINCIPAL_ID, request)
    assert deleg.status == "active"
    assert deleg.delegation_type == "interactive"


async def test_delegation_rejects_action_not_in_capabilities():
    agent_id = await _create_agent(capabilities=["email.send"])
    request = DelegationCreateRequest(
        agent_id=uuid.UUID(agent_id),
        granted_scopes=GrantedScopes(allowed_actions=["payment.create"]),
        expires_in_seconds=3600,
    )
    with pytest.raises(ValueError, match="not in agent capabilities"):
        await delegation_service.create_delegation(TENANT_ID, PRINCIPAL_ID, request)


async def test_agent_delegation_scope_contraction_enforced():
    agent1_id = await _create_agent(capabilities=["payment.create", "email.send"])
    agent2_id = await _create_agent(capabilities=["payment.create"])

    # Create parent delegation with limited scopes
    parent_deleg = await delegation_service.create_delegation(
        TENANT_ID,
        PRINCIPAL_ID,
        DelegationCreateRequest(
            agent_id=uuid.UUID(agent1_id),
            granted_scopes=GrantedScopes(allowed_actions=["payment.create"]),
            expires_in_seconds=3600,
        ),
    )

    # Try to delegate email.send (not in parent scope) — should fail
    with pytest.raises(ValueError, match="exceeds parent scope"):
        await delegation_service.create_agent_delegation(
            TENANT_ID,
            AgentDelegationRequest(
                parent_agent_id=uuid.UUID(agent1_id),
                child_agent_id=uuid.UUID(agent2_id),
                parent_delegation_id=uuid.UUID(parent_deleg.delegation_id),
                inherited_scopes=GrantedScopes(allowed_actions=["email.send"]),
                expires_in_seconds=3600,
            ),
        )

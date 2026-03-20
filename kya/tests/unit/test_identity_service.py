"""Tests for identity service."""
import uuid

import pytest

from kya.schemas.api.agents import AgentRegisterRequest
from kya.services.identity import identity_service

TENANT_ID = str(uuid.uuid4())


async def test_register_agent_success():
    await identity_service.ensure_tenant(TENANT_ID)
    request = AgentRegisterRequest(
        display_name="Test Agent",
        provider="anthropic",
        capabilities=["payment.create", "email.send"],
        owner_entity_id=uuid.uuid4(),
        owner_type="user",
        environment="sandbox",
    )
    response = await identity_service.register_agent(TENANT_ID, request)
    assert response.agent_id
    assert response.public_key
    assert response.private_key
    assert response.trust_tier == "unverified"
    assert response.status == "active"


async def test_register_agent_invalid_capability_format():
    with pytest.raises(Exception):
        AgentRegisterRequest(
            display_name="Bad Agent",
            provider="openai",
            capabilities=["InvalidFormat"],
            owner_entity_id=uuid.uuid4(),
            owner_type="user",
        )


async def test_register_production_agent_requires_verified_tier():
    await identity_service.ensure_tenant(TENANT_ID)
    request = AgentRegisterRequest(
        display_name="Prod Agent",
        provider="anthropic",
        capabilities=["payment.create"],
        owner_entity_id=uuid.uuid4(),
        owner_type="user",
        environment="production",
    )
    with pytest.raises(ValueError, match="production"):
        await identity_service.register_agent(TENANT_ID, request)

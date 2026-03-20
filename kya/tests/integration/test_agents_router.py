"""Integration tests for agents API."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from kya.main import app

TENANT_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Principal-ID": str(uuid.uuid4())}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_register_agent_end_to_end(client):
    resp = await client.post(
        "/v1/agents/register",
        json={
            "display_name": "E2E Agent",
            "provider": "anthropic",
            "capabilities": ["payment.create"],
            "owner_entity_id": str(uuid.uuid4()),
            "owner_type": "user",
            "environment": "sandbox",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "agent_id" in data
    assert "private_key" in data
    assert data["trust_tier"] == "unverified"


async def test_register_agent_missing_tenant_header(client):
    resp = await client.post(
        "/v1/agents/register",
        json={
            "display_name": "No Tenant",
            "provider": "openai",
            "capabilities": ["email.send"],
            "owner_entity_id": str(uuid.uuid4()),
            "owner_type": "user",
        },
    )
    assert resp.status_code == 403


async def test_register_agent_capability_format_rejected(client):
    resp = await client.post(
        "/v1/agents/register",
        json={
            "display_name": "Bad Caps",
            "provider": "openai",
            "capabilities": ["InvalidCapability"],
            "owner_entity_id": str(uuid.uuid4()),
            "owner_type": "user",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 422  # Pydantic validation error

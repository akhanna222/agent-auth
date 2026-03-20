"""Integration tests for the verification endpoint."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from kya.main import app

TENANT_ID = str(uuid.uuid4())
PRINCIPAL_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-ID": TENANT_ID, "X-Principal-ID": PRINCIPAL_ID}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _full_setup(client):
    """Register agent, create delegation, issue token. Returns (agent_id, token_data)."""
    # Register agent
    resp = await client.post(
        "/v1/agents/register",
        json={
            "display_name": "Verify Test Agent",
            "provider": "anthropic",
            "capabilities": ["payment.create"],
            "owner_entity_id": PRINCIPAL_ID,
            "owner_type": "user",
        },
        headers=HEADERS,
    )
    agent = resp.json()

    # Create delegation
    resp = await client.post(
        "/v1/delegations",
        json={
            "agent_id": agent["agent_id"],
            "granted_scopes": {
                "allowed_actions": ["payment.create"],
                "max_amount_usd": 1000,
                "require_step_up_above_usd": 500,
            },
            "expires_in_seconds": 3600,
        },
        headers=HEADERS,
    )
    deleg = resp.json()

    # Issue token
    resp = await client.post(
        "/v1/intent/issue",
        json={
            "delegation_id": deleg["delegation_id"],
            "action": "payment.create",
            "action_payload": {"amount_usd": 100, "recipient": "test@example.com"},
        },
        headers=HEADERS,
    )
    token = resp.json()
    return agent["agent_id"], token


async def test_full_verification_allow(client):
    agent_id, token = await _full_setup(client)
    resp = await client.post(
        "/v1/verify-agent-action",
        json={
            "agent_id": agent_id,
            "signed_token": token["signed_token"],
            "action": "payment.create",
            "action_payload": {"amount_usd": 100, "recipient": "test@example.com"},
            "request_context": {"ip_address": "127.0.0.1"},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["decision"] == "allow"
    assert data["is_authorized"] is True


async def test_full_verification_deny_revoked(client):
    agent_id, token = await _full_setup(client)
    # Revoke the agent
    await client.post(
        f"/v1/revoke/agent/{agent_id}",
        json={"reason": "SECURITY_INCIDENT"},
        headers=HEADERS,
    )
    # Verify should fail
    resp = await client.post(
        "/v1/verify-agent-action",
        json={
            "agent_id": agent_id,
            "signed_token": token["signed_token"],
            "action": "payment.create",
            "action_payload": {"amount_usd": 100, "recipient": "test@example.com"},
            "request_context": {"ip_address": "127.0.0.1"},
        },
        headers=HEADERS,
    )
    body = resp.json()
    data = body.get("data", body)
    assert data["decision"] == "deny"

"""Tests for intent service."""
import uuid

import pytest

from kya.dependencies import get_platform_keys
from kya.schemas.api.agents import AgentRegisterRequest
from kya.schemas.api.delegations import DelegationCreateRequest, GrantedScopes
from kya.schemas.api.intent import IntentIssueRequest
from kya.services.delegation import delegation_service
from kya.services.identity import identity_service
from kya.services.intent import intent_service
from kya.utils.crypto import hash_payload

TENANT_ID = str(uuid.uuid4())
PRINCIPAL_ID = str(uuid.uuid4())


async def _setup():
    """Create agent and delegation, return (agent_id, delegation_id)."""
    await identity_service.ensure_tenant(TENANT_ID)
    agent_resp = await identity_service.register_agent(
        TENANT_ID,
        AgentRegisterRequest(
            display_name="Token Test Agent",
            provider="anthropic",
            capabilities=["payment.create", "email.send"],
            owner_entity_id=uuid.uuid4(),
            owner_type="user",
        ),
    )
    deleg = await delegation_service.create_delegation(
        TENANT_ID,
        PRINCIPAL_ID,
        DelegationCreateRequest(
            agent_id=uuid.UUID(agent_resp.agent_id),
            granted_scopes=GrantedScopes(
                allowed_actions=["payment.create", "email.send"],
                max_amount_usd=1000.0,
            ),
            expires_in_seconds=3600,
        ),
    )
    return agent_resp.agent_id, deleg.delegation_id


async def test_issue_token_success():
    _, delegation_id = await _setup()
    _, private_key = get_platform_keys()
    token = await intent_service.issue_token(
        TENANT_ID,
        PRINCIPAL_ID,
        IntentIssueRequest(
            delegation_id=uuid.UUID(delegation_id),
            action="payment.create",
            action_payload={"amount_usd": 100, "recipient": "test@example.com"},
        ),
        private_key,
    )
    assert token.status == "unused"
    assert token.action == "payment.create"
    assert token.signed_token


async def test_token_payload_hash_not_raw_payload():
    _, delegation_id = await _setup()
    _, private_key = get_platform_keys()
    payload = {"amount_usd": 100, "recipient": "test@example.com"}
    token = await intent_service.issue_token(
        TENANT_ID,
        PRINCIPAL_ID,
        IntentIssueRequest(
            delegation_id=uuid.UUID(delegation_id),
            action="payment.create",
            action_payload=payload,
        ),
        private_key,
    )
    # The signed JWT should contain action_hash, not the raw payload
    from kya.utils.crypto import verify_jwt
    public_key, _ = get_platform_keys()
    claims = verify_jwt(token.signed_token, public_key)
    assert "action_hash" in claims
    assert claims["action_hash"] == hash_payload(payload)
    assert "action_payload" not in claims


async def test_issue_token_amount_exceeds_delegation_limit():
    _, delegation_id = await _setup()
    _, private_key = get_platform_keys()
    with pytest.raises(ValueError, match="exceeds delegation limit"):
        await intent_service.issue_token(
            TENANT_ID,
            PRINCIPAL_ID,
            IntentIssueRequest(
                delegation_id=uuid.UUID(delegation_id),
                action="payment.create",
                action_payload={"amount_usd": 5000},
            ),
            private_key,
        )

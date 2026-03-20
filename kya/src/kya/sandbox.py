"""MPGS-compatible response wrapper and sandbox data seeding."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


def wrap_response(data: dict, request_id: str | None = None, start_time: float | None = None) -> dict:
    """Wrap response in MPGS-expected {data, meta} format."""
    meta = {
        "request_id": request_id or str(uuid.uuid4()),
        "version": "1.0",
    }
    if start_time is not None:
        meta["latency_ms"] = round((time.time() - start_time) * 1000, 1)
    return {"data": data, "meta": meta}


# Pre-seeded sandbox test agents
SANDBOX_TENANT_ID = "mastercard-sandbox"
SANDBOX_PRINCIPAL_ID = "principal_mc_sandbox_001"

SANDBOX_AGENTS = {
    "agt_mc_test_001": {
        "agent_id": "agt_mc_test_001",
        "display_name": "InvoicePaymentAgent",
        "provider": "anthropic",
        "model_version": "claude-sonnet-4-6",
        "capabilities": ["payment.create", "payment.refund", "payment.status"],
        "trust_tier": "verified",
        "status": "active",
        "environment": "sandbox",
        "owner_entity_id": SANDBOX_PRINCIPAL_ID,
        "owner_type": "org",
    },
    "agt_mc_test_002": {
        "agent_id": "agt_mc_test_002",
        "display_name": "CardholderAssistant",
        "provider": "openai",
        "model_version": "gpt-4o",
        "capabilities": ["payment.create", "payment.status"],
        "trust_tier": "verified",
        "status": "active",
        "environment": "sandbox",
        "owner_entity_id": SANDBOX_PRINCIPAL_ID,
        "owner_type": "org",
    },
    "agt_mc_test_003": {
        "agent_id": "agt_mc_test_003",
        "display_name": "FraudReviewAgent",
        "provider": "anthropic",
        "model_version": "claude-opus-4-6",
        "capabilities": ["payment.create", "payment.refund", "payment.status", "fraud.review"],
        "trust_tier": "certified",
        "status": "active",
        "environment": "sandbox",
        "owner_entity_id": SANDBOX_PRINCIPAL_ID,
        "owner_type": "org",
    },
    "agt_mc_test_revoked": {
        "agent_id": "agt_mc_test_revoked",
        "display_name": "RevokedAgent",
        "provider": "custom",
        "model_version": None,
        "capabilities": ["payment.create"],
        "trust_tier": "verified",
        "status": "revoked",
        "environment": "sandbox",
        "owner_entity_id": SANDBOX_PRINCIPAL_ID,
        "owner_type": "org",
    },
}

# Sandbox delegations — what each agent is allowed to do
SANDBOX_DELEGATIONS = {
    "del_mc_test_001": {
        "delegation_id": "del_mc_test_001",
        "agent_id": "agt_mc_test_001",
        "delegation_type": "interactive",
        "status": "active",
        "granted_scopes": {
            "allowed_actions": ["payment.create", "payment.status"],
            "denied_actions": ["payment.refund"],
            "max_amount_usd": 10000,
            "require_step_up_above_usd": 5000,
            "time_window": {
                "days": ["mon", "tue", "wed", "thu", "fri"],
                "hours_utc_start": 6,
                "hours_utc_end": 22,
            },
        },
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    },
    "del_mc_test_002": {
        "delegation_id": "del_mc_test_002",
        "agent_id": "agt_mc_test_002",
        "delegation_type": "interactive",
        "status": "active",
        "granted_scopes": {
            "allowed_actions": ["payment.create", "payment.status"],
            "denied_actions": [],
            "max_amount_usd": 500,
            "require_step_up_above_usd": 300,
        },
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    },
    "del_mc_test_003": {
        "delegation_id": "del_mc_test_003",
        "agent_id": "agt_mc_test_003",
        "delegation_type": "interactive",
        "status": "active",
        "granted_scopes": {
            "allowed_actions": ["payment.create", "payment.refund", "fraud.review"],
            "denied_actions": [],
            "max_amount_usd": 50000,
            "require_step_up_above_usd": 25000,
        },
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    },
}

# Sandbox tokens — map token string to test scenario
SANDBOX_TOKENS = {
    "tok_mc_allow_sandbox": {
        "agent_id": "agt_mc_test_001",
        "delegation_id": "del_mc_test_001",
        "action": "payment.create",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_stepup_sandbox": {
        "agent_id": "agt_mc_test_001",
        "delegation_id": "del_mc_test_001",
        "action": "payment.create",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_overlimit_sandbox": {
        "agent_id": "agt_mc_test_002",
        "delegation_id": "del_mc_test_002",
        "action": "payment.create",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_used_sandbox": {
        "agent_id": "agt_mc_test_001",
        "delegation_id": "del_mc_test_001",
        "action": "payment.create",
        "status": "used",
        "use_count": 1,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_weekend_sandbox": {
        "agent_id": "agt_mc_test_001",
        "delegation_id": "del_mc_test_001",
        "action": "payment.create",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_refund_sandbox": {
        "agent_id": "agt_mc_test_001",
        "delegation_id": "del_mc_test_001",
        "action": "payment.refund",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
    "tok_mc_fraud_allow_sandbox": {
        "agent_id": "agt_mc_test_003",
        "delegation_id": "del_mc_test_003",
        "action": "payment.create",
        "status": "unused",
        "use_count": 0,
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    },
}

# Valid sandbox API keys
SANDBOX_API_KEYS = {
    "kya_sandbox_mc_test_4f8a2b1c9d": SANDBOX_TENANT_ID,
}


def is_sandbox_token(token_str: str) -> bool:
    """Check if token is a sandbox test token."""
    return token_str.startswith("tok_mc_") and token_str.endswith("_sandbox")


def get_sandbox_agent(agent_id: str) -> dict | None:
    return SANDBOX_AGENTS.get(agent_id)


def get_sandbox_delegation(delegation_id: str) -> dict | None:
    return SANDBOX_DELEGATIONS.get(delegation_id)


def get_sandbox_token(token_str: str) -> dict | None:
    return SANDBOX_TOKENS.get(token_str)


# Reverse index: agent_id → delegation (O(1) lookup)
_AGENT_TO_DELEGATION = {d["agent_id"]: d for d in SANDBOX_DELEGATIONS.values()}

# Pre-computed creation timestamp for sandbox entities
SANDBOX_CREATED_AT = datetime.now(timezone.utc).isoformat()


def resolve_sandbox_delegation_for_agent(agent_id: str) -> dict | None:
    """Find the delegation for a given sandbox agent."""
    return _AGENT_TO_DELEGATION.get(agent_id)

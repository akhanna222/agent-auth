"""Tests for the built-in policy engine."""
from kya.services.policy import evaluate_policy


def _base_input(**overrides):
    inp = {
        "agent": {"agent_id": "a1", "status": "active", "environment": "development", "trust_tier": "verified"},
        "delegation": {
            "delegation_id": "d1",
            "status": "active",
            "granted_scopes": {
                "allowed_actions": ["payment.create"],
                "denied_actions": [],
                "max_amount_usd": 1000,
                "require_step_up_above_usd": 500,
            },
            "expires_at": "2099-01-01T00:00:00Z",
        },
        "token": {
            "token_id": "t1",
            "jti": "jti1",
            "status": "unused",
            "action": "payment.create",
            "action_hash": "abc123",
            "expires_at": "2099-01-01T00:00:00Z",
            "use_count": 0,
            "max_uses": 1,
        },
        "action": "payment.create",
        "payload": {"amount_usd": 100},
        "payload_hash": "abc123",
        "revocations": {"agent_revoked": False, "delegation_revoked": False, "token_revoked": False},
        "context": {"ip_address": "127.0.0.1", "environment": "development", "day_of_week": "mon", "hour_utc": 12},
        "current_time": "2024-06-01T12:00:00Z",
    }
    inp.update(overrides)
    return inp


def test_allow_happy_path():
    result = evaluate_policy(_base_input())
    assert result["allow"] is True
    assert result["deny"] is False


def test_deny_revoked_agent():
    result = evaluate_policy(_base_input(revocations={"agent_revoked": True, "delegation_revoked": False, "token_revoked": False}))
    assert result["deny"] is True
    assert result["deny_reason"] == "AGENT_REVOKED"


def test_deny_revoked_delegation():
    result = evaluate_policy(_base_input(revocations={"agent_revoked": False, "delegation_revoked": True, "token_revoked": False}))
    assert result["deny"] is True
    assert result["deny_reason"] == "DELEGATION_REVOKED"


def test_deny_replayed_token():
    inp = _base_input()
    inp["token"]["status"] = "used"
    result = evaluate_policy(inp)
    assert result["deny"] is True
    assert result["deny_reason"] == "TOKEN_ALREADY_USED"


def test_deny_token_payload_mismatch():
    result = evaluate_policy(_base_input(payload_hash="wrong_hash"))
    assert result["deny"] is True
    assert result["deny_reason"] == "TOKEN_PAYLOAD_MISMATCH"


def test_deny_action_not_permitted():
    result = evaluate_policy(_base_input(action="email.send"))
    assert result["deny"] is True
    assert result["deny_reason"] == "ACTION_NOT_PERMITTED"


def test_deny_amount_exceeds_limit():
    inp = _base_input()
    inp["payload"]["amount_usd"] = 5000
    result = evaluate_policy(inp)
    assert result["deny"] is True
    assert result["deny_reason"] == "AMOUNT_EXCEEDS_LIMIT"


def test_step_up_amount_exceeds_threshold():
    inp = _base_input()
    inp["payload"]["amount_usd"] = 750  # Above 500 step-up threshold, below 1000 limit
    result = evaluate_policy(inp)
    assert result["step_up"] is True
    assert result["allow"] is False


def test_deny_agent_not_found():
    result = evaluate_policy(_base_input(agent=None))
    assert result["deny"] is True
    assert result["deny_reason"] == "AGENT_NOT_FOUND"

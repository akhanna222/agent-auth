"""Built-in policy engine (replaces OPA for standalone mode)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..schemas.api.delegations import GrantedScopes


def evaluate_policy(input_data: dict) -> dict:
    """
    Evaluate KYA policy rules (Python implementation of OPA main.rego).
    Returns dict with keys: allow, deny, step_up, deny_reason.
    """
    agent = input_data.get("agent")
    delegation = input_data.get("delegation")
    token = input_data.get("token")
    action = input_data.get("action")
    payload = input_data.get("payload", {})
    payload_hash = input_data.get("payload_hash")
    revocations = input_data.get("revocations", {})
    context = input_data.get("context", {})
    current_time = input_data.get("current_time", datetime.now(timezone.utc).isoformat() + "Z")

    # Identity check
    if not agent:
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "AGENT_NOT_FOUND"}
    if revocations.get("agent_revoked"):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "AGENT_REVOKED"}
    if agent.get("status") != "active":
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "AGENT_INVALID_STATUS"}
    if agent.get("environment") != context.get("environment", "development"):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "AGENT_ENV_MISMATCH"}

    # Delegation check
    if not delegation:
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "DELEGATION_NOT_FOUND"}
    if revocations.get("delegation_revoked"):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "DELEGATION_REVOKED"}
    if delegation.get("status") != "active":
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "DELEGATION_REVOKED"}

    scopes = delegation.get("granted_scopes", {})
    if action not in scopes.get("allowed_actions", []):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "ACTION_NOT_PERMITTED"}
    if action in scopes.get("denied_actions", []):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "ACTION_EXPLICITLY_DENIED"}

    expires_at = delegation.get("expires_at", "")
    if current_time >= str(expires_at):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "DELEGATION_EXPIRED"}

    # Token check
    if not token:
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_NOT_FOUND"}
    if revocations.get("token_revoked"):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_REVOKED"}
    if token.get("status") == "used":
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_ALREADY_USED"}
    if token.get("status") == "revoked":
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_REVOKED"}
    if token.get("action") != action:
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "ACTION_NOT_PERMITTED"}

    token_expires = token.get("expires_at", "")
    if current_time >= str(token_expires):
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_EXPIRED"}

    if payload_hash and token.get("action_hash") and token["action_hash"] != payload_hash:
        return {"allow": False, "deny": True, "step_up": False, "deny_reason": "TOKEN_PAYLOAD_MISMATCH"}

    # Constraint checks
    amount = payload.get("amount_usd")
    max_amount = scopes.get("max_amount_usd")
    if amount is not None and max_amount is not None:
        if float(amount) > float(max_amount):
            return {"allow": False, "deny": True, "step_up": False, "deny_reason": "AMOUNT_EXCEEDS_LIMIT"}

    # Time window check
    time_window = scopes.get("time_window")
    if time_window:
        day = context.get("day_of_week", "")
        hour = context.get("hour_utc", 0)
        if day not in time_window.get("days", []):
            return {"allow": False, "deny": True, "step_up": False, "deny_reason": "OUTSIDE_TIME_WINDOW"}
        if hour < time_window.get("hours_utc_start", 0) or hour >= time_window.get("hours_utc_end", 24):
            return {"allow": False, "deny": True, "step_up": False, "deny_reason": "OUTSIDE_TIME_WINDOW"}

    # Step-up trigger
    step_up_threshold = scopes.get("require_step_up_above_usd")
    if amount is not None and step_up_threshold is not None:
        if float(amount) > float(step_up_threshold):
            return {"allow": False, "deny": False, "step_up": True, "deny_reason": None}

    return {"allow": True, "deny": False, "step_up": False, "deny_reason": None}

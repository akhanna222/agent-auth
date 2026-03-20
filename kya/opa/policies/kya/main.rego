package kya.main

import future.keywords.if
import future.keywords.in

# ── Identity Check ────────────────────────────────────────────────────────────
agent_valid if {
    input.agent.status == "active"
    not input.revocations.agent_revoked
    input.agent.environment == input.context.environment
    input.agent.trust_tier != "revoked"
}

# ── Delegation Check ──────────────────────────────────────────────────────────
delegation_valid if {
    input.delegation.status == "active"
    not input.revocations.delegation_revoked
    input.action in input.delegation.granted_scopes.allowed_actions
    not input.action in input.delegation.granted_scopes.denied_actions
    input.current_time < input.delegation.expires_at
}

# ── Token Check ───────────────────────────────────────────────────────────────
token_valid if {
    input.token.status == "unused"
    not input.revocations.token_revoked
    input.token.action == input.action
    input.current_time < input.token.expires_at
    input.token.use_count < input.token.max_uses
    input.token.action_hash == input.payload_hash
}

# ── Constraint Checks ─────────────────────────────────────────────────────────
constraints_satisfied if {
    not input.payload.amount_usd
}

constraints_satisfied if {
    input.payload.amount_usd
    input.payload.amount_usd <= input.delegation.granted_scopes.max_amount_usd
}

# ── Time Window Check ─────────────────────────────────────────────────────────
within_time_window if {
    not input.delegation.granted_scopes.time_window
}

within_time_window if {
    input.delegation.granted_scopes.time_window
    input.context.day_of_week in input.delegation.granted_scopes.time_window.days
    input.context.hour_utc >= input.delegation.granted_scopes.time_window.hours_utc_start
    input.context.hour_utc < input.delegation.granted_scopes.time_window.hours_utc_end
}

# ── Step-Up Trigger ───────────────────────────────────────────────────────────
requires_step_up if {
    input.payload.amount_usd
    threshold := input.delegation.granted_scopes.require_step_up_above_usd
    input.payload.amount_usd > threshold
}

# ── Final Decisions ───────────────────────────────────────────────────────────
default allow   = false
default step_up = false
default deny    = false

allow if {
    agent_valid
    delegation_valid
    token_valid
    constraints_satisfied
    within_time_window
    not requires_step_up
}

step_up if {
    agent_valid
    delegation_valid
    token_valid
    constraints_satisfied
    within_time_window
    requires_step_up
}

deny if {
    not allow
    not step_up
}

# ── Deny Reason ───────────────────────────────────────────────────────────────
deny_reason := "AGENT_NOT_FOUND"          if { not input.agent }
deny_reason := "AGENT_REVOKED"            if { input.revocations.agent_revoked }
deny_reason := "AGENT_INVALID_STATUS"     if { input.agent.status != "active" }
deny_reason := "AGENT_ENV_MISMATCH"       if { input.agent.environment != input.context.environment }
deny_reason := "DELEGATION_REVOKED"       if { input.revocations.delegation_revoked }
deny_reason := "DELEGATION_EXPIRED"       if { input.current_time >= input.delegation.expires_at }
deny_reason := "ACTION_NOT_PERMITTED"     if {
    not input.action in input.delegation.granted_scopes.allowed_actions
}
deny_reason := "ACTION_EXPLICITLY_DENIED" if {
    input.action in input.delegation.granted_scopes.denied_actions
}
deny_reason := "TOKEN_ALREADY_USED"       if { input.token.status == "used" }
deny_reason := "TOKEN_REVOKED"            if { input.revocations.token_revoked }
deny_reason := "TOKEN_EXPIRED"            if { input.current_time >= input.token.expires_at }
deny_reason := "TOKEN_PAYLOAD_MISMATCH"   if { input.token.action_hash != input.payload_hash }
deny_reason := "AMOUNT_EXCEEDS_LIMIT"     if {
    input.payload.amount_usd > input.delegation.granted_scopes.max_amount_usd
}
deny_reason := "OUTSIDE_TIME_WINDOW"      if { not within_time_window }

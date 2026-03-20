# KYA × Mastercard MPGS
## Integration Guide — Sandbox Edition

> **Version:** 1.0  
> **Audience:** Mastercard MPGS Engineering  
> **Time to first working call:** < 5 minutes

---

## What KYA Does for MPGS

KYA (Know Your Agent) is a trust verification layer that sits between an AI agent and MPGS. Before MPGS processes any agent-initiated payment, it makes one HTTP call to KYA. KYA responds in under 100ms with a clear decision: **allow**, **deny**, or **step_up**.

```
AI Agent  →  MPGS receives payment request
                    ↓
             POST /v1/verify-agent-action  →  KYA
                    ↓
             { decision: "allow" | "deny" | "step_up" }
                    ↓
             MPGS proceeds / blocks / challenges
```

KYA verifies three things on every call:

1. **Agent identity** — is this a registered, active, non-revoked agent?
2. **Delegation** — did a verified human authorise this agent to make payments?
3. **Intent** — does this specific action match a signed, single-use, unexpired mandate?

If any check fails, KYA returns `deny` with a machine-readable reason code. MPGS blocks the transaction. No human review needed.

---

## Sandbox Credentials

Use these for all test calls. No signup required.

```
Base URL:      https://sandbox.kya.moofwd.io/v1
Tenant:        mastercard-sandbox
API Key:       kya_sandbox_mc_test_4f8a2b1c9d
Header:        X-Tenant-ID: mastercard-sandbox
               Authorization: Bearer kya_sandbox_mc_test_4f8a2b1c9d
```

---

## Pre-seeded Test Agents

| Agent ID | Name | Status | Notes |
|---|---|---|---|
| `agt_mc_test_001` | InvoicePaymentAgent | active · verified | Normal payment agent |
| `agt_mc_test_002` | CardholderAssistant | active · verified | Low limit ($500) |
| `agt_mc_test_003` | FraudReviewAgent | active · certified | Highest trust tier |
| `agt_mc_test_revoked` | RevokedAgent | revoked | For testing deny flows |

---

## The One Endpoint MPGS Needs

### `POST /v1/verify-agent-action`

This is the only endpoint MPGS needs to call. Everything else (agent registration, delegation management, intent tokens) is handled by the agent operator side.

#### Request

```http
POST /v1/verify-agent-action HTTP/1.1
Host: sandbox.kya.moofwd.io
Content-Type: application/json
X-Tenant-ID: mastercard-sandbox
Authorization: Bearer kya_sandbox_mc_test_4f8a2b1c9d
X-Request-ID: req_mpgs_001

{
  "agent_id": "agt_mc_test_001",
  "signed_token": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJwYXltZW50LmNyZWF0ZSIsImFtb3VudCI6MTIwMH0.sandbox_sig",
  "action": "payment.create",
  "action_payload": {
    "amount_usd": 1200,
    "currency": "USD",
    "merchant_id": "MCH_TEST_001",
    "invoice_ref": "INV-SANDBOX-001"
  },
  "request_context": {
    "ip_address": "203.0.113.1",
    "user_agent": "MPGS-Gateway/4.1",
    "timestamp": "2025-01-07T14:00:00Z"
  }
}
```

#### Response — Allow

```json
{
  "data": {
    "is_agent_valid": true,
    "is_authorized": true,
    "risk_score": 7,
    "decision": "allow",
    "decision_id": "dec_sandbox_abc123",
    "constraints_verified": {
      "amount_within_limit": true,
      "delegation_active": true,
      "token_valid": true,
      "time_window_valid": true
    },
    "processed_at": "2025-01-07T14:00:00.067Z"
  },
  "meta": {
    "request_id": "req_mpgs_001",
    "latency_ms": 67,
    "version": "1.0"
  }
}
```

**MPGS action:** Proceed with payment authorization.

#### Response — Deny

```json
{
  "data": {
    "is_agent_valid": false,
    "is_authorized": false,
    "risk_score": 100,
    "decision": "deny",
    "decision_id": "dec_sandbox_def456",
    "denial_reason": "AGENT_REVOKED"
  }
}
```

**MPGS action:** Block the transaction. Return decline to the agent.

#### Response — Step-Up

```json
{
  "data": {
    "is_agent_valid": true,
    "is_authorized": false,
    "risk_score": 18,
    "decision": "step_up",
    "decision_id": "dec_sandbox_ghi789",
    "challenge_id": "chal_sandbox_xyz",
    "challenge_type": "push_notification",
    "poll_url": "https://sandbox.kya.moofwd.io/v1/stepup/chal_sandbox_xyz/status",
    "expires_at": "2025-01-07T14:05:00Z"
  }
}
```

**MPGS action:** Hold the transaction. Poll `poll_url` every 3 seconds. Resume when status = `approved`. Cancel if `rejected` or `expired`.

---

## Test Scenarios

Use these pre-issued signed tokens to test every decision path without any setup.

| Scenario | agent_id | signed_token | amount | Expected decision |
|---|---|---|---|---|
| Normal allow | `agt_mc_test_001` | `tok_mc_allow_sandbox` | $1,200 | `allow` · risk ~7 |
| Step-up triggered | `agt_mc_test_001` | `tok_mc_stepup_sandbox` | $7,500 | `step_up` |
| Amount over limit | `agt_mc_test_002` | `tok_mc_overlimit_sandbox` | $800 | `deny` · `AMOUNT_EXCEEDS_LIMIT` |
| Revoked agent | `agt_mc_test_revoked` | any | any | `deny` · `AGENT_REVOKED` |
| Replayed token | `agt_mc_test_001` | `tok_mc_used_sandbox` | $500 | `deny` · `TOKEN_ALREADY_USED` |
| Outside hours | `agt_mc_test_001` | `tok_mc_weekend_sandbox` | $1,000 | `deny` · `OUTSIDE_TIME_WINDOW` |

> All sandbox tokens listed in the Postman collection — pre-configured and ready to send.

---

## MPGS Integration Pseudocode

Drop this logic into the MPGS pre-authorization hook:

```python
import httpx

KYA_BASE_URL = "https://sandbox.kya.moofwd.io/v1"
KYA_API_KEY  = "kya_sandbox_mc_test_4f8a2b1c9d"
KYA_TENANT   = "mastercard-sandbox"

async def kya_verify(agent_id: str, signed_token: str,
                     action: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.post(
            f"{KYA_BASE_URL}/verify-agent-action",
            headers={
                "X-Tenant-ID":    KYA_TENANT,
                "Authorization":  f"Bearer {KYA_API_KEY}",
                "X-Request-ID":   generate_uuid(),
                "Content-Type":   "application/json",
            },
            json={
                "agent_id":       agent_id,
                "signed_token":   signed_token,
                "action":         action,
                "action_payload": payload,
                "request_context": {
                    "ip_address": get_client_ip(),
                    "user_agent": "MPGS-Gateway/4.1",
                    "timestamp":  utc_now(),
                }
            }
        )
    return response.json()["data"]


async def mpgs_pre_auth_hook(payment_request):
    """
    Call this hook before processing any agent-initiated payment.
    For human-initiated payments, KYA is bypassed entirely.
    """

    # Only apply KYA to agent-initiated payments
    if not payment_request.is_agent_initiated:
        return proceed(payment_request)

    kya_result = await kya_verify(
        agent_id=     payment_request.agent_id,
        signed_token= payment_request.kya_token,
        action=       "payment.create",
        payload={
            "amount_usd":   payment_request.amount,
            "currency":     payment_request.currency,
            "merchant_id":  payment_request.merchant_id,
        }
    )

    if kya_result["decision"] == "allow":
        return proceed(payment_request)

    elif kya_result["decision"] == "step_up":
        return hold_for_step_up(
            payment_request,
            challenge_id= kya_result["challenge_id"],
            poll_url=     kya_result["poll_url"],
            expires_at=   kya_result["expires_at"],
        )

    else:  # deny
        return decline(
            payment_request,
            reason=       kya_result["denial_reason"],
            decision_id=  kya_result["decision_id"],
        )
```

---

## Step-Up Polling Flow

When KYA returns `step_up`, MPGS holds the transaction and polls for human resolution:

```python
async def poll_step_up(poll_url: str, timeout_seconds: int = 300) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        await asyncio.sleep(3)
        response = await client.get(poll_url, headers=KYA_HEADERS)
        status = response.json()["data"]["status"]
        if status == "approved":
            return "approved"
        if status in ("rejected", "expired"):
            return status
    return "timeout"
```

---

## Denial Reason Codes

| Code | Meaning | MPGS Action |
|---|---|---|
| `AGENT_REVOKED` | Agent identity revoked | Hard decline |
| `AGENT_NOT_FOUND` | Unknown agent_id | Hard decline |
| `DELEGATION_REVOKED` | Human revoked agent's authority | Hard decline |
| `DELEGATION_EXPIRED` | Delegation TTL expired | Hard decline |
| `TOKEN_ALREADY_USED` | Replay attempt | Hard decline + flag |
| `TOKEN_EXPIRED` | Intent token TTL expired | Soft decline — agent should re-issue |
| `TOKEN_PAYLOAD_MISMATCH` | Payload tampered in transit | Hard decline + alert |
| `AMOUNT_EXCEEDS_LIMIT` | Amount over delegation ceiling | Hard decline |
| `ACTION_NOT_PERMITTED` | Action not in agent's scope | Hard decline |
| `OUTSIDE_TIME_WINDOW` | Request outside allowed hours | Soft decline |
| `RISK_SCORE_TOO_HIGH` | Anomaly detected | Hard decline + review queue |

---

## Failure Mode — What If KYA Is Unreachable?

KYA targets 99.99% uptime. In the event of unreachability, the recommended MPGS posture is:

```
Timeout < 200ms:     Retry once, then apply fallback
Fallback — Option A: Deny all agent payments (safest — recommended for launch)
Fallback — Option B: Allow with risk flag in transaction metadata (higher throughput)
Fallback — Option C: Route to human review queue (balanced)
```

Discuss with Moofwd which fallback posture matches Mastercard's risk appetite before going live.

---

## What KYA Does Not Change

- KYA does **not** modify the payment authorization flow
- KYA does **not** see card numbers, CVVs, or account details
- KYA does **not** store payment amounts beyond the audit log
- KYA does **not** replace 3DS — it complements it for agent-initiated flows
- Human-initiated payments are **completely unaffected** — zero integration overhead

---

## Next Steps

| Step | Owner | Timeline |
|---|---|---|
| Run sandbox Postman collection | Mastercard engineering | Day 1 |
| Review denial reason handling | Mastercard + Moofwd | Day 2 |
| Define fallback posture | Mastercard risk team | Day 3 |
| Agree step-up channel (push / SMS / TOTP) | Joint | Week 1 |
| Production tenant provisioning | Moofwd | Week 2 |
| MPGS staging integration | Mastercard engineering | Week 3 |
| Joint pen test / security review | Both | Week 4 |

---

**Contact:** Abhishek (Abi) Tiwari, AI Lead, Moofwd  
**Sandbox support:** sandbox-support@moofwd.io  
**SLA:** 99.99% uptime · < 100ms p99 · 24/7 incident response

---
*KYA × MPGS Integration Guide v1.0 — Sandbox Edition*

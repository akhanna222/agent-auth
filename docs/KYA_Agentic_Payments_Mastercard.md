# KYA × Mastercard MPGS — Agentic Payments

> How AI agents make payments safely through Mastercard's Payment Gateway Services

---

## The Problem

AI agents are becoming capable enough to handle real financial transactions — paying invoices, processing refunds, managing subscriptions. But payment networks like Mastercard have no way to answer a fundamental question:

**"Is this AI agent actually authorized to spend this person's money right now?"**

Traditional authentication (passwords, 3DS, biometrics) assumes a human is present. When an agent acts autonomously, those controls don't apply. Without a trust layer, payment processors face a choice between blocking all agent payments (killing innovation) or allowing them unchecked (creating fraud risk).

KYA eliminates that tradeoff.

---

## The Solution

KYA sits between the AI agent and MPGS as a real-time trust verification layer. MPGS makes one API call before processing any agent-initiated payment. KYA responds in under 100ms with a clear decision.

```
                                    ┌─────────────────┐
                                    │   Human Owner    │
                                    │  (Cardholder)    │
                                    └────────┬────────┘
                                             │ Delegates authority
                                             ▼
┌──────────────┐    payment     ┌─────────────────┐    verify    ┌───────────┐
│   AI Agent   │───request────▶│      MPGS        │────────────▶│    KYA    │
│ (Claude, GPT,│               │  Payment Gateway │◀────────────│  Platform │
│  custom)     │◀──result──────│                  │  allow/deny  │           │
└──────────────┘               └─────────────────┘   /step_up   └───────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │   Card Network   │
                               │   (Mastercard)   │
                               └─────────────────┘
```

### What happens on every agent payment:

1. An AI agent submits a payment request to MPGS
2. MPGS calls `POST /v1/verify-agent-action` on KYA
3. KYA checks **identity** (is this agent real?), **delegation** (did the human authorize this?), **intent** (does this match a signed mandate?), **policy** (is it within limits?), and **risk** (is this anomalous?)
4. KYA returns `allow`, `deny`, or `step_up` with a machine-readable reason
5. MPGS proceeds, blocks, or holds the payment accordingly
6. The decision is logged in a tamper-evident audit chain

**Human-initiated payments are completely unaffected.** KYA only activates for agent-initiated flows.

---

## Real-World Scenarios

### Scenario 1: Invoice Payment Agent

A company deploys an AI agent to pay approved invoices automatically.

```
Human (CFO):
  "Pay invoices under $10,000 from verified vendors during business hours.
   Anything over $5,000 needs my approval."

                    ┌─────────────────────────────────────┐
                    │         KYA Delegation               │
                    │                                      │
                    │  allowed_actions: [payment.create]   │
                    │  max_amount_usd: 10,000              │
                    │  step_up_above_usd: 5,000            │
                    │  time_window: Mon-Fri, 6am-10pm UTC  │
                    │  expires: 90 days                    │
                    └─────────────────────────────────────┘
```

| Invoice | Amount | Day | KYA Decision | What Happens |
|---|---|---|---|---|
| INV-001 | $2,400 | Tuesday 2pm | **allow** | Payment processes instantly |
| INV-002 | $7,500 | Wednesday 10am | **step_up** | CFO gets push notification, approves, payment proceeds |
| INV-003 | $15,000 | Thursday 3pm | **deny** (AMOUNT_EXCEEDS_LIMIT) | Payment blocked, agent notified |
| INV-004 | $3,000 | Saturday 1pm | **deny** (OUTSIDE_TIME_WINDOW) | Payment blocked until Monday |

### Scenario 2: Cardholder Assistant

A bank offers an AI assistant that helps cardholders make purchases via chat.

```
Cardholder:
  "Help me buy things, but keep it under $500 per transaction."

                    ┌─────────────────────────────────────┐
                    │         KYA Delegation               │
                    │                                      │
                    │  allowed_actions: [payment.create]   │
                    │  max_amount_usd: 500                 │
                    │  step_up_above_usd: 300              │
                    └─────────────────────────────────────┘
```

The assistant can instantly process purchases up to $300. Purchases between $300-$500 trigger a quick confirmation. Anything over $500 is blocked entirely — even if the agent is compromised, damage is capped.

### Scenario 3: Agent-to-Agent Delegation (Orchestrator Pattern)

A payment orchestrator agent delegates to specialized sub-agents:

```
┌──────────────────────┐
│  Human (Treasurer)   │
│  max: $50,000        │
└──────────┬───────────┘
           │ delegates
           ▼
┌──────────────────────┐
│  Orchestrator Agent  │
│  max: $50,000        │──────────────────┐
└──────────┬───────────┘                  │
           │ sub-delegates                │ sub-delegates
           ▼                              ▼
┌──────────────────────┐    ┌──────────────────────┐
│  Invoice Agent       │    │  Payroll Agent        │
│  max: $10,000        │    │  max: $25,000         │
│  actions: payment.*  │    │  actions: payment.*   │
└──────────────────────┘    └──────────────────────┘
```

KYA enforces **scope contraction** — each child agent can only receive permissions that are a subset of its parent. The Invoice Agent can never spend more than $10,000 even if it tries, because KYA validates the full delegation chain on every transaction.

### Scenario 4: Fraud Review Agent

A certified fraud review agent with elevated trust can process high-value refunds:

```
Agent: FraudReviewAgent (trust_tier: certified)
Action: payment.refund
Amount: $45,000

KYA checks:
  ✓ Agent identity: active, certified tier
  ✓ Delegation: active, refund permitted, $50K limit
  ✓ Intent token: valid, unused, action hash matches
  ✓ Risk score: 0 (certified agent = lowest risk)
  → Decision: allow
```

Trust tiers (`unverified` → `verified` → `certified`) let MPGS differentiate between agents that have passed different levels of vetting.

---

## How MPGS Integrates

### The One Endpoint

MPGS only needs to call one endpoint. Everything else (registration, delegation, tokens) is handled by the agent operator.

```
POST /v1/verify-agent-action
```

### Integration in the Pre-Authorization Hook

```python
async def mpgs_pre_auth_hook(payment_request):
    # Only apply KYA to agent-initiated payments
    if not payment_request.is_agent_initiated:
        return proceed(payment_request)  # humans pass through unchanged

    result = await kya_client.post("/v1/verify-agent-action", json={
        "agent_id":       payment_request.agent_id,
        "signed_token":   payment_request.kya_token,
        "action":         "payment.create",
        "action_payload": {
            "amount_usd":  payment_request.amount,
            "currency":    payment_request.currency,
            "merchant_id": payment_request.merchant_id,
        },
        "request_context": {
            "ip_address":  request.client_ip,
        }
    })

    decision = result["data"]["decision"]

    if decision == "allow":
        return proceed(payment_request)

    elif decision == "step_up":
        return hold_and_poll(
            payment_request,
            poll_url=result["data"]["poll_url"],
            expires_at=result["data"]["expires_at"],
        )

    else:  # deny
        return decline(
            payment_request,
            reason=result["data"]["denial_reason"],
        )
```

### Response Format

Every response follows a consistent envelope:

```json
{
  "data": {
    "is_agent_valid": true,
    "is_authorized": true,
    "risk_score": 7,
    "decision": "allow",
    "decision_id": "dec_abc123",
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

---

## Denial Reason Codes

When KYA denies a payment, it returns a machine-readable reason code so MPGS can take the right action:

| Code | What It Means | MPGS Action |
|---|---|---|
| `AGENT_NOT_FOUND` | Unknown agent ID | Hard decline |
| `AGENT_REVOKED` | Agent's identity has been revoked | Hard decline |
| `AGENT_ENV_MISMATCH` | Agent environment doesn't match | Hard decline |
| `DELEGATION_REVOKED` | Human revoked the agent's authority | Hard decline |
| `DELEGATION_EXPIRED` | Delegation TTL has expired | Hard decline |
| `TOKEN_ALREADY_USED` | Replay attack — token was already consumed | Hard decline + flag |
| `TOKEN_EXPIRED` | Intent token has expired | Soft decline (agent re-issues) |
| `TOKEN_PAYLOAD_MISMATCH` | Payload was tampered in transit | Hard decline + alert |
| `AMOUNT_EXCEEDS_LIMIT` | Amount exceeds delegation ceiling | Hard decline |
| `ACTION_NOT_PERMITTED` | Action not in agent's allowed scope | Hard decline |
| `ACTION_EXPLICITLY_DENIED` | Action is in the deny list | Hard decline |
| `OUTSIDE_TIME_WINDOW` | Request outside allowed hours/days | Soft decline |
| `RISK_SCORE_TOO_HIGH` | Behavioral anomaly detected | Hard decline + review |

---

## Step-Up Authentication Flow

When a payment exceeds the step-up threshold but is within the absolute limit, KYA returns `step_up` instead of `deny`. This triggers human confirmation without blocking the entire flow.

```
Agent requests $7,500 payment
        │
        ▼
   KYA evaluates:
   ✓ Within $10,000 limit
   ✗ Exceeds $5,000 step-up threshold
        │
        ▼
   Returns: step_up + challenge_id
        │
        ├──────────────────────────────┐
        ▼                              ▼
   MPGS holds payment            Human receives
   Polls /v1/stepup/{id}/status  push notification
        │                              │
        │         ┌────────────────────┘
        │         ▼
        │    Human approves
        │         │
        ▼         ▼
   Status = approved → KYA issues upgraded token
        │
        ▼
   MPGS resumes payment with upgraded token
```

The step-up challenge expires after 5 minutes. If the human rejects or doesn't respond, MPGS cancels the transaction.

---

## Risk Scoring

Every verification includes a real-time risk score (0-100) based on six behavioral signals:

| Signal | Weight | What It Detects |
|---|---|---|
| **Velocity** | 25 pts | Unusual burst of transactions |
| **Payload deviation** | 20 pts | Amount/parameters far from agent's norm |
| **Action novelty** | 20 pts | Agent performing unfamiliar actions |
| **Time anomaly** | 15 pts | Activity at unusual hours |
| **Agent age** | 10 pts | Newly registered agents (higher risk) |
| **Trust tier** | 10 pts | Unverified agents score higher |

| Score Range | Outcome |
|---|---|
| 0 – 50 | Policy decision stands (allow/deny) |
| 51 – 75 | Escalate to step-up regardless of policy |
| 76 – 100 | Auto-deny regardless of policy |

A certified agent making a normal payment during business hours might score **0**. A new unverified agent making its first large transaction at 3am would score **65+**, triggering step-up even if the policy would normally allow it.

---

## Security Guarantees

| Property | How KYA Ensures It |
|---|---|
| **Agent can't forge identity** | Ed25519 cryptographic keypair — private key held only by agent |
| **Agent can't exceed permissions** | Delegation scopes checked on every request |
| **Agent can't replay transactions** | Single-use JWT tokens consumed on first use |
| **Agent can't tamper with payloads** | SHA-256 action hash in JWT — payload mismatch = deny |
| **Child agent can't exceed parent** | Scope contraction enforced at delegation creation |
| **Revocation is instant** | Cache-first propagation, sub-millisecond |
| **Audit trail can't be tampered** | SHA-256 hash chain — any modification breaks the chain |
| **KYA can't see card data** | KYA only sees amount, action, and agent identity — never card numbers or CVVs |

---

## What KYA Does NOT Change

- **Human-initiated payments** are completely unaffected — zero overhead
- KYA does **not** replace 3DS or SCA — it complements them for agent flows
- KYA does **not** touch card numbers, CVVs, or account details
- KYA does **not** modify the MPGS authorization flow — it's a pre-auth check
- KYA does **not** store payment amounts beyond the audit log entry

---

## Sandbox: Try It Now

The sandbox comes pre-loaded with test agents and tokens. No signup required.

### Credentials

```
API Key:    kya_sandbox_mc_test_4f8a2b1c9d
Tenant:     mastercard-sandbox
Header:     Authorization: Bearer kya_sandbox_mc_test_4f8a2b1c9d
```

### Test Agents

| Agent | Role | Limit | Trust |
|---|---|---|---|
| `agt_mc_test_001` | InvoicePaymentAgent | $10,000 | verified |
| `agt_mc_test_002` | CardholderAssistant | $500 | verified |
| `agt_mc_test_003` | FraudReviewAgent | $50,000 | certified |
| `agt_mc_test_revoked` | RevokedAgent | — | revoked |

### Test Tokens (Ready to Send)

| Token | Scenario | Expected |
|---|---|---|
| `tok_mc_allow_sandbox` | Normal $1,200 payment | **allow** |
| `tok_mc_stepup_sandbox` | $7,500 exceeds step-up threshold | **step_up** |
| `tok_mc_overlimit_sandbox` | $800 exceeds $500 agent limit | **deny** — AMOUNT_EXCEEDS_LIMIT |
| `tok_mc_used_sandbox` | Already consumed token | **deny** — TOKEN_ALREADY_USED |
| `tok_mc_weekend_sandbox` | Weekend payment (outside hours) | **deny** — OUTSIDE_TIME_WINDOW |
| `tok_mc_refund_sandbox` | Refund action | **allow** |
| `tok_mc_fraud_allow_sandbox` | Certified agent fraud review | **allow** |

### Quick Test (curl)

```bash
curl -X POST http://localhost:8000/v1/verify-agent-action \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: mastercard-sandbox" \
  -H "Authorization: Bearer kya_sandbox_mc_test_4f8a2b1c9d" \
  -d '{
    "agent_id": "agt_mc_test_001",
    "signed_token": "tok_mc_allow_sandbox",
    "action": "payment.create",
    "action_payload": {"amount_usd": 1200, "currency": "USD"},
    "request_context": {"ip_address": "203.0.113.1"}
  }'
```

Expected response: `"decision": "allow"`

---

## Failure Modes

| Situation | Recommended MPGS Posture |
|---|---|
| KYA responds normally | Use the decision |
| KYA timeout (>200ms) | Retry once, then apply fallback |
| KYA unreachable | **Option A:** Deny all agent payments (safest) |
| | **Option B:** Allow with risk flag in metadata |
| | **Option C:** Route to human review queue |

KYA targets 99.99% uptime and <100ms p99 latency.

---

## Production Rollout Path

| Phase | What | Timeline |
|---|---|---|
| **1. Sandbox** | Run Postman collection, validate all 7 test scenarios | Day 1-2 |
| **2. Decision mapping** | Map KYA denial codes to MPGS decline codes | Day 3-5 |
| **3. Fallback policy** | Agree on behavior when KYA is unreachable | Week 1 |
| **4. Step-up channel** | Choose push / SMS / TOTP for human confirmations | Week 1 |
| **5. Staging** | Integrate with MPGS staging environment | Week 2-3 |
| **6. Security review** | Joint penetration test and audit | Week 3-4 |
| **7. Shadow mode** | Run KYA in parallel (log decisions, don't enforce) | Week 5-6 |
| **8. Production** | Enable enforcement for agent-initiated payments | Week 7+ |

---

*KYA × Mastercard MPGS — Agentic Payments v1.0*

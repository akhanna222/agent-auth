# KYA — Know Your Agent

An authentication and authorization platform for AI agents. KYA provides cryptographic identity, scoped delegation, intent tokens, policy evaluation, risk scoring, and tamper-evident audit logging — everything needed to let AI agents act on behalf of humans safely.

## Why KYA?

AI agents increasingly need to perform real actions: process payments, send messages, access data. KYA answers the question: **"Should this agent be allowed to do this, right now, on behalf of this user?"**

### Use Cases

- **Payment processing** — An agent requests to pay an invoice. KYA verifies delegation scope, checks amount limits, evaluates risk, and either allows, denies, or triggers step-up authentication.
- **Agent-to-agent delegation** — A parent agent delegates a subset of its permissions to a child agent, with automatic scope contraction (child can never exceed parent).
- **Compliance & audit** — Every authorization decision is logged in a hash-chained, tamper-evident audit trail that can be independently verified.
- **Multi-tenant SaaS** — Each tenant gets isolated agents, delegations, and audit logs with per-endpoint rate limiting.

## UI Preview

KYA ships with a built-in dark-themed dashboard at `/ui` — no separate frontend needed.

### Dashboard — System Overview & Audit Trail
![KYA Dashboard](docs/images/kya-dashboard.svg)

### Agent Management — Registration & Inventory
![KYA Agents](docs/images/kya-agents.svg)

### Verification — Real-Time Action Authorization
![KYA Verify](docs/images/kya-verify.svg)

> **8 pages total:** Dashboard, Agents, Delegations, Intent Tokens, Verify Action, Revocation, Step-Up, Audit Log. Access at `http://localhost:8000/ui` after starting the server.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Agent / App │────▶│  KYA API     │────▶│  Policy Engine │
│              │◀────│  (FastAPI)   │◀────│  (OPA / Python)│
└─────────────┘     └──────┬───────┘     └───────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Database │ │  Cache   │ │  Audit   │
        │ (PG/SQL) │ │ (Redis)  │ │  Log     │
        └──────────┘ └──────────┘ └──────────┘
```

**Authorization flow:**

1. **Register** — Agent gets an Ed25519 keypair and identity
2. **Delegate** — Human grants scoped permissions to the agent
3. **Issue token** — Agent requests a single-use intent token for a specific action
4. **Verify** — Service calls `/v1/verify-agent-action` with the token; KYA evaluates policy + risk and returns allow / deny / step_up
5. **Audit** — Decision is recorded in hash-chained log

### Core Components

| Component | Purpose |
|---|---|
| **Identity Service** | Ed25519 keypair generation, agent registration |
| **Delegation Service** | Human→agent and agent→agent permission scoping |
| **Intent Service** | Single-use JWT tokens bound to specific actions |
| **Policy Engine** | Python port of OPA Rego rules — 12+ deny reasons |
| **Risk Engine** | 6-signal weighted scoring (velocity, payload deviation, time anomaly, etc.) |
| **Revocation Service** | Cache-first revocation with cascade (agent → delegations → tokens) |
| **Step-Up Service** | Challenge/response for high-risk actions |
| **Audit Service** | Hash-chained append-only log with chain verification |

## Delegation Flows

KYA supports two delegation models that feed into the same verification pipeline.

### Human → Agent

A human grants scoped permissions to an agent:

```bash
POST /v1/delegations
```
```json
{
  "agent_id": "agt_001",
  "granted_scopes": {
    "allowed_actions": ["payment.create"],
    "max_amount_usd": 1000,
    "require_step_up_above_usd": 500
  },
  "expires_in_seconds": 3600
}
```

The agent can then request intent tokens and act within those scopes. If the action exceeds `require_step_up_above_usd`, a step-up challenge is sent back to the human for approval.

### Agent → Agent

A parent agent delegates a subset of its permissions to a child agent:

```bash
POST /v1/delegations/agent-to-agent
```
```json
{
  "parent_agent_id": "agt_001",
  "child_agent_id": "agt_002",
  "scopes": {
    "allowed_actions": ["payment.create"],
    "max_amount_usd": 500
  },
  "expires_in_seconds": 1800
}
```

### Delegation Safeguards

| Rule | Enforcement |
|---|---|
| **Scope contraction** | Child scopes must be a subset of parent — child can never exceed parent |
| **Depth limit** | Max 3 levels of delegation chain (DB constraint) |
| **Self-delegation blocked** | `parent_agent_id != child_agent_id` (DB constraint) |
| **Cascade revocation** | Revoking a parent cascades to all child delegations and tokens |
| **Amount ceiling** | Child `max_amount_usd` must be ≤ parent `max_amount_usd` |

Both paths converge at `/v1/verify-agent-action` — the policy engine checks the full delegation chain regardless of whether the original grant came from a human or another agent.

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Install & Run

```bash
cd kya
pip install -e ".[dev]"
python -m kya.main
```

The server starts at `http://localhost:8000`. A built-in UI is available at `/ui`.

> **Standalone mode**: By default, KYA runs with SQLite and an in-memory cache — no Postgres or Redis needed for development.

### Run Tests

```bash
cd kya
pytest tests/ -v
```

33 tests across unit and integration suites covering crypto, policy, services, and API endpoints.

### Production Setup (Docker)

```bash
cd kya
docker compose up -d
```

Starts Postgres 15, Redis 7, OPA, and the KYA API. Set environment variables to configure:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./kya.db` | Database connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis URL (set empty for in-memory) |
| `ENVIRONMENT` | `development` | `development` / `sandbox` / `production` |
| `USE_INMEMORY_CACHE` | `true` | Use in-memory cache instead of Redis |
| `USE_BUILTIN_POLICY` | `true` | Use Python policy engine instead of OPA |

## API Reference

All endpoints require `X-Tenant-ID` header (or `Authorization: Bearer <api-key>` for sandbox).

### Agents

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/agents/register` | Register a new agent (returns Ed25519 keypair) |
| `GET` | `/v1/agents` | List agents for tenant |
| `GET` | `/v1/agents/{agent_id}` | Get agent details |

### Delegations

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/delegations` | Create human→agent delegation |
| `POST` | `/v1/delegations/agent-to-agent` | Create agent→agent delegation |
| `POST` | `/v1/delegations/pre-auth` | Create pre-authorized mandate |
| `GET` | `/v1/delegations` | List delegations |
| `GET` | `/v1/delegations/{id}` | Get delegation details |

### Intent Tokens

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/intent/issue` | Issue a single-use intent token |

### Verification

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/verify-agent-action` | Verify an agent's action (core endpoint) |

### Revocation

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/revoke/agent/{id}` | Revoke agent + cascade |
| `POST` | `/v1/revoke/delegation/{id}` | Revoke delegation + tokens |
| `POST` | `/v1/revoke/token/{id}` | Revoke single token |

### Step-Up Authentication

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/stepup/challenge` | Create step-up challenge |
| `POST` | `/v1/stepup/{id}/approve` | Approve challenge (issues upgraded token) |
| `POST` | `/v1/stepup/{id}/reject` | Reject challenge |

### Audit

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/audit/events` | Query audit events |
| `GET` | `/v1/audit/agent/{id}/timeline` | Agent-specific timeline |
| `GET` | `/v1/audit/verify-chain` | Verify audit chain integrity |
| `GET` | `/v1/audit/decisions` | Query by decision type |

## Mastercard MPGS — Agentic Payments

KYA integrates with Mastercard Payment Gateway Services to authorize AI agent-initiated payments in real time. See the full guide:

**[KYA × Mastercard MPGS — Agentic Payments](docs/KYA_Agentic_Payments_Mastercard.md)**

Covers real-world scenarios (invoice payments, cardholder assistants, agent-to-agent orchestration), the MPGS pre-auth integration, step-up flow, risk scoring, denial codes, and a production rollout plan.

## Sandbox / MPGS Integration

KYA includes a Mastercard Payment Gateway Services (MPGS) sandbox with pre-seeded test data.

### Sandbox API Key

```
Authorization: Bearer kya_sandbox_mc_test_4f8a2b1c9d
```

### Pre-seeded Test Agents

| Agent ID | Name | Capabilities |
|---|---|---|
| `agt_mc_test_001` | InvoicePaymentAgent | payment.create, payment.refund |
| `agt_mc_test_002` | CardholderAssistant | payment.create ($500 limit) |
| `agt_mc_test_003` | FraudReviewAgent | payment.review (certified tier) |
| `agt_mc_test_revoked` | RevokedTestAgent | payment.create (revoked) |

### Test Tokens

| Token | Expected Result |
|---|---|
| `tok_mc_allow_sandbox` | Allow — $100 payment |
| `tok_mc_stepup_sandbox` | Step-up — $600 exceeds step-up threshold |
| `tok_mc_overlimit_sandbox` | Deny — $1500 exceeds $1000 limit |
| `tok_mc_used_sandbox` | Deny — already consumed |
| `tok_mc_weekend_sandbox` | Deny — outside time window |
| `tok_mc_refund_sandbox` | Allow — refund action |
| `tok_mc_fraud_allow_sandbox` | Allow — fraud review (certified agent) |

## Project Structure

```
kya/
├── src/kya/
│   ├── main.py                 # FastAPI app setup
│   ├── config.py               # Pydantic settings
│   ├── database.py             # Async SQLAlchemy with tenant RLS
│   ├── middleware.py            # Request ID, tenant resolution, rate limiting
│   ├── sandbox.py              # MPGS sandbox data & helpers
│   ├── redis_client.py         # InMemoryCache / Redis abstraction
│   ├── dependencies.py         # Platform keypair management
│   ├── models/db/              # SQLAlchemy ORM models
│   ├── schemas/api/            # Pydantic request/response schemas
│   ├── routers/                # FastAPI route handlers
│   ├── services/               # Business logic layer
│   │   ├── identity.py         #   Agent registration
│   │   ├── delegation.py       #   Delegation management
│   │   ├── intent.py           #   Intent token issuance
│   │   ├── policy.py           #   Policy evaluation (OPA port)
│   │   ├── risk.py             #   Risk scoring
│   │   ├── verification.py     #   Orchestration layer
│   │   ├── revocation.py       #   Revocation with cascade
│   │   ├── stepup.py           #   Step-up challenges
│   │   └── audit.py            #   Hash-chained audit log
│   ├── utils/crypto.py         # Ed25519, JWT, SHA-256 utilities
│   └── templates/index.html    # Built-in dashboard UI
├── opa/policies/               # OPA Rego policies (for Docker deployment)
├── tests/
│   ├── unit/                   # 28 unit tests
│   └── integration/            # 5 integration tests
├── docker-compose.yml          # Postgres, Redis, OPA, API
└── pyproject.toml              # Dependencies & build config
```

## Security Model

- **Ed25519/EdDSA** cryptographic identity for every agent
- **Single-use JWT intent tokens** with action hash binding (payload hash, not raw payload in JWT)
- **Scope contraction** enforced on agent-to-agent delegation (child ⊆ parent)
- **Delegation depth limit** of 3 levels (DB constraint)
- **Cache-first revocation** for sub-millisecond propagation
- **Hash-chained audit log** with SHA-256 chain verification
- **Row-level security** via tenant context in database sessions
- **Rate limiting** per tenant per endpoint

## Response Format

All API responses follow the MPGS-compatible envelope:

```json
{
  "data": { ... },
  "meta": {
    "request_id": "uuid",
    "latency_ms": 12.3,
    "version": "0.1.0"
  }
}
```

## License

See repository root for license information.

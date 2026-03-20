# KYA — Know Your Agent
## Complete Engineering Build Specification
### Claude Code Step-by-Step Implementation Guide

> **Version:** 1.0 — MVP Build  
> **Audience:** Claude Code / Engineers  
> **Structure:** 5 Phases, sequential — complete each phase fully before starting the next

---

## HOW TO USE THIS DOCUMENT

This is not a conceptual document. Every section contains actionable schema, API contracts, logic rules, and acceptance criteria. Follow these rules:

1. Read the **entire section** before writing any code for that phase
2. Follow acceptance criteria exactly — they are your definition of done
3. **Never skip ahead.** Every phase has hard dependencies on the previous
4. When a block is marked `⚠️ CRITICAL` — implement it exactly as specified, no shortcuts
5. Tests are **not optional**. Every component has a required test list
6. When in doubt about a design decision — **stop and ask** before building

---

## TECHNOLOGY STACK (Fixed — Do Not Deviate)

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.12 | Type safety, async support |
| API Framework | FastAPI | Native async, OpenAPI auto-docs, Pydantic v2 |
| Database | PostgreSQL 15 | JSONB, row-level security, reliability |
| Cache / Pub-Sub | Redis 7 | Sub-millisecond revocation, hot cache |
| Policy Engine | Open Policy Agent (OPA) | Declarative rules, independently testable |
| Auth | JWT (EdDSA / Ed25519) + OAuth2 | Industry standard, stateless |
| Key Management | File-based (dev) / AWS KMS interface (prod) | Pluggable KMS abstraction |
| Migrations | Alembic | Version-controlled schema |
| Testing | pytest + httpx (async) | Full async test support |
| Containerisation | Docker + Docker Compose | Local/prod parity |
| Queue (Phase 4+) | Redis Streams | Lightweight, no extra infra for MVP |

---

## REPOSITORY STRUCTURE

Set up this exact structure before writing any application code:

```
kya/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── alembic.ini
├── alembic/
│   └── versions/
├── opa/
│   └── policies/
│       └── kya/
│           └── main.rego
├── src/
│   └── kya/
│       ├── __init__.py
│       ├── main.py                  # FastAPI app entry point
│       ├── config.py                # Settings via pydantic-settings
│       ├── database.py              # Async SQLAlchemy engine
│       ├── redis_client.py          # Redis connection pool
│       ├── dependencies.py          # FastAPI dependency injection
│       ├── middleware.py            # Tenant resolution, request ID
│       ├── services/
│       │   ├── identity.py
│       │   ├── delegation.py
│       │   ├── intent.py
│       │   ├── policy.py
│       │   ├── verification.py
│       │   ├── audit.py
│       │   ├── revocation.py
│       │   ├── stepup.py
│       │   └── risk.py
│       ├── models/
│       │   └── db/                  # SQLAlchemy ORM models
│       ├── schemas/
│       │   └── api/                 # Pydantic request/response schemas
│       ├── routers/
│       │   ├── agents.py
│       │   ├── delegations.py
│       │   ├── intent.py
│       │   ├── verify.py
│       │   ├── revoke.py
│       │   ├── stepup.py
│       │   └── audit.py
│       └── utils/
│           ├── crypto.py            # Key generation, JWT signing/verifying
│           ├── hashing.py           # SHA-256, HMAC utilities
│           └── time.py              # UTC helpers
└── tests/
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## DOCKER COMPOSE (Start Here)

Create `docker-compose.yml` before anything else. All development runs through this.

```yaml
version: "3.9"
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: kya_dev
      POSTGRES_USER: kya_app
      POSTGRES_PASSWORD: kya_secret
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  opa:
    image: openpolicyagent/opa:latest
    command: run --server --addr :8181 /policies
    volumes:
      - ./opa/policies:/policies
    ports:
      - "8181:8181"

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://kya_app:kya_secret@db:5432/kya_dev
      REDIS_URL: redis://redis:6379
      OPA_URL: http://opa:8181
    depends_on:
      - db
      - redis
      - opa

volumes:
  postgres_data:
```

---

---

# PHASE 1 — Foundation (Weeks 1–2)

**Goal:** Working repo, database, auth middleware, tenant isolation, and a running API with one endpoint.

**Acceptance gate:** All Phase 1 tests pass. Docker Compose brings the full stack up cleanly. A `POST /v1/agents/register` call succeeds end-to-end.

---

## 1.1 — Project Bootstrap

### pyproject.toml dependencies

```toml
[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.111"
uvicorn = {extras = ["standard"], version = "^0.29"}
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.29"
alembic = "^1.13"
pydantic = "^2.7"
pydantic-settings = "^2.2"
redis = {extras = ["asyncio"], version = "^5.0"}
python-jose = {extras = ["cryptography"], version = "^3.3"}
cryptography = "^42.0"
httpx = "^0.27"
structlog = "^24.1"

[tool.poetry.dev-dependencies]
pytest = "^8.1"
pytest-asyncio = "^0.23"
pytest-cov = "^5.0"
```

### config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    OPA_URL: str = "http://localhost:8181"
    JWT_PRIVATE_KEY_PATH: str = "./keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str  = "./keys/public.pem"
    JWT_ALGORITHM: str = "EdDSA"
    JWT_ISSUER: str = "kya-platform"
    JWT_EXPIRY_SECONDS: int = 3600
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 1.2 — Database Migrations

Run all migrations **in order**. Never modify an applied migration. Create a new migration for any change.

### Migration 001 — Tenants

```sql
CREATE TABLE tenants (
    tenant_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'starter',
    status      TEXT NOT NULL DEFAULT 'active',
    config      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
```

### Migration 002 — Agents

```sql
CREATE TABLE agents (
    agent_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    display_name    TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model_version   TEXT,
    capabilities    JSONB NOT NULL DEFAULT '[]',
    public_key      TEXT NOT NULL,
    trust_tier      TEXT NOT NULL DEFAULT 'unverified',
    status          TEXT NOT NULL DEFAULT 'active',
    owner_entity_id UUID NOT NULL,
    owner_type      TEXT NOT NULL,
    environment     TEXT NOT NULL DEFAULT 'sandbox',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_agents_tenant     ON agents(tenant_id);
CREATE INDEX idx_agents_status     ON agents(tenant_id, status);
CREATE INDEX idx_agents_owner      ON agents(owner_entity_id, owner_type);
```

### Migration 003 — Delegations

```sql
CREATE TABLE delegations (
    delegation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_id        UUID NOT NULL REFERENCES agents(agent_id),
    principal_id    UUID NOT NULL,
    principal_type  TEXT NOT NULL,
    idp_subject     TEXT NOT NULL,
    delegation_type TEXT NOT NULL DEFAULT 'interactive',
    granted_scopes  JSONB NOT NULL,
    constraints     JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active',
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    revoked_by      UUID,
    session_context JSONB DEFAULT '{}',
    CONSTRAINT delegation_expiry_valid CHECK (expires_at > issued_at)
);

CREATE INDEX idx_delegations_agent     ON delegations(agent_id, status);
CREATE INDEX idx_delegations_principal ON delegations(principal_id, status);
CREATE INDEX idx_delegations_tenant    ON delegations(tenant_id);
```

### Migration 004 — Agent-to-Agent Delegations

```sql
-- ⚠️ CRITICAL: This table enables multi-agent orchestration.
-- A sub-agent NEVER gets more permissions than its parent.

CREATE TABLE agent_delegations (
    agent_delegation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(tenant_id),
    parent_agent_id      UUID NOT NULL REFERENCES agents(agent_id),
    child_agent_id       UUID NOT NULL REFERENCES agents(agent_id),
    parent_delegation_id UUID NOT NULL REFERENCES delegations(delegation_id),
    inherited_scopes     JSONB NOT NULL,
    depth                INTEGER NOT NULL DEFAULT 1,
    status               TEXT NOT NULL DEFAULT 'active',
    issued_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ NOT NULL,
    CONSTRAINT depth_limit       CHECK (depth <= 3),
    CONSTRAINT no_self_delegation CHECK (parent_agent_id != child_agent_id)
);
```

### Migration 005 — Intent Tokens

```sql
CREATE TABLE intent_tokens (
    token_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    jti             TEXT UNIQUE NOT NULL,
    agent_id        UUID NOT NULL REFERENCES agents(agent_id),
    principal_id    UUID NOT NULL,
    delegation_id   UUID NOT NULL REFERENCES delegations(delegation_id),
    token_mode      TEXT NOT NULL DEFAULT 'single_use',
    action          TEXT NOT NULL,
    action_payload  JSONB NOT NULL,
    constraints     JSONB NOT NULL DEFAULT '{}',
    signed_token    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'unused',
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    use_count       INTEGER NOT NULL DEFAULT 0,
    max_uses        INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT token_use_limit CHECK (use_count <= max_uses)
);

CREATE INDEX idx_intent_tokens_agent  ON intent_tokens(agent_id, status);
CREATE INDEX idx_intent_tokens_jti    ON intent_tokens(jti);
CREATE INDEX idx_intent_tokens_tenant ON intent_tokens(tenant_id);
```

### Migration 006 — Audit Log

```sql
-- ⚠️ CRITICAL: This table is append-only. The app role must NEVER
-- have UPDATE or DELETE privileges on this table.

CREATE TABLE audit_log (
    log_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL,
    sequence_num  BIGSERIAL,
    event_type    TEXT NOT NULL,
    agent_id      UUID,
    principal_id  UUID,
    token_id      UUID,
    delegation_id UUID,
    action        TEXT,
    decision      TEXT,
    risk_score    NUMERIC(5,2),
    denial_reason TEXT,
    request_hash  TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash    TEXT NOT NULL,
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

REVOKE UPDATE, DELETE ON audit_log FROM kya_app;
CREATE INDEX idx_audit_tenant_seq ON audit_log(tenant_id, sequence_num);
CREATE INDEX idx_audit_agent      ON audit_log(agent_id, created_at);
```

### Migration 007 — Step-Up Challenges

```sql
CREATE TABLE stepup_challenges (
    challenge_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL,
    agent_id       UUID NOT NULL REFERENCES agents(agent_id),
    token_id       UUID NOT NULL REFERENCES intent_tokens(token_id),
    principal_id   UUID NOT NULL,
    channel        TEXT NOT NULL DEFAULT 'push',
    status         TEXT NOT NULL DEFAULT 'pending',
    challenge_hash TEXT NOT NULL,
    callback_url   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ NOT NULL,
    resolved_at    TIMESTAMPTZ
);

CREATE INDEX idx_stepup_token   ON stepup_challenges(token_id, status);
CREATE INDEX idx_stepup_pending ON stepup_challenges(principal_id, status)
    WHERE status = 'pending';
```

---

## 1.3 — Middleware

### Tenant Resolution Middleware

Every request must resolve a tenant before hitting any route handler. Implement this as FastAPI middleware.

```
Request comes in
  → Extract X-Tenant-ID header (or subdomain)
  → Look up tenant in Redis cache (key: kya:tenant:{slug})
  → On cache miss: query Postgres, cache for 300s
  → If tenant not found or status != 'active': return 403
  → Attach tenant object to request.state.tenant
  → All subsequent DB queries MUST include tenant_id filter
```

### Request ID Middleware

```
Every request:
  → Read X-Request-ID header, or generate UUID if absent
  → Attach to request.state.request_id
  → Include in all log lines for this request
  → Return in response header X-Request-ID
```

### JWT Auth Dependency

```python
# dependencies.py
# This is a FastAPI dependency injected into every protected route.
# It must:
#   1. Extract Bearer token from Authorization header
#   2. Verify signature using KYA public key
#   3. Validate: exp, iss, aud claims
#   4. Extract tenant_id and verify it matches request.state.tenant.tenant_id
#   5. Return decoded claims as CurrentUser object
#   6. Raise HTTP 401 on any failure — never 500
```

---

## 1.4 — Identity Service

### Agent Registration Flow

```
POST /v1/agents/register
  1. Validate request body (Pydantic)
  2. Check: capability names must be in allowed format "domain.action"
  3. Check: if environment=production, trust_tier must be >= 'verified'
     (unverified agents cannot be registered in production)
  4. Generate Ed25519 keypair
  5. Insert agent row with public_key stored as PEM
  6. Write audit log: event_type = 'agent.registered'
  7. Return agent_id, public_key, private_key
     ⚠️ private_key is returned ONCE and ONLY ONCE. KYA does not store it.
```

### Request Schema

```python
class AgentRegisterRequest(BaseModel):
    display_name: str
    provider: str                          # 'openai' | 'anthropic' | 'custom'
    model_version: str | None = None
    capabilities: list[str]                # ['payment.create', 'email.send']
    owner_entity_id: UUID
    owner_type: Literal["user", "org"]
    environment: Literal["sandbox", "production"] = "sandbox"
    metadata: dict = {}

    @validator('capabilities')
    def validate_capability_format(cls, v):
        # Each capability must match pattern: ^[a-z_]+\.[a-z_]+$
        # Examples: payment.create, email.send, calendar.write
        pass
```

### Response Schema

```python
class AgentRegisterResponse(BaseModel):
    agent_id: UUID
    public_key: str           # PEM format
    private_key: str          # PEM format — ONLY returned at registration
    trust_tier: str
    status: str
    created_at: datetime
```

---

## 1.5 — Phase 1 Acceptance Criteria

- [ ] `docker compose up` starts Postgres, Redis, OPA, and API with no errors
- [ ] All 7 migrations apply cleanly via `alembic upgrade head`
- [ ] `POST /v1/agents/register` returns 201 with agent_id and keypair
- [ ] Tenant middleware rejects requests with invalid or missing tenant header (403)
- [ ] JWT middleware rejects requests with invalid or expired token (401)
- [ ] Audit log row is created for every agent registration
- [ ] Private key is NOT stored in database (verify with direct SQL query)
- [ ] All capability strings are validated against `domain.action` pattern
- [ ] Unverified agents are rejected for `environment: production`

### Phase 1 Required Tests

```
tests/unit/test_crypto.py
  - test_generate_ed25519_keypair
  - test_jwt_sign_and_verify
  - test_jwt_rejects_expired_token
  - test_jwt_rejects_wrong_key

tests/unit/test_identity_service.py
  - test_register_agent_success
  - test_register_agent_invalid_capability_format
  - test_register_production_agent_requires_verified_tier

tests/integration/test_agents_router.py
  - test_register_agent_end_to_end
  - test_register_agent_missing_tenant_header
  - test_register_agent_invalid_jwt
  - test_register_agent_capability_format_rejected
```

---

---

# PHASE 2 — Delegation & Intent (Weeks 3–4)

**Goal:** Full delegation model including human→agent and agent→agent. Intent token creation. Pre-auth mandate for autonomous agents.

**Acceptance gate:** A complete delegation chain exists in the database. An intent token can be issued and its JWT signature verified. Pre-auth flow creates a mandate that an autonomous agent can draw tokens against.

---

## 2.1 — Delegation Service

### Human → Agent Delegation

```
POST /v1/delegations
  1. Validate request body
  2. Extract principal_id from JWT claims (NOT from request body)
  3. Verify agent exists, is active, belongs to same tenant
  4. Verify all actions in granted_scopes.allowed_actions exist
     in agent.capabilities — you cannot delegate what the agent cannot do
  5. Create delegation row
  6. Cache delegation in Redis: kya:delegation:{delegation_id} TTL=60s
  7. Write audit log: event_type = 'delegation.created'
  8. Return delegation_id and full scope summary
```

### Scope Validation Rule

```
⚠️ CRITICAL RULE — Scope Contraction:
When creating an agent-to-agent delegation, the child's inherited_scopes
MUST be a strict subset of the parent delegation's granted_scopes.

Pseudocode:
  child_actions = set(inherited_scopes.allowed_actions)
  parent_actions = set(parent_delegation.granted_scopes.allowed_actions)
  
  if not child_actions.issubset(parent_actions):
      raise ValidationError("Child scope exceeds parent scope")
  
  if inherited_scopes.max_amount_usd > parent_delegation.granted_scopes.max_amount_usd:
      raise ValidationError("Child amount limit exceeds parent limit")

This check runs in DelegationService, NOT in OPA.
OPA trusts that the delegation stored in the DB is already valid.
```

### Delegation Request Schema

```python
class DelegationCreateRequest(BaseModel):
    agent_id: UUID
    delegation_type: Literal["interactive", "autonomous", "pre_auth"] = "interactive"
    granted_scopes: GrantedScopes
    expires_in_seconds: int = Field(ge=300, le=7776000)  # 5min to 90 days
    session_context: dict = {}

class GrantedScopes(BaseModel):
    allowed_actions: list[str]
    denied_actions: list[str] = []
    allowed_domains: list[str] = []
    max_amount_usd: float | None = None
    require_step_up_above_usd: float | None = None
    rate_limit: RateLimit | None = None
    time_window: TimeWindow | None = None

class TimeWindow(BaseModel):
    days: list[Literal["mon","tue","wed","thu","fri","sat","sun"]]
    hours_utc_start: int    # 0-23
    hours_utc_end: int      # 0-23
```

### Agent-to-Agent Delegation

```
POST /v1/delegations/agent-to-agent
  1. Authenticate: caller must be the parent agent (JWT signed by agent's private key)
  2. Fetch parent_delegation — must be active
  3. Validate: inherited_scopes is strict subset of parent_delegation.granted_scopes
  4. Validate: depth = parent's depth + 1; must be <= 3
  5. Validate: child expires_at <= parent expires_at (child cannot outlive parent)
  6. Create agent_delegations row
  7. Write audit log: event_type = 'agent_delegation.created'
```

### Pre-Auth Mandate (Autonomous Agents)

```
POST /v1/delegations/pre-auth
  Purpose: Human signs a batch mandate once. The agent creates individual
           intent tokens against this mandate without human being present.

  1. Validate request body
  2. Extract principal_id from JWT (human must be authenticated)
  3. Create delegation row with delegation_type = 'pre_auth'
  4. Sign the mandate payload with KYA's platform key
  5. Return signed mandate_token (JWT)
  6. Write audit log: event_type = 'pre_auth.created'

Pre-auth mandate JWT payload:
{
  "iss": "kya-platform",
  "sub": "{principal_id}",
  "jti": "{mandate_id}",
  "delegation_id": "{delegation_id}",
  "workflow_description": "...",
  "allowed_actions": [...],
  "constraints": {...},
  "exp": ...,
  "iat": ...
}
```

---

## 2.2 — Intent Token Service

### Intent Token Issuance

```
POST /v1/intent/issue
  1. Validate request body
  2. Verify delegation_id exists, is active, belongs to requesting principal
  3. Verify action is in delegation.granted_scopes.allowed_actions
  4. Verify action_payload constraints against delegation constraints
     - amount_usd <= max_amount_usd (if present)
  5. Generate JWT with the following payload:
     {
       "iss": "kya-platform",
       "sub": "{principal_id}",
       "jti": "{unique_jti}",
       "agent_id": "{agent_id}",
       "delegation_id": "{delegation_id}",
       "action": "{action}",
       "action_hash": sha256(json(action_payload)),
       "constraints": {...},
       "exp": now + expires_in_seconds,
       "iat": now
     }
  6. Sign JWT with KYA platform Ed25519 private key
  7. Insert intent_tokens row with signed_token
  8. Write audit log: event_type = 'token.issued'
  9. Return token_id, signed_token, expires_at

⚠️ CRITICAL: The action_payload is NOT embedded in the JWT directly.
Only its SHA-256 hash is included. The full payload is stored in Postgres.
This prevents token inflation and allows payload verification without
trusting the token carrier.
```

### Issue Token from Pre-Auth (Autonomous Flow)

```
POST /v1/intent/issue-from-pre-auth
  Caller: the agent itself (JWT signed by agent's private key)

  1. Verify agent JWT (signed by agent's private key)
  2. Verify mandate_token signature (KYA platform key)
  3. Verify mandate is not expired
  4. Verify requested action is in mandate's allowed_actions
  5. Verify action_payload constraints against mandate constraints
  6. Check running totals: has pre-auth budget been exhausted?
     SELECT SUM(action_payload->>'amount_usd') FROM intent_tokens
     WHERE delegation_id = {pre_auth_delegation_id}
     AND status IN ('unused', 'used')
  7. If within budget: issue token (same flow as above)
  8. Write audit log: event_type = 'token.issued_autonomous'
```

---

## 2.3 — Crypto Utilities

Implement in `utils/crypto.py`:

```python
# Key generation
def generate_ed25519_keypair() -> tuple[str, str]:
    """Returns (public_key_pem, private_key_pem)"""

# JWT operations
def sign_jwt(payload: dict, private_key_pem: str) -> str:
    """Sign using EdDSA. Always include iat, exp, jti, iss."""

def verify_jwt(token: str, public_key_pem: str) -> dict:
    """Verify signature, expiry, issuer. Raise on any failure."""

def hash_payload(payload: dict) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)"""

def compute_entry_hash(entry: dict, previous_hash: str) -> str:
    """SHA-256(json(entry) + previous_hash) — for audit chain"""
```

---

## 2.4 — Phase 2 Acceptance Criteria

- [ ] `POST /v1/delegations` creates delegation scoped to authenticated principal
- [ ] Agent-to-agent delegation is rejected if child scope exceeds parent scope
- [ ] Agent-to-agent delegation is rejected if depth > 3
- [ ] `POST /v1/intent/issue` creates signed JWT token
- [ ] Token JWT contains action_hash (not raw payload)
- [ ] `POST /v1/delegations/pre-auth` creates autonomous mandate
- [ ] Autonomous agent can issue tokens against pre-auth mandate
- [ ] Pre-auth spend tracking prevents over-budget token issuance
- [ ] All delegation events logged to audit_log

### Phase 2 Required Tests

```
tests/unit/test_delegation_service.py
  - test_create_delegation_success
  - test_delegation_rejects_action_not_in_capabilities
  - test_agent_delegation_scope_contraction_enforced
  - test_agent_delegation_depth_limit_enforced
  - test_pre_auth_mandate_creation

tests/unit/test_intent_service.py
  - test_issue_token_success
  - test_token_payload_hash_not_raw_payload
  - test_issue_token_amount_exceeds_delegation_limit
  - test_autonomous_token_issuance_from_pre_auth
  - test_autonomous_token_rejected_when_budget_exhausted

tests/unit/test_crypto.py
  - test_ed25519_sign_and_verify
  - test_payload_hash_canonical
  - test_audit_chain_hash
```

---

---

# PHASE 3 — Policy Engine & Verification API (Weeks 5–6)

**Goal:** Full OPA policy evaluation. External-facing `/verify-agent-action` endpoint. Risk scoring. The system can now make real allow/deny/step_up decisions.

**Acceptance gate:** A full verification request is processed end-to-end in under 100ms (p99 local). OPA policies are independently testable. Risk score changes based on agent history.

---

## 3.1 — OPA Policy

Create at `opa/policies/kya/main.rego`:

```rego
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
    input.token.action_hash == input.payload_hash   # payload integrity check
}

# ── Constraint Checks ─────────────────────────────────────────────────────────
constraints_satisfied if {
    not input.payload.amount_usd    # no amount = always pass
}

constraints_satisfied if {
    input.payload.amount_usd
    input.payload.amount_usd <= input.delegation.granted_scopes.max_amount_usd
}

# ── Time Window Check ─────────────────────────────────────────────────────────
within_time_window if {
    not input.delegation.granted_scopes.time_window  # no window = always pass
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

# ── Deny Reason (first matching rule wins) ────────────────────────────────────
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
```

---

## 3.2 — Policy Engine Service

This is the orchestration layer. It hydrates data, calls OPA, and acts on results.

```python
# services/policy.py

class PolicyEngine:

    async def evaluate(self, request: VerificationRequest) -> PolicyDecision:

        # STEP 1: Parallel hydration (hit Redis first, fallback to Postgres)
        agent, delegation, token, revocations = await asyncio.gather(
            self.fetch_agent(request.agent_id),
            self.fetch_delegation_from_token(request.signed_token),
            self.fetch_and_validate_token(request.signed_token),
            self.check_all_revocations(request),
        )

        # STEP 2: Compute payload hash (to verify token integrity)
        payload_hash = hash_payload(request.action_payload)

        # STEP 3: Build OPA input bundle
        opa_input = {
            "agent":        agent.model_dump() if agent else None,
            "delegation":   delegation.model_dump() if delegation else None,
            "token":        token.model_dump() if token else None,
            "action":       request.action,
            "payload":      request.action_payload,
            "payload_hash": payload_hash,
            "revocations":  revocations,
            "context": {
                "ip_address":    request.request_context.ip_address,
                "environment":   self.settings.ENVIRONMENT,
                "day_of_week":   datetime.utcnow().strftime("%a").lower(),
                "hour_utc":      datetime.utcnow().hour,
            },
            "current_time": datetime.utcnow().isoformat() + "Z",
        }

        # STEP 4: Evaluate OPA policy
        opa_result = await self.opa_client.post(
            "/v1/data/kya/main",
            json={"input": opa_input}
        )
        result = opa_result.json()["result"]

        # STEP 5: Compute risk score
        risk_score = await self.risk_engine.score(
            request=request,
            agent=agent,
            opa_result=result,
        )

        # STEP 6: Apply risk override
        # Even if OPA says 'allow', risk score can escalate to step_up or deny
        final_decision = self.apply_risk_override(result, risk_score, delegation)

        # STEP 7: Consume token if allowed
        if final_decision.outcome == "allow" and token:
            await self.token_service.consume(token.token_id)

        # STEP 8: Write audit log — ALWAYS, regardless of decision
        await self.audit_service.log(
            event_type=f"action.{final_decision.outcome}",
            request=request,
            decision=final_decision,
            risk_score=risk_score,
        )

        return final_decision
```

---

## 3.3 — Risk Scoring Engine

```python
# services/risk.py

RISK_SIGNALS = [
    ("velocity_anomaly", 25),   # requests this hour vs 7-day avg. >3x = max score
    ("payload_deviation", 20),  # amount vs agent historical avg. >5x = max score
    ("action_novelty", 20),     # first time this action type seen for agent
    ("time_anomaly", 15),       # outside declared time_window in delegation
    ("agent_age", 10),          # agent registered < 24hrs ago
    ("trust_tier", 10),         # unverified=10, verified=5, certified=0
]

# Risk thresholds — configurable per tenant via tenant.config JSONB
DEFAULT_THRESHOLDS = {
    "auto_allow":  30,   # score <= 30: OPA decision stands
    "step_up":     60,   # 31-60: escalate to step_up even if OPA said allow
    "auto_deny":   61,   # score > 60: deny even if OPA said allow
}

class RiskEngine:
    async def score(self, request, agent, opa_result) -> float:
        signals = await asyncio.gather(
            self.velocity_signal(agent.agent_id),
            self.payload_deviation_signal(agent.agent_id, request.action_payload),
            self.action_novelty_signal(agent.agent_id, request.action),
            self.time_anomaly_signal(request, agent),
            self.agent_age_signal(agent),
            self.trust_tier_signal(agent),
        )
        # Weighted sum, normalised to 0-100
        return min(100.0, sum(signals))

    async def velocity_signal(self, agent_id: UUID) -> float:
        # Count actions in last 1hr from audit_log
        # Compare to rolling 7-day hourly average
        # >3x average = full 25 points; linear interpolation below
        pass

    async def action_novelty_signal(self, agent_id: UUID, action: str) -> float:
        # Check if this action type appears in audit_log for this agent
        # First time seen = 20 points; seen before = 0
        pass
```

---

## 3.4 — Verification API Endpoint

```python
# routers/verify.py

@router.post("/v1/verify-agent-action")
async def verify_agent_action(
    request: VerifyRequest,
    http_request: Request,
    policy_engine: PolicyEngine = Depends(),
) -> VerifyResponse:
    """
    External-facing. No JWT auth required from caller.
    The agent's identity is proven by the signed_token itself.
    
    ⚠️ CRITICAL: This endpoint must complete in < 100ms p99.
    All DB reads must hit Redis cache first.
    """
    decision = await policy_engine.evaluate(
        VerificationRequest(
            agent_id=request.agent_id,
            signed_token=request.signed_token,
            action=request.action,
            action_payload=request.action_payload,
            request_context=request.request_context,
        )
    )
    return VerifyResponse(
        is_agent_valid=decision.is_agent_valid,
        is_authorized=decision.outcome == "allow",
        risk_score=decision.risk_score,
        decision=decision.outcome,
        decision_id=decision.decision_id,
        denial_reason=decision.denial_reason,
        processed_at=datetime.utcnow(),
    )
```

### Verification Request/Response Schemas

```python
class VerifyRequest(BaseModel):
    agent_id: UUID
    signed_token: str                   # Full JWT intent token
    action: str
    action_payload: dict
    request_context: RequestContext

class RequestContext(BaseModel):
    ip_address: str
    user_agent: str | None = None
    timestamp: datetime

class VerifyResponse(BaseModel):
    is_agent_valid: bool
    is_authorized: bool
    risk_score: float
    decision: Literal["allow", "deny", "step_up"]
    decision_id: UUID
    denial_reason: str | None = None
    challenge_id: UUID | None = None    # populated when decision = step_up
    poll_url: str | None = None         # populated when decision = step_up
    processed_at: datetime
```

---

## 3.5 — Redis Caching Strategy

```python
# Every cache read follows this pattern: cache-aside

async def fetch_agent(self, agent_id: UUID) -> Agent | None:
    cache_key = f"kya:agent:cache:{agent_id}"
    
    # Try cache first
    cached = await redis.get(cache_key)
    if cached:
        return Agent.model_validate_json(cached)
    
    # Cache miss — hit Postgres
    agent = await db.get(Agent, agent_id)
    if agent:
        await redis.setex(cache_key, 60, agent.model_dump_json())
    return agent

# Revocation checks bypass cache entirely — always check Redis revocation keys
async def check_all_revocations(self, request) -> dict:
    agent_revoked     = await redis.exists(f"kya:revoked:agent:{request.agent_id}")
    delegation_id     = self.extract_delegation_id_from_token(request.signed_token)
    deleg_revoked     = await redis.exists(f"kya:revoked:delegation:{delegation_id}")
    jti               = self.extract_jti_from_token(request.signed_token)
    token_revoked     = await redis.exists(f"kya:revoked:token:{jti}")
    return {
        "agent_revoked":      bool(agent_revoked),
        "delegation_revoked": bool(deleg_revoked),
        "token_revoked":      bool(token_revoked),
    }
```

---

## 3.6 — Phase 3 Acceptance Criteria

- [ ] `POST /v1/verify-agent-action` returns allow for a valid request
- [ ] Returns deny with correct `denial_reason` for each failure mode (test all 12 deny reasons)
- [ ] Returns step_up when amount exceeds `require_step_up_above_usd`
- [ ] Token is marked `used` in DB after a successful allow
- [ ] Replayed token (used token submitted again) returns `TOKEN_ALREADY_USED`
- [ ] Risk score changes between a new agent (high) and established agent (low)
- [ ] p99 latency on local Docker stack < 100ms (run 1000 requests, measure)
- [ ] OPA policies pass all unit tests independently (use `opa test`)
- [ ] Audit log has entry for every verify call (allow AND deny AND step_up)

### Phase 3 Required Tests

```
tests/unit/test_policy_engine.py
  - test_allow_happy_path
  - test_deny_revoked_agent
  - test_deny_revoked_delegation
  - test_deny_replayed_token
  - test_deny_token_payload_mismatch
  - test_deny_action_not_permitted
  - test_deny_amount_exceeds_limit
  - test_deny_outside_time_window
  - test_step_up_amount_exceeds_threshold
  - test_risk_override_escalates_to_step_up

tests/unit/test_risk_engine.py
  - test_new_agent_gets_high_score
  - test_established_agent_gets_low_score
  - test_velocity_spike_raises_score
  - test_action_novelty_raises_score

opa/tests/test_main.rego
  - (OPA native tests for every policy rule)

tests/integration/test_verify_endpoint.py
  - test_full_verification_allow
  - test_full_verification_deny_revoked
  - test_full_verification_step_up
  - test_latency_under_100ms (1000 iterations)
```

---

---

# PHASE 4 — Revocation & Step-Up (Week 7)

**Goal:** Instant revocation propagation. Step-up challenge/response flow with polling and webhook support.

**Acceptance gate:** An agent revocation propagates in < 5ms. A step-up challenge can be initiated, polled, and resolved. Resolved step-up produces an upgraded token.

---

## 4.1 — Revocation Service

```
⚠️ CRITICAL DESIGN RULE:
Revocation writes to Redis FIRST, then Postgres.
Redis write is synchronous and completes in <1ms.
Postgres write is async (fire-and-forget after Redis confirms).
This ensures sub-millisecond propagation to all verify nodes.
```

### Revocation Cascade Rules

```
Revoking an AGENT cascades to:
  → All active delegations for this agent (status = 'revoked')
  → All unused intent tokens for those delegations (status = 'revoked')
  → Redis keys for all of the above (set permanently)

Revoking a DELEGATION cascades to:
  → All unused intent tokens under this delegation
  → Redis key for delegation (set permanently)
  → Child agent-delegations (if agent-to-agent)

Revoking a TOKEN:
  → Redis key for jti (set with TTL = token's original expires_at)
  → No cascade
```

### Implementation

```python
# services/revocation.py

class RevocationService:

    async def revoke_agent(self, agent_id: UUID, reason: str) -> None:
        # 1. Write to Redis immediately (synchronous)
        await redis.set(f"kya:revoked:agent:{agent_id}", reason)
        
        # 2. Invalidate agent cache
        await redis.delete(f"kya:agent:cache:{agent_id}")
        
        # 3. Find all active delegations for this agent
        delegations = await db.query(
            "SELECT delegation_id FROM delegations "
            "WHERE agent_id = %s AND status = 'active'", [agent_id]
        )
        
        # 4. Cascade to delegations and tokens via Redis Streams
        for d in delegations:
            await self.revoke_delegation(d.delegation_id, reason, cascade_from_agent=True)
        
        # 5. Async DB update (via Redis Stream worker)
        await self.queue_db_update("agent", agent_id, "revoked", reason)
        
        # 6. Audit log
        await audit.log(event_type="agent.revoked", agent_id=agent_id, metadata={"reason": reason})

    async def revoke_delegation(self, delegation_id: UUID, reason: str, 
                                cascade_from_agent: bool = False) -> None:
        # Same pattern: Redis first, then async DB update
        await redis.set(f"kya:revoked:delegation:{delegation_id}", reason)
        
        # Find and revoke all unused tokens under this delegation
        tokens = await db.query(
            "SELECT jti, expires_at FROM intent_tokens "
            "WHERE delegation_id = %s AND status = 'unused'", [delegation_id]
        )
        for t in tokens:
            ttl = max(0, int((t.expires_at - datetime.utcnow()).total_seconds()))
            await redis.setex(f"kya:revoked:token:{t.jti}", ttl, reason)
        
        await self.queue_db_update("delegation", delegation_id, "revoked", reason)
        await audit.log(event_type="delegation.revoked", delegation_id=delegation_id)
```

### Revocation Endpoints

```python
# POST /v1/revoke/agent/{agent_id}
# POST /v1/revoke/delegation/{delegation_id}
# POST /v1/revoke/token/{token_id}

# Request body (all three):
class RevokeRequest(BaseModel):
    reason: Literal[
        "SECURITY_INCIDENT",
        "PERMISSION_CHANGE",
        "ACTION_CANCELLED",
        "EXPIRED",
        "USER_REQUEST",
        "ADMIN_ACTION",
    ]
    notes: str | None = None

# Response:
class RevokeResponse(BaseModel):
    revoked: bool
    propagation_ms: float          # How long Redis write took
    cascaded_to: list[str]         # IDs of cascaded revocations
    revoked_at: datetime
```

---

## 4.2 — Step-Up Service

### Step-Up Flow

```
INITIATION (triggered by PolicyEngine when decision = step_up):
  1. Create stepup_challenges row with status = 'pending'
  2. Store challenge state in Redis: kya:stepup:pending:{challenge_id} TTL=300s
  3. Dispatch notification to principal (push/SMS/email — pluggable channel interface)
  4. Return challenge_id and poll_url to the original caller
  5. Agent polls /v1/stepup/{challenge_id}/status every 2-5 seconds

RESOLUTION (when human responds):
  POST /v1/stepup/{challenge_id}/respond
  {
    "decision": "approve",
    "totp_code": "123456"    # if channel = totp
  }
  
  On APPROVE:
    1. Validate TOTP / push response
    2. Update challenge status = 'approved'
    3. Update Redis key: kya:stepup:pending:{challenge_id} = 'approved'
    4. Issue a new intent token (upgraded token) with status = 'unused'
       - This new token has the same action/payload as the original
       - TTL = 5 minutes from approval
    5. Write audit log: event_type = 'stepup.approved'
    6. If callback_url registered: POST the result to webhook
  
  On REJECT:
    1. Update challenge status = 'rejected'
    2. Revoke the original intent token
    3. Write audit log: event_type = 'stepup.rejected'
  
  On TIMEOUT (challenge expires with no response):
    1. Background job (Redis keyspace notification on TTL expiry)
    2. Update challenge status = 'expired'
    3. Revoke the original intent token
    4. Write audit log: event_type = 'stepup.timeout'
```

### Polling Endpoint

```python
# GET /v1/stepup/{challenge_id}/status
class StepUpStatusResponse(BaseModel):
    status: Literal["pending", "approved", "rejected", "expired"]
    challenge_id: UUID
    upgraded_token: str | None = None   # populated on approve
    decision_at: datetime | None = None
    expires_at: datetime

# Agent polls this every 2-5 seconds
# Once status != 'pending': agent stops polling
# If status = 'approved': agent uses upgraded_token for the action
```

---

## 4.3 — Phase 4 Acceptance Criteria

- [ ] `POST /v1/revoke/agent/{id}` writes to Redis in < 5ms
- [ ] Immediately after agent revocation, `POST /v1/verify-agent-action` returns `AGENT_REVOKED`
- [ ] Delegation revocation cascades to all associated unused tokens (check Redis keys)
- [ ] Step-up challenge is created and returned in verify response
- [ ] Polling endpoint returns `pending` until resolved
- [ ] Human approval issues upgraded token
- [ ] Upgraded token can be used to pass verification
- [ ] Expired challenge (timeout) revokes the original token
- [ ] Webhook fires on challenge resolution if callback_url registered

### Phase 4 Required Tests

```
tests/unit/test_revocation_service.py
  - test_revoke_agent_redis_written_first
  - test_revoke_agent_cascades_to_delegations
  - test_revoke_delegation_cascades_to_tokens
  - test_revoke_token_direct

tests/integration/test_revocation_propagation.py
  - test_verify_fails_immediately_after_agent_revoke
  - test_verify_fails_immediately_after_delegation_revoke
  - test_verify_fails_immediately_after_token_revoke
  - test_revocation_latency_under_5ms

tests/integration/test_stepup_flow.py
  - test_stepup_initiated_on_amount_threshold
  - test_polling_returns_pending
  - test_approval_issues_upgraded_token
  - test_upgraded_token_passes_verification
  - test_rejection_revokes_original_token
  - test_timeout_revokes_original_token
```

---

---

# PHASE 5 — Audit, Hardening & Multi-Tenancy (Week 8)

**Goal:** Tamper-evident audit log with hash chaining. Multi-tenant isolation enforced at database level. Audit verification endpoint. Rate limiting. Production-readiness hardening.

**Acceptance gate:** Audit chain can be independently verified. Tenant A cannot access Tenant B's data (test with direct SQL and API). Rate limiting blocks excessive requests. System handles 500 concurrent verify requests without errors.

---

## 5.1 — Audit Log Service

### Hash Chain Implementation

```python
# services/audit.py

class AuditService:

    async def log(self, event_type: str, **kwargs) -> AuditLogEntry:
        tenant_id = kwargs.get("tenant_id")
        
        # 1. Fetch the previous entry's hash for this tenant
        previous_entry = await db.fetch_one(
            "SELECT entry_hash FROM audit_log "
            "WHERE tenant_id = %s "
            "ORDER BY sequence_num DESC LIMIT 1",
            [tenant_id]
        )
        previous_hash = previous_entry.entry_hash if previous_entry else "GENESIS"
        
        # 2. Build the entry dict (excluding entry_hash)
        entry = {
            "tenant_id":    str(tenant_id),
            "event_type":   event_type,
            "agent_id":     str(kwargs.get("agent_id", "")),
            "action":       kwargs.get("action", ""),
            "decision":     kwargs.get("decision", ""),
            "risk_score":   kwargs.get("risk_score"),
            "created_at":   datetime.utcnow().isoformat() + "Z",
            **kwargs
        }
        
        # 3. Compute request_hash (hash of the triggering request payload)
        request_hash = hash_payload(kwargs.get("request_payload", {}))
        
        # 4. Compute entry_hash (hash of entry content + previous_hash)
        entry_hash = compute_entry_hash(entry, previous_hash)
        
        # 5. Insert — this is the ONLY write path
        return await db.insert("audit_log", {
            **entry,
            "request_hash":  request_hash,
            "previous_hash": previous_hash,
            "entry_hash":    entry_hash,
        })
```

### Audit Chain Verification Endpoint

```python
# GET /v1/audit/verify-chain?tenant_id={tenant_id}&from_seq={n}&to_seq={m}

# This endpoint allows external auditors to verify chain integrity.
# It re-computes all entry hashes and verifies they form an unbroken chain.

class ChainVerificationResponse(BaseModel):
    is_valid: bool
    entries_checked: int
    first_sequence: int
    last_sequence: int
    broken_at_sequence: int | None = None   # null if chain is intact
    verification_timestamp: datetime
```

### Audit Query Endpoints

```python
# GET /v1/audit/events?agent_id={id}&from={iso}&to={iso}&event_type={type}
# GET /v1/audit/agent/{agent_id}/timeline
# GET /v1/audit/decisions?decision=deny&from={iso}&to={iso}

# All queries are scoped to tenant automatically via middleware.
# No cross-tenant data is ever accessible.
```

---

## 5.2 — Multi-Tenancy Enforcement

### Row-Level Security (Postgres)

```sql
-- Enable RLS on all tables
ALTER TABLE agents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE delegations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE intent_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE stepup_challenges ENABLE ROW LEVEL SECURITY;

-- Create policy: app can only see rows matching current tenant context
-- Set via: SET app.current_tenant_id = '{tenant_id}'

CREATE POLICY tenant_isolation ON agents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation ON delegations
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Repeat for all tables
```

### Application-Level Enforcement

```python
# database.py

@asynccontextmanager
async def get_db_session(tenant_id: UUID):
    """Every DB session must have tenant context set."""
    async with AsyncSession(engine) as session:
        # Set Postgres session variable for RLS
        await session.execute(
            text(f"SET app.current_tenant_id = '{tenant_id}'")
        )
        yield session
        # RLS ensures no cross-tenant leakage at DB level
```

---

## 5.3 — Rate Limiting

```python
# middleware.py — applied to ALL routes

RATE_LIMITS = {
    "/v1/verify-agent-action": {"requests": 1000, "window_seconds": 60},
    "/v1/agents/register":     {"requests": 100,  "window_seconds": 60},
    "/v1/intent/issue":        {"requests": 500,  "window_seconds": 60},
    "default":                 {"requests": 300,  "window_seconds": 60},
}

# Redis sliding window counter
async def check_rate_limit(tenant_id: UUID, endpoint: str) -> bool:
    limit_config = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
    key = f"kya:rate:{tenant_id}:{endpoint}:{current_window()}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, limit_config["window_seconds"])
    if count > limit_config["requests"]:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

---

## 5.4 — Production Hardening

### Structured Logging

```python
# All log lines must be structured JSON via structlog
# Required fields on every log line:
{
  "timestamp":   "ISO8601",
  "level":       "INFO|WARN|ERROR",
  "service":     "kya-api",
  "tenant_id":   "uuid",
  "request_id":  "uuid",
  "event":       "human-readable event name",
  "duration_ms": 42.3,          # always include for API calls
  # ... event-specific fields
}
```

### Health Check Endpoints

```python
# GET /health          — liveness: returns 200 if process is alive
# GET /health/ready    — readiness: checks DB, Redis, OPA connectivity
# GET /health/detailed — full dependency status (internal use only)

class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    dependencies: dict[str, bool]   # {"postgres": true, "redis": true, "opa": true}
    version: str
    uptime_seconds: float
```

### Graceful Shutdown

```python
# main.py
# Handle SIGTERM: stop accepting new requests, finish in-flight requests,
# close DB connection pool, close Redis connection pool, exit cleanly.
# In-flight request timeout: 10 seconds.
```

---

## 5.5 — Phase 5 Acceptance Criteria

- [ ] Audit chain verification endpoint returns `is_valid: true` for untampered log
- [ ] Manually corrupting one audit row causes chain verification to return `broken_at_sequence`
- [ ] Tenant A cannot access Tenant B's agents via API (test with cross-tenant JWT)
- [ ] Postgres RLS blocks cross-tenant direct SQL query (test with psql)
- [ ] Rate limiting returns 429 after limit exceeded
- [ ] `/health/ready` returns unhealthy when Postgres is down
- [ ] 500 concurrent verify requests complete without errors (load test)
- [ ] All log lines are structured JSON with required fields
- [ ] Graceful shutdown completes in-flight requests before exit

### Phase 5 Required Tests

```
tests/unit/test_audit_service.py
  - test_hash_chain_computed_correctly
  - test_genesis_entry_has_correct_previous_hash
  - test_chain_verification_passes_untampered_log
  - test_chain_verification_detects_tampering

tests/integration/test_multi_tenancy.py
  - test_tenant_a_cannot_read_tenant_b_agents
  - test_tenant_a_cannot_verify_tenant_b_token
  - test_cross_tenant_jwt_rejected
  - test_rls_blocks_direct_sql_cross_tenant

tests/integration/test_rate_limiting.py
  - test_rate_limit_allows_under_limit
  - test_rate_limit_blocks_over_limit
  - test_rate_limit_resets_after_window

tests/load/test_verify_throughput.py
  - test_500_concurrent_requests_no_errors
  - test_p99_latency_under_100ms_at_load
```

---

---

# APPENDIX A — Known Hard Problems & Solutions

## Hard Problem 1: Autonomous Agents (No Human Present)

**Problem:** Intent tokens require human authorization. Autonomous agents run without a human present.

**Solution:** Pre-auth mandate pattern (Phase 2).
- Human signs a batch mandate once upfront
- Mandate specifies workflow, constraints, and time window
- Agent creates individual tokens against the mandate autonomously
- Mandate has a spend ceiling — agent cannot exceed it
- All tokens issued this way are tagged `token_mode = 'pre_auth'` in audit log

## Hard Problem 2: Agent-to-Agent Trust

**Problem:** Multi-agent systems (CrewAI, LangGraph) need sub-agents to act on behalf of orchestrators.

**Solution:** Agent delegation model (Migration 004).
- Orchestrator agent can sub-delegate to worker agents
- Scope contraction is enforced: child scope ⊆ parent scope
- Max depth of 3 hops (enforced by DB constraint AND application layer)
- Each hop is recorded in audit log, forming a full chain of custody

## Hard Problem 3: Revocation Latency

**Problem:** Database writes are too slow for real-time revocation (verification targets < 100ms).

**Solution:** Redis-first revocation.
- Revocation writes to Redis synchronously (< 1ms)
- DB update is async via Redis Stream worker
- All verify calls check Redis revocation keys before touching DB
- Agent/delegation cache TTL is 60s — but revocation keys are permanent

## Hard Problem 4: Verification Endpoint Latency

**Problem:** Policy evaluation requires agent + delegation + token data from DB. 3 sequential reads = too slow.

**Solution:** Parallel hydration + Redis cache.
- All three fetches (agent, delegation, token) run concurrently via `asyncio.gather`
- Hot data cached in Redis with 60s TTL
- Revocation checks always bypass cache (correctness > speed for revocation)
- OPA runs in a sidecar container (no network hop overhead)

## Hard Problem 5: Audit Log Integrity

**Problem:** DBA access or infrastructure breach can modify audit records.

**Solution:** Hash chaining + external anchor (Post-MVP).
- Every entry includes SHA-256(entry_content + previous_entry_hash)
- Tampering with any entry breaks all subsequent hashes
- Phase 5 includes verification endpoint to detect any break in chain
- Post-MVP: periodically anchor chain head hash to write-only S3 with Object Lock

---

# APPENDIX B — Event Type Reference

All valid `event_type` values for the audit log:

| Event Type | Triggered By |
|---|---|
| `agent.registered` | POST /v1/agents/register |
| `agent.revoked` | POST /v1/revoke/agent/{id} |
| `agent.key_rotated` | POST /v1/agents/{id}/rotate-keys |
| `delegation.created` | POST /v1/delegations |
| `delegation.revoked` | POST /v1/revoke/delegation/{id} |
| `delegation.expired` | Background job on TTL |
| `agent_delegation.created` | POST /v1/delegations/agent-to-agent |
| `pre_auth.created` | POST /v1/delegations/pre-auth |
| `token.issued` | POST /v1/intent/issue |
| `token.issued_autonomous` | POST /v1/intent/issue-from-pre-auth |
| `token.used` | Successful verify (allow decision) |
| `token.revoked` | POST /v1/revoke/token/{id} or cascade |
| `action.allow` | POST /v1/verify-agent-action (allow) |
| `action.deny` | POST /v1/verify-agent-action (deny) |
| `action.step_up` | POST /v1/verify-agent-action (step_up) |
| `stepup.initiated` | PolicyEngine triggers step-up |
| `stepup.approved` | POST /v1/stepup/{id}/respond (approve) |
| `stepup.rejected` | POST /v1/stepup/{id}/respond (reject) |
| `stepup.timeout` | Background job on challenge TTL expiry |

---

# APPENDIX C — Deny Reason Reference

All valid `denial_reason` values returned by the verification API:

| Code | Meaning |
|---|---|
| `AGENT_NOT_FOUND` | agent_id does not exist |
| `AGENT_REVOKED` | Agent has been explicitly revoked |
| `AGENT_INVALID_STATUS` | Agent is suspended |
| `AGENT_ENV_MISMATCH` | Agent is sandbox, request is production (or vice versa) |
| `DELEGATION_NOT_FOUND` | delegation_id from token does not exist |
| `DELEGATION_REVOKED` | Delegation has been explicitly revoked |
| `DELEGATION_EXPIRED` | Delegation TTL has passed |
| `ACTION_NOT_PERMITTED` | Action not in `allowed_actions` |
| `ACTION_EXPLICITLY_DENIED` | Action is in `denied_actions` |
| `TOKEN_NOT_FOUND` | Token JTI not found |
| `TOKEN_ALREADY_USED` | Single-use token was replayed |
| `TOKEN_REVOKED` | Token was explicitly revoked |
| `TOKEN_EXPIRED` | Token TTL has passed |
| `TOKEN_PAYLOAD_MISMATCH` | action_payload hash does not match token's action_hash |
| `AMOUNT_EXCEEDS_LIMIT` | Payload amount exceeds delegation max_amount_usd |
| `OUTSIDE_TIME_WINDOW` | Request is outside delegation's allowed time window |
| `RATE_LIMIT_EXCEEDED` | Agent has exceeded its rate limit |
| `RISK_SCORE_TOO_HIGH` | Risk score exceeded auto-deny threshold |

---

# APPENDIX D — Redis Key Reference

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `kya:tenant:{slug}` | String | 300s | Tenant record cache |
| `kya:agent:cache:{agent_id}` | String | 60s | Agent record cache |
| `kya:delegation:cache:{id}` | String | 60s | Delegation record cache |
| `kya:revoked:agent:{agent_id}` | String | Permanent | Agent revocation flag |
| `kya:revoked:delegation:{id}` | String | Permanent | Delegation revocation flag |
| `kya:revoked:token:{jti}` | String | Token's original TTL | Token revocation flag |
| `kya:stepup:pending:{challenge_id}` | String | 300s | Step-up challenge state |
| `kya:rate:{tenant_id}:{endpoint}:{window}` | String | Window duration | Rate limit counter |

---

# APPENDIX E — Build Order Checklist

Use this as your task tracker. Complete every item before moving to the next phase.

```
PHASE 1 — Foundation
  [ ] Repository structure created
  [ ] docker-compose.yml with all services
  [ ] pyproject.toml with all dependencies
  [ ] config.py with pydantic-settings
  [ ] database.py with async SQLAlchemy
  [ ] redis_client.py with connection pool
  [ ] All 7 migrations written and tested
  [ ] Tenant middleware implemented and tested
  [ ] Request ID middleware implemented
  [ ] JWT auth dependency implemented
  [ ] Crypto utils: keypair generation, JWT sign/verify, hash functions
  [ ] Identity service: agent registration
  [ ] Agents router: POST /v1/agents/register
  [ ] All Phase 1 tests passing
  [ ] docker compose up brings full stack with no errors

PHASE 2 — Delegation & Intent
  [ ] Delegation service: human→agent delegation
  [ ] Delegation service: agent→agent delegation with scope contraction
  [ ] Delegation service: pre-auth mandate creation
  [ ] Intent service: token issuance (interactive)
  [ ] Intent service: token issuance from pre-auth (autonomous)
  [ ] Spend tracking for pre-auth mandates
  [ ] Delegation router: all endpoints
  [ ] Intent router: all endpoints
  [ ] All Phase 2 tests passing

PHASE 3 — Policy Engine & Verification
  [ ] OPA policy: main.rego with all rules
  [ ] OPA policy: unit tests (opa test)
  [ ] Risk engine: all 6 signals implemented
  [ ] Policy engine: hydration + OPA evaluation + risk override
  [ ] Verification router: POST /v1/verify-agent-action
  [ ] Redis cache-aside pattern for agent and delegation
  [ ] Token consumption on allow decision
  [ ] Audit log for all verify outcomes
  [ ] Latency test: p99 < 100ms
  [ ] All Phase 3 tests passing

PHASE 4 — Revocation & Step-Up
  [ ] Revocation service: agent revocation with cascade
  [ ] Revocation service: delegation revocation with cascade
  [ ] Revocation service: token revocation
  [ ] Revocation router: all three endpoints
  [ ] Step-up service: challenge creation and dispatch
  [ ] Step-up service: human response handling (approve/reject)
  [ ] Step-up service: timeout handling via Redis TTL
  [ ] Step-up service: upgraded token issuance on approve
  [ ] Step-up router: all endpoints
  [ ] Webhook delivery on challenge resolution
  [ ] All Phase 4 tests passing

PHASE 5 — Audit, Hardening & Multi-Tenancy
  [ ] Audit service: hash chain computation
  [ ] Audit chain verification endpoint
  [ ] Audit query endpoints with tenant scoping
  [ ] Postgres RLS policies on all tables
  [ ] DB session context sets tenant for RLS
  [ ] Rate limiting middleware on all routes
  [ ] Structured JSON logging via structlog
  [ ] Health check endpoints (liveness + readiness)
  [ ] Graceful shutdown handler
  [ ] Load test: 500 concurrent requests
  [ ] All Phase 5 tests passing
  [ ] Full end-to-end smoke test across all phases
```

---

*KYA Build Specification v1.0 — Ready for Claude Code*

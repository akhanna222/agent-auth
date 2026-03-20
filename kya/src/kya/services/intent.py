"""Intent token service — issuance and management."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from ..database import get_db_session
from ..models.db.delegation import Delegation
from ..models.db.intent_token import IntentToken
from ..schemas.api.delegations import GrantedScopes
from ..schemas.api.intent import IntentIssueRequest
from ..services.audit import audit_service
from ..utils.crypto import hash_payload, sign_jwt, verify_jwt


class IntentService:
    async def issue_token(
        self,
        tenant_id: str,
        principal_id: str,
        request: IntentIssueRequest,
        platform_private_key: str,
    ) -> IntentToken:
        delegation_id = str(request.delegation_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(Delegation).where(Delegation.delegation_id == delegation_id)
            )
            delegation = result.scalar_one_or_none()
            if not delegation:
                raise ValueError("Delegation not found")
            if delegation.status != "active":
                raise ValueError("Delegation is not active")
            if delegation.principal_id != principal_id:
                raise ValueError("Delegation does not belong to this principal")

            # Verify action is in granted scopes
            scopes = GrantedScopes(**delegation.granted_scopes)
            if request.action not in scopes.allowed_actions:
                raise ValueError(f"Action '{request.action}' is not in delegation's allowed actions")
            if request.action in scopes.denied_actions:
                raise ValueError(f"Action '{request.action}' is explicitly denied")

            # Check amount constraint
            amount = request.action_payload.get("amount_usd")
            if amount is not None and scopes.max_amount_usd is not None:
                if float(amount) > scopes.max_amount_usd:
                    raise ValueError(
                        f"Amount {amount} exceeds delegation limit {scopes.max_amount_usd}"
                    )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        jti = str(uuid.uuid4())
        action_hash = hash_payload(request.action_payload)

        jwt_payload = {
            "sub": principal_id,
            "jti": jti,
            "agent_id": delegation.agent_id,
            "delegation_id": delegation_id,
            "action": request.action,
            "action_hash": action_hash,
            "constraints": delegation.constraints,
        }
        signed_token = sign_jwt(jwt_payload, platform_private_key, expiry_seconds=request.expires_in_seconds)

        token = IntentToken(
            token_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            jti=jti,
            agent_id=delegation.agent_id,
            principal_id=principal_id,
            delegation_id=delegation_id,
            token_mode="single_use",
            action=request.action,
            action_payload=request.action_payload,
            constraints=delegation.constraints,
            signed_token=signed_token,
            status="unused",
            issued_at=now,
            expires_at=expires_at,
        )

        async with get_db_session() as session:
            session.add(token)
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="token.issued",
            agent_id=delegation.agent_id,
            principal_id=principal_id,
            token_id=token.token_id,
            delegation_id=delegation_id,
            action=request.action,
        )

        return token

    async def issue_from_pre_auth(
        self,
        tenant_id: str,
        agent_id: str,
        mandate_token: str,
        action: str,
        action_payload: dict,
        expires_in_seconds: int,
        platform_private_key: str,
        platform_public_key: str,
    ) -> IntentToken:
        """Issue token from pre-auth mandate (autonomous flow)."""
        # Verify mandate token
        claims = verify_jwt(mandate_token, platform_public_key)
        delegation_id = claims["delegation_id"]
        principal_id = claims["sub"]

        async with get_db_session() as session:
            result = await session.execute(
                select(Delegation).where(Delegation.delegation_id == delegation_id)
            )
            delegation = result.scalar_one_or_none()
            if not delegation or delegation.status != "active":
                raise ValueError("Pre-auth delegation not found or inactive")

            scopes = GrantedScopes(**delegation.granted_scopes)
            if action not in scopes.allowed_actions:
                raise ValueError(f"Action '{action}' not in mandate's allowed actions")

            # Check spend budget
            amount = action_payload.get("amount_usd")
            if amount is not None and scopes.max_amount_usd is not None:
                total_result = await session.execute(
                    select(func.coalesce(
                        func.sum(func.json_extract(IntentToken.action_payload, "$.amount_usd")),
                        0
                    )).where(
                        IntentToken.delegation_id == delegation_id,
                        IntentToken.status.in_(["unused", "used"]),
                    )
                )
                total_spent = float(total_result.scalar() or 0)
                if total_spent + float(amount) > scopes.max_amount_usd:
                    raise ValueError("Pre-auth budget exhausted")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        jti = str(uuid.uuid4())
        action_hash = hash_payload(action_payload)

        jwt_payload = {
            "sub": principal_id,
            "jti": jti,
            "agent_id": agent_id,
            "delegation_id": delegation_id,
            "action": action,
            "action_hash": action_hash,
        }
        signed_token = sign_jwt(jwt_payload, platform_private_key, expiry_seconds=expires_in_seconds)

        token = IntentToken(
            token_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            jti=jti,
            agent_id=agent_id,
            principal_id=principal_id,
            delegation_id=delegation_id,
            token_mode="pre_auth",
            action=action,
            action_payload=action_payload,
            constraints={},
            signed_token=signed_token,
            status="unused",
            issued_at=now,
            expires_at=expires_at,
        )

        async with get_db_session() as session:
            session.add(token)
            await session.commit()

        await audit_service.log(
            tenant_id=tenant_id,
            event_type="token.issued_autonomous",
            agent_id=agent_id,
            principal_id=principal_id,
            token_id=token.token_id,
            delegation_id=delegation_id,
            action=action,
        )

        return token

    async def get_token(self, token_id: str) -> IntentToken | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(IntentToken).where(IntentToken.token_id == token_id)
            )
            return result.scalar_one_or_none()

    async def get_token_by_jti(self, jti: str) -> IntentToken | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(IntentToken).where(IntentToken.jti == jti)
            )
            return result.scalar_one_or_none()

    async def consume_token(self, token_id: str) -> None:
        async with get_db_session() as session:
            result = await session.execute(
                select(IntentToken).where(IntentToken.token_id == token_id)
            )
            token = result.scalar_one_or_none()
            if token:
                token.status = "used"
                token.used_at = datetime.now(timezone.utc)
                token.use_count += 1
                session.add(token)
                await session.commit()

    async def list_tokens(self, tenant_id: str) -> list[IntentToken]:
        async with get_db_session() as session:
            result = await session.execute(
                select(IntentToken).where(IntentToken.tenant_id == tenant_id).order_by(IntentToken.issued_at.desc())
            )
            return list(result.scalars().all())


intent_service = IntentService()

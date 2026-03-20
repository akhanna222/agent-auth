"""Cryptographic utilities: Ed25519 key generation, JWT signing/verifying, hashing."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def generate_ed25519_keypair() -> tuple[str, str]:
    """Generate an Ed25519 keypair. Returns (public_key_pem, private_key_pem)."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return public_pem, private_pem


def sign_jwt(
    payload: dict,
    private_key_pem: str,
    issuer: str = "kya-platform",
    expiry_seconds: int = 3600,
) -> str:
    """Sign a JWT using EdDSA (Ed25519). Always includes iat, exp, jti, iss."""
    now = datetime.now(timezone.utc)
    payload = {
        **payload,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=expiry_seconds),
        "jti": payload.get("jti", str(uuid.uuid4())),
    }
    return jwt.encode(payload, private_key_pem, algorithm="EdDSA")


def verify_jwt(token: str, public_key_pem: str, issuer: str = "kya-platform") -> dict:
    """Verify JWT signature, expiry, issuer. Raises on any failure."""
    return jwt.decode(
        token,
        public_key_pem,
        algorithms=["EdDSA"],
        issuer=issuer,
        options={"require": ["exp", "iat", "jti", "iss"]},
    )


def hash_payload(payload: dict) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def compute_entry_hash(entry: dict, previous_hash: str) -> str:
    """SHA-256(json(entry) + previous_hash) — for audit chain."""
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((canonical + previous_hash).encode()).hexdigest()

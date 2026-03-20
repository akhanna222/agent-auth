"""Tests for cryptographic utilities."""
import time

import pytest

from kya.utils.crypto import (
    compute_entry_hash,
    generate_ed25519_keypair,
    hash_payload,
    sign_jwt,
    verify_jwt,
)


def test_generate_ed25519_keypair():
    public_key, private_key = generate_ed25519_keypair()
    assert "BEGIN PUBLIC KEY" in public_key
    assert "BEGIN PRIVATE KEY" in private_key


def test_jwt_sign_and_verify():
    public_key, private_key = generate_ed25519_keypair()
    payload = {"sub": "test-user", "data": "hello"}
    token = sign_jwt(payload, private_key)
    claims = verify_jwt(token, public_key)
    assert claims["sub"] == "test-user"
    assert claims["data"] == "hello"
    assert "jti" in claims
    assert "iat" in claims
    assert "exp" in claims
    assert claims["iss"] == "kya-platform"


def test_jwt_rejects_expired_token():
    public_key, private_key = generate_ed25519_keypair()
    token = sign_jwt({"sub": "test"}, private_key, expiry_seconds=-1)
    with pytest.raises(Exception):
        verify_jwt(token, public_key)


def test_jwt_rejects_wrong_key():
    _, private_key = generate_ed25519_keypair()
    other_public, _ = generate_ed25519_keypair()
    token = sign_jwt({"sub": "test"}, private_key)
    with pytest.raises(Exception):
        verify_jwt(token, other_public)


def test_payload_hash_canonical():
    h1 = hash_payload({"b": 2, "a": 1})
    h2 = hash_payload({"a": 1, "b": 2})
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_audit_chain_hash():
    entry = {"event": "test", "data": "value"}
    h1 = compute_entry_hash(entry, "GENESIS")
    h2 = compute_entry_hash(entry, "GENESIS")
    assert h1 == h2

    h3 = compute_entry_hash(entry, "different_prev")
    assert h3 != h1


def test_ed25519_sign_and_verify():
    """Alias test — ensures EdDSA algorithm is used."""
    pub, priv = generate_ed25519_keypair()
    token = sign_jwt({"sub": "agent-1", "action": "payment.create"}, priv)
    claims = verify_jwt(token, pub)
    assert claims["action"] == "payment.create"

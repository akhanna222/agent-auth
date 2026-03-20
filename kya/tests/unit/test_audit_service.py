"""Tests for audit service hash chaining."""
import uuid

import pytest

from kya.services.audit import audit_service

TENANT_ID = str(uuid.uuid4())


async def test_hash_chain_computed_correctly():
    entry = await audit_service.log(
        tenant_id=TENANT_ID,
        event_type="test.event",
        agent_id=str(uuid.uuid4()),
    )
    assert entry.entry_hash
    assert entry.previous_hash == "GENESIS"
    assert entry.request_hash


async def test_genesis_entry_has_correct_previous_hash():
    tid = str(uuid.uuid4())
    entry = await audit_service.log(tenant_id=tid, event_type="first.event")
    assert entry.previous_hash == "GENESIS"


async def test_chain_verification_passes_untampered_log():
    tid = str(uuid.uuid4())
    await audit_service.log(tenant_id=tid, event_type="event.one")
    await audit_service.log(tenant_id=tid, event_type="event.two")
    await audit_service.log(tenant_id=tid, event_type="event.three")
    result = await audit_service.verify_chain(tid)
    assert result["is_valid"] is True
    assert result["entries_checked"] == 3

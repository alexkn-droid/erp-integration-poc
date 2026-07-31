from __future__ import annotations

from erp_poc.idempotency import IdempotencyStore


def test_get_missing_returns_none(tmp_path):
    store = IdempotencyStore(tmp_path / "store.json")
    assert store.get("nope") is None


def test_put_then_get_round_trips(tmp_path):
    store = IdempotencyStore(tmp_path / "store.json")
    store.put("ext-1", "qbo-42")
    assert store.get("ext-1") == "qbo-42"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "store.json"
    IdempotencyStore(path).put("ext-1", "qbo-42")
    reloaded = IdempotencyStore(path)
    assert reloaded.get("ext-1") == "qbo-42"


def test_multiple_keys_do_not_clobber_each_other(tmp_path):
    store = IdempotencyStore(tmp_path / "store.json")
    store.put("ext-1", "qbo-1")
    store.put("ext-2", "qbo-2")
    assert store.get("ext-1") == "qbo-1"
    assert store.get("ext-2") == "qbo-2"

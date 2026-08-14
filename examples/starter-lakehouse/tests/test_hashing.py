from __future__ import annotations

from starter_lakehouse import hashing


def test_content_hash_key_order_invariant():
    assert hashing.content_hash({"a": 1, "b": 2}) == hashing.content_hash({"b": 2, "a": 1})


def test_content_hash_value_sensitive():
    assert hashing.content_hash({"a": 1}) != hashing.content_hash({"a": 2})
    assert hashing.content_hash("x") != hashing.content_hash("y")


def test_identify_changes_classification():
    known = {"1": hashing.content_hash({"id": 1, "v": "same"})}
    records = [
        {"id": 1, "v": "same"},
        {"id": 2, "v": "new"},
    ]
    changes = hashing.identify_changes(records, "id", known)
    assert [r["id"] for r in changes["unchanged"]] == [1]
    assert [r["id"] for r in changes["new"]] == [2]
    assert changes["changed"] == []
    assert all(hashing.HASH_COLUMN in r for r in records)


def test_identify_changes_detects_change():
    known = {"1": hashing.content_hash({"id": 1, "v": "old"})}
    changes = hashing.identify_changes([{"id": 1, "v": "new"}], "id", known)
    assert [r["id"] for r in changes["changed"]] == [1]


def test_identify_changes_stable_across_runs():
    """Stamping the hash column must not change the next run's hash."""
    record = {"id": 1, "v": "same"}
    first = hashing.identify_changes([record], "id", {})
    stamped = first["new"][0]
    second = hashing.identify_changes([dict(stamped)], "id", {"1": stamped[hashing.HASH_COLUMN]})
    assert [r["id"] for r in second["unchanged"]] == [1]


def test_get_existing_hashes_empty_keys_short_circuits():
    # spark=None proves no session is touched for the empty case
    assert hashing.get_existing_hashes(None, "t", "id", []) == {}  # type: ignore[arg-type]


def test_filter_records_empty():
    assert hashing.filter_records_needing_update(None, [], "t", "id") == []  # type: ignore[arg-type]

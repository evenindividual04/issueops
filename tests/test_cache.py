import json
import os

import pytest

from app.models.schemas import IssueMetadata
from app.services.cache import CacheManager


def _meta(**overrides) -> IssueMetadata:
    defaults = dict(
        has_reproduction_steps=True,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="prod",
        summary="example issue",
        difficulty="easy",
        required_skills=["python"],
        primary_area="backend",
        verification_hint=None,
        extraction_confidence=0.9,
    )
    defaults.update(overrides)
    return IssueMetadata(**defaults)


@pytest.fixture
def tmp_cache_path(tmp_path):
    return str(tmp_path / "cache.json")


def test_compute_hash_is_deterministic(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    assert cache._compute_hash("hello") == cache._compute_hash("hello")
    assert cache._compute_hash("a") != cache._compute_hash("b")


def test_set_get_roundtrip(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    metadata = _meta(summary="round-trip me")
    cache.set("issue body text", metadata)
    retrieved = cache.get("issue body text")
    assert retrieved is not None
    assert retrieved.summary == "round-trip me"


def test_get_miss_returns_none(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    assert cache.get("never seen") is None


def test_save_then_load_persists(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.set("body-1", _meta(summary="persisted"))
    cache.save()

    fresh = CacheManager(cache_path=tmp_cache_path)
    retrieved = fresh.get("body-1")
    assert retrieved is not None
    assert retrieved.summary == "persisted"


def test_load_corrupt_cache_falls_back_to_empty(tmp_cache_path):
    with open(tmp_cache_path, "w") as f:
        f.write("{not valid json")
    cache = CacheManager(cache_path=tmp_cache_path)
    assert cache.cache == {}


def test_load_missing_file_starts_empty(tmp_cache_path):
    assert not os.path.exists(tmp_cache_path)
    cache = CacheManager(cache_path=tmp_cache_path)
    assert cache.cache == {}


def test_get_with_corrupt_entry_returns_none(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    key = cache._compute_hash("bad")
    cache.cache[key] = {"not": "a valid IssueMetadata"}
    assert cache.get("bad") is None


def test_save_failure_does_not_raise(tmp_cache_path, monkeypatch):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.set("x", _meta())

    def _boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _boom)
    cache.save()  # should swallow the OSError


def test_persisted_file_is_valid_json(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.set("payload", _meta())
    cache.save()
    with open(tmp_cache_path) as f:
        data = json.load(f)
    # v2 envelope: {_schema_version, cache, processed_signatures}
    assert data["_schema_version"] == CacheManager.SCHEMA_VERSION
    assert len(data["cache"]) == 1


def test_mark_and_check_recently_processed(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.mark_processed("o", "r", 1, "body content")

    assert cache.is_recently_processed("o", "r", 1, "body content") is True
    assert cache.is_recently_processed("o", "r", 1, "different body") is False
    assert cache.is_recently_processed("o", "r", 2, "body content") is False


def test_processed_signature_expires_after_window(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.mark_processed("o", "r", 1, "body")
    # Backdate the timestamp by 48h
    key = CacheManager._signature_key("o", "r", 1)
    cache.processed_signatures[key]["ts"] -= 48 * 3600

    assert cache.is_recently_processed("o", "r", 1, "body", window_seconds=24 * 3600) is False
    assert cache.is_recently_processed("o", "r", 1, "body", window_seconds=72 * 3600) is True


def test_processed_signatures_persist_across_load(tmp_cache_path):
    cache = CacheManager(cache_path=tmp_cache_path)
    cache.mark_processed("o", "r", 1, "body")
    cache.save()

    fresh = CacheManager(cache_path=tmp_cache_path)
    assert fresh.is_recently_processed("o", "r", 1, "body") is True


def test_legacy_v1_cache_file_still_loads(tmp_cache_path):
    # Pre-v1.1 file: flat dict of sha → metadata, no schema_version envelope.
    with open(tmp_cache_path, "w") as f:
        json.dump({"deadbeef": {}}, f)

    cache = CacheManager(cache_path=tmp_cache_path)
    assert cache.cache == {"deadbeef": {}}
    assert cache.processed_signatures == {}

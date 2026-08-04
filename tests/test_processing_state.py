from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.processing_state import detector_version, merge_results, prune_state, select_pending


def test_detector_version_changes_with_code(tmp_path: Path):
    source = tmp_path / "detector.py"
    source.write_text("one\n")
    first = detector_version([source])
    source.write_text("two\n")
    assert detector_version([source]) != first


def test_same_item_and_version_is_skipped():
    state = {"entries": [{"item_id": "123", "detector_version": "v1", "listing_hash": "a", "last_seen_at": "2026-08-03T00:00:00Z"}]}
    listings = [{"id": "123", "listing_hash": "a"}, {"id": "456", "listing_hash": "b"}]
    assert [item["id"] for item in select_pending(listings, state, "v1")] == ["456"]
    assert [item["id"] for item in select_pending(listings, state, "v2")] == ["123", "456"]


def test_prunes_entries_older_than_seven_days():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    state = {"entries": [
        {"item_id": "old", "detector_version": "v1", "last_seen_at": "2026-07-27T23:59:59Z"},
        {"item_id": "new", "detector_version": "v1", "last_seen_at": "2026-07-28T00:00:00Z"},
    ]}
    assert prune_state(state, now=now, retention_days=7) == 1
    assert [entry["item_id"] for entry in state["entries"]] == ["new"]


def test_merge_records_result_and_preserves_first_seen():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    state = {"entries": []}
    listings = [{"id": "123", "listing_hash": "abc", "title": "Board", "url": "https://example/123"}]
    results = [{"item_id": "123", "cpu_state": "visible_cpu_likely", "value_score": 80, "maxima": {}, "gallery_count": 4}]
    merge_results(state, listings, results, version="abc", now=now)
    entry = state["entries"][0]
    assert entry["item_id"] == "123"
    assert entry["detector_version"] == "abc"
    assert entry["value_score"] == 80
    assert entry["first_seen_at"] == entry["last_seen_at"]

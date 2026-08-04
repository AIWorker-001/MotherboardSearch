from datetime import datetime, timezone

from src.processing_state import listing_fingerprint, merge_results, result_fingerprint, select_pending


def test_listing_hash_changes_when_gallery_changes():
    listing = {"id": "123", "title": "Board", "card": "$10"}
    first = listing_fingerprint(listing, {"urls": ["a", "b"]})
    assert listing_fingerprint(listing, {"urls": ["b", "a"]}) == first
    assert listing_fingerprint(listing, {"urls": ["a", "b", "c"]}) != first


def test_result_hash_is_stable_and_changes_with_score():
    result = {"cpu_state": "unclear", "value_score": 0, "maxima": {"cpu": 0.4}, "gallery_count": 2}
    first = result_fingerprint(result)
    assert result_fingerprint(dict(result)) == first
    changed = dict(result, value_score=25)
    assert result_fingerprint(changed) != first


def test_pending_uses_item_detector_and_listing_hash():
    listing = {"id": "123", "listing_hash": "gallery-a"}
    state = {"entries": [{"item_id": "123", "detector_version": "v1", "listing_hash": "gallery-a"}]}
    assert select_pending([listing], state, "v1") == []
    assert select_pending([{**listing, "listing_hash": "gallery-b"}], state, "v1")
    assert select_pending([listing], state, "v2")


def test_merge_saves_listing_and_result_hashes():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    state = {"entries": []}
    listings = [{"id": "123", "listing_hash": "abc", "title": "Board"}]
    results = [{"item_id": "123", "cpu_state": "unclear", "value_score": 0, "maxima": {}, "gallery_count": 2}]
    merge_results(state, listings, results, version="v1", now=now)
    entry = state["entries"][0]
    assert entry["listing_hash"] == "abc"
    assert entry["result_hash"] == result_fingerprint(results[0])

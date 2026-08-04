from datetime import datetime, timezone

from src.run_history import append_run, prune


def test_append_and_prune():
    history = {'schema_version': 1, 'runs': []}
    append_run(history, {'status': 'completed', 'listings_found': 5, 'processed': 2}, source='run.json')
    assert len(history['runs']) == 1
    history['runs'][0]['recorded_at'] = '2026-01-01T00:00:00Z'
    removed = prune(history, 30, now=datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert removed == 1

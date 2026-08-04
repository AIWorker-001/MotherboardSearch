from datetime import datetime, timedelta, timezone

from src.distributed_state import claim_shard, complete_shard, fail_shard, initialize_run, recover_stale


def manifest():
    return {'shards': [{'shard': 0, 'items': 2}, {'shard': 1, 'items': 3}]}


def test_claim_complete_and_retry():
    state = {'runs': []}
    run = initialize_run(state, 'r1', manifest())
    shard = claim_shard(run, 'worker-1')
    assert shard['status'] == 'running'
    complete_shard(run, shard['shard'], 'result.json')
    assert shard['status'] == 'completed'
    second = claim_shard(run, 'worker-2')
    fail_shard(run, second['shard'], 'boom', retry_limit=2)
    assert second['status'] == 'retry'


def test_stale_recovery():
    state = {'runs': []}
    run = initialize_run(state, 'r1', manifest())
    shard = claim_shard(run, 'worker-1')
    shard['updated_at'] = '2026-08-04T00:00:00Z'
    recovered = recover_stale(run, 60, now=datetime(2026, 8, 4, 2, 0, tzinfo=timezone.utc))
    assert recovered == 1
    assert shard['status'] == 'retry'

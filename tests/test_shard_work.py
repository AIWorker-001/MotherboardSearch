from src.shard_work import split_items, stable_shard


def test_stable_sharding():
    assert stable_shard('123', 4) == stable_shard('123', 4)
    items = [{'id': str(index)} for index in range(20)]
    shards = split_items(items, 4)
    assert sum(len(rows) for rows in shards) == 20
    flattened = {row['id'] for shard in shards for row in shard}
    assert flattened == {str(index) for index in range(20)}

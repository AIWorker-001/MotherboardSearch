import json
from pathlib import Path

from src.merge_shards import merge_files


def test_merge(tmp_path: Path):
    first = tmp_path / 'a.json'; second = tmp_path / 'b.json'
    first.write_text(json.dumps([{'item_id':'2'}]))
    second.write_text(json.dumps([{'item_id':'1'}]))
    assert [row['item_id'] for row in merge_files([first, second])] == ['1','2']

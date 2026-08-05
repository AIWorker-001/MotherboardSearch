from pathlib import Path
from src.knowledge_storage import KnowledgeStorage


def test_local_storage_round_trip(tmp_path: Path):
    source=tmp_path/'object.bin'; source.write_bytes(b'abc')
    storage=KnowledgeStorage({'backend':'local','cache_root':str(tmp_path/'cache')})
    record=storage.put(source,metadata={'kind':'test'},content_type='application/octet-stream')
    assert record['backend']=='local'
    assert storage.materialize(record,suffix='.bin')==source


def test_coordinator_url_is_generic_and_project_scoped(tmp_path: Path):
    storage=KnowledgeStorage({
        'backend':'coordinator','coordinator_url':'https://coordinator.example',
        'project':'Any-Project','namespace':'arbitrary.assets','cache_root':str(tmp_path),
    })
    assert storage.collection_url=='https://coordinator.example/storage/projects/Any-Project/namespaces/arbitrary.assets/objects'

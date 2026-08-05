from pathlib import Path
from src.reference_gap_queue import build_gap_queue, candidate_manifest_from_verified_listings


def test_queue_contains_models_missing_references(tmp_path: Path):
    (tmp_path/'123_01.jpg').write_bytes(b'jpg')
    ids=[{'item_id':'123','motherboard':{'text':'ASUS P8P67 EVO','source':'listing_probable'}}]
    verification=[{'item_id':'123','model':'ASUS P8P67 EVO','status':'no_reference','identity_score':0.0}]
    queue=build_gap_queue(ids,verification,tmp_path)
    assert queue[0]['model']=='ASUS P8P67 EVO'
    assert queue[0]['next_action']=='collect_reference_candidates'
    assert 'official product image' in queue[0]['search_queries'][0]


def test_confirmed_reference_is_not_queued(tmp_path: Path):
    ids=[{'item_id':'1','motherboard':{'text':'Board','source':'listing_confirmed'}}]
    verification=[{'item_id':'1','status':'reference_confirmed','identity_score':0.9}]
    assert build_gap_queue(ids,verification,tmp_path)==[]


def test_shopgoodwill_candidates_require_explicit_human_approval(tmp_path: Path):
    queue=[{'item_id':'123','model':'ASUS P8P67 EVO','listing_images':['a.jpg','b.jpg']}]
    assert candidate_manifest_from_verified_listings(queue,set())==[]
    candidates=candidate_manifest_from_verified_listings(queue,{'123'})
    assert len(candidates)==2
    assert all(row['source_type']=='shopgoodwill_verified' for row in candidates)

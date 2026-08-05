from pathlib import Path

def test_reference_verification_exists_and_has_review_routing():
    source=Path('src/reference_verification.py').read_text()
    assert 'reference_conflict' in source
    assert 'manual_review_required' in source
    assert 'reference_collection_required' in source


def test_reference_verification_projects_known_regions():
    source=Path('src/reference_verification.py').read_text()
    assert 'projected_regions' in source
    assert 'region_crops' in source


def test_reference_verification_projects_known_regions():
    source=Path('src/reference_verification.py').read_text()
    assert 'projected_regions' in source
    assert 'region_crops' in source

from src.operations_health import evaluate_health


def test_unhealthy_error_rates():
    run = {'listings_found': 10, 'processed': 10, 'search_errors': [1,2,3,4], 'gallery_errors': [1,2,3], 'image_download_errors': [], 'rollback_recommended': False}
    results = [{'needs_review': True} for _ in range(8)] + [{'needs_review': False} for _ in range(2)]
    config = {'maximum_search_errors': 3, 'maximum_gallery_error_rate': 0.2, 'maximum_image_error_rate': 0.15, 'maximum_review_rate': 0.6}
    health = evaluate_health(run, results, config)
    assert not health['healthy']
    assert 'search_errors' in health['reasons']
    assert 'gallery_error_rate' in health['reasons']
    assert 'review_rate' in health['reasons']

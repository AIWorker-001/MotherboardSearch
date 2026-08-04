from datetime import datetime, timezone

from src.continual_learning import labeled_image_count, should_train


def test_labeled_count():
    store = {'images': [{'annotations': []}, {'annotations': [{'label': 'cpu'}]}]}
    assert labeled_image_count(store) == 1


def test_training_thresholds():
    config = {
        'enabled': True,
        'minimum_total_labeled_images': 200,
        'minimum_new_labeled_images': 50,
        'minimum_days_between_training': 7,
        'maximum_training_failures': 3,
    }
    state = {'last_training_at': None, 'last_training_annotation_count': 100, 'consecutive_failures': 0}
    eligible, reasons = should_train(config, state, 210, now=datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert eligible
    assert reasons == []
    eligible, reasons = should_train(config, state, 140, now=datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert not eligible
    assert 'insufficient_total_labels' in reasons
    assert 'insufficient_new_labels' in reasons

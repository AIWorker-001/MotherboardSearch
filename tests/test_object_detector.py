from src.object_detector import Detection, aggregate_evidence, box_iou, non_max_suppression


def test_iou_and_nms_remove_duplicate_same_class_boxes():
    first = Detection("ram_dimm", 0.9, (0, 0, 100, 100), "ram")
    duplicate = Detection("ram_dimm", 0.8, (5, 5, 95, 95), "ram")
    other = Detection("nvme_ssd", 0.7, (5, 5, 95, 95), "ssd")
    assert box_iou(first.box, duplicate.box) > 0.7
    kept = non_max_suppression([duplicate, other, first])
    assert first in kept
    assert duplicate not in kept
    assert other in kept


def test_cooler_is_strong_cpu_evidence():
    result = aggregate_evidence([Detection("intel_stock_cooler", 0.72, (0, 0, 200, 200), "cooler")])
    assert result["cpu_state"] == "cooler_attached_cpu_highly_likely"
    assert result["value_score"] == 100
    assert not result["needs_review"]


def test_empty_socket_and_damage_are_rejected():
    result = aggregate_evidence([
        Detection("empty_lga_socket", 0.80, (0, 0, 200, 200), "empty"),
        Detection("bent_socket_pins", 0.60, (20, 20, 100, 100), "pins"),
    ])
    assert result["cpu_state"] == "empty_socket_likely"
    assert result["value_score"] == -200
    assert result["needs_review"]
    assert "possible_physical_damage" in result["review_reasons"]


def test_ram_and_nvme_raise_score():
    result = aggregate_evidence([
        Detection("cpu_installed", 0.70, (0, 0, 100, 100), "cpu"),
        Detection("ram_dimm", 0.55, (100, 0, 130, 200), "ram"),
        Detection("nvme_ssd", 0.50, (0, 200, 150, 230), "ssd"),
    ])
    assert result["cpu_state"] == "visible_cpu_likely"
    assert result["value_score"] == 140


def test_detection_config_filters_queries_by_group(tmp_path):
    from src.object_detector import DetectionConfig
    config = DetectionConfig(classes={
        'socket': {'queries':['empty socket'], 'group':'socket_state'},
        'cooler': {'queries':['cpu cooler'], 'group':'cooler'},
    })
    assert config.queries({'socket_state'}) == ['empty socket']
    assert config.query_to_class({'cooler'}) == {'cpu cooler':'cooler'}

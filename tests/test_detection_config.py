from pathlib import Path

from src.object_detector import DetectionConfig


def test_phase2_class_config_has_required_groups():
    config = DetectionConfig.load(Path("config/detection_classes.json"))
    groups = {spec["group"] for spec in config.classes.values()}
    assert {"cooler", "socket_state", "component", "damage"} <= groups
    assert "bent_socket_pins" in config.classes
    assert "ram_dimm" in config.classes
    assert "nvme_ssd" in config.classes

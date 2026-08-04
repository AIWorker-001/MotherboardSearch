from src.dataset_builder import split_images, yolo_line


def test_split_is_reproducible():
    rows = [{"image_id": str(index)} for index in range(20)]
    assert split_images(rows, 0.7, 0.15, 42) == split_images(rows, 0.7, 0.15, 42)


def test_yolo_conversion():
    line = yolo_line({"box": [10, 20, 30, 60]}, 2, 100, 100)
    assert line.startswith("2 0.20000000 0.40000000 0.20000000 0.40000000")

from src.annotation_store import add_box, image_id, upsert_image


def test_annotation_upsert_and_box():
    store = {"classes": ["cpu_installed"], "images": []}
    image = upsert_image(store, path="image.jpg", item_id="1")
    assert image["image_id"] == image_id("image.jpg")
    add_box(image, label="cpu_installed", box=[1, 2, 10, 20], reviewer="tester")
    assert image["review"]["status"] == "labeled"
    assert len(image["annotations"]) == 1

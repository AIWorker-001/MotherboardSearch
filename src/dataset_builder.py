#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Any


def validate_annotation_store(store: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    classes = set(store.get("classes", []))
    for image in store.get("images", []):
        if not Path(image["path"]).exists():
            errors.append(f"missing_image:{image['path']}")
        for annotation in image.get("annotations", []):
            if annotation["label"] not in classes:
                errors.append(f"unknown_class:{annotation['label']}")
            x1, y1, x2, y2 = annotation["box"]
            if x2 <= x1 or y2 <= y1:
                errors.append(f"invalid_box:{image['image_id']}")
    return errors


def split_images(images: list[dict[str, Any]], train: float, validation: float, seed: int) -> dict[str, list[dict[str, Any]]]:
    rows = list(images)
    random.Random(seed).shuffle(rows)
    train_end = int(len(rows) * train)
    validation_end = train_end + int(len(rows) * validation)
    return {"train": rows[:train_end], "val": rows[train_end:validation_end], "test": rows[validation_end:]}


def yolo_line(annotation: dict[str, Any], class_index: int, width: float, height: float) -> str:
    x1, y1, x2, y2 = (float(value) for value in annotation["box"])
    center_x = ((x1 + x2) / 2.0) / width
    center_y = ((y1 + y2) / 2.0) / height
    box_width = (x2 - x1) / width
    box_height = (y2 - y1) / height
    return f"{class_index} {center_x:.8f} {center_y:.8f} {box_width:.8f} {box_height:.8f}"


def build_dataset(store: dict[str, Any], output: Path, train: float, validation: float, seed: int) -> dict[str, int]:
    from PIL import Image

    labeled = [row for row in store["images"] if row.get("annotations")]
    splits = split_images(labeled, train, validation, seed)
    class_to_index = {label: index for index, label in enumerate(store["classes"])}
    counts = {}
    for split, rows in splits.items():
        image_dir = output / "images" / split
        label_dir = output / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        for row in rows:
            source = Path(row["path"])
            target = image_dir / f"{row['image_id']}{source.suffix.lower()}"
            shutil.copy2(source, target)
            with Image.open(source) as image:
                width, height = image.size
            lines = [yolo_line(annotation, class_to_index[annotation["label"]], width, height) for annotation in row["annotations"]]
            (label_dir / f"{row['image_id']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[split] = len(rows)
    names = "\n".join(f"  {index}: {label}" for index, label in enumerate(store["classes"]))
    (output / "dataset.yaml").write_text(
        f"path: {output.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n",
        encoding="utf-8",
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reproducible YOLO dataset from reviewed annotations")
    parser.add_argument("--annotations", type=Path, default=Path("data/annotations/annotations.json"))
    parser.add_argument("--config", type=Path, default=Path("config/training.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    store = json.loads(args.annotations.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))["dataset"]
    errors = validate_annotation_store(store)
    if errors:
        raise ValueError(";".join(errors))
    counts = build_dataset(store, args.output, float(config["train_ratio"]), float(config["validation_ratio"]), int(config["seed"]))
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from object_detector import DetectionConfig, ZeroShotHardwareDetector, aggregate_evidence, annotate_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Spatial hardware detector for motherboard listing photos")
    parser.add_argument("--manifest", type=Path, required=True, help="JSON with item id/title and local image paths")
    parser.add_argument("--config", type=Path, default=Path("config/detection_classes.json"))
    parser.add_argument("--model", default="IDEA-Research/grounding-dino-tiny")
    parser.add_argument("--output", type=Path, default=Path("output/phase2_report.json"))
    parser.add_argument("--annotated-dir", type=Path, default=Path("output/annotated"))
    args = parser.parse_args()

    config = DetectionConfig.load(args.config)
    detector = ZeroShotHardwareDetector(config, args.model)
    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = []
    for item in items:
        all_detections = []
        image_reports = []
        for index, filename in enumerate(item.get("images", []), start=1):
            path = Path(filename)
            image = Image.open(path).convert("RGB")
            detections = detector.detect(image, image_index=index)
            all_detections.extend(detections)
            annotation_path = args.annotated_dir / str(item["id"]) / f"{index:02d}.jpg"
            annotate_image(image, detections, annotation_path)
            image_reports.append({"image": str(path), "annotated": str(annotation_path), "detection_count": len(detections)})
        evidence = aggregate_evidence(all_detections)
        report.append({"item_id": str(item["id"]), "title": item.get("title", ""), **evidence, "images": image_reports})
        print(f"{item['id']} | {evidence['cpu_state']} | score={evidence['value_score']} review={evidence['needs_review']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

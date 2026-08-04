#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from detection_fusion import fused_decision, generate_tiles, geometry_filter, translate_detection
from object_detector import DetectionConfig, ZeroShotHardwareDetector, annotate_image, non_max_suppression


def main() -> int:
    parser = argparse.ArgumentParser(description="Spatial hardware detector with multi-scale multi-image evidence fusion")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/detection_classes.json"))
    parser.add_argument("--fusion-config", type=Path, default=Path("config/detection_fusion.json"))
    parser.add_argument("--model", default="IDEA-Research/grounding-dino-tiny")
    parser.add_argument("--output", type=Path, default=Path("output/phase2_report.json"))
    parser.add_argument("--annotated-dir", type=Path, default=Path("output/annotated"))
    parser.add_argument("--passes", default="socket_state,cooler,cooler_structure,component,damage", help="Comma-separated detector groups")
    args = parser.parse_args()

    config = DetectionConfig.load(args.config)
    fusion_config = json.loads(args.fusion_config.read_text(encoding="utf-8"))
    detector = ZeroShotHardwareDetector(config, args.model)
    passes = [value.strip() for value in args.passes.split(",") if value.strip()]
    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = []

    for item in items:
        all_detections = []
        image_reports = []
        for index, filename in enumerate(item.get("images", []), start=1):
            path = Path(filename)
            image = Image.open(path).convert("RGB")
            image_detections = []
            tiling = fusion_config["tiling"]
            tiles = generate_tiles(image, int(tiling["tile_size"]), float(tiling["overlap"])) if tiling.get("enabled") and max(image.size) >= int(tiling["minimum_side"]) else [("full", (0, 0, image.width, image.height), image)]
            for tile_name, box, tile in tiles:
                for detector_group in passes:
                    detections = detector.detect(
                        tile,
                        image_index=index,
                        threshold=0.18 if tile_name != "full" else 0.20,
                        groups={detector_group},
                    )
                    image_detections.extend(translate_detection(row, box[0], box[1]) for row in detections)
            image_detections = geometry_filter(image_detections, image.size, fusion_config["geometry"])
            image_detections = non_max_suppression(image_detections, iou_threshold=0.40)
            all_detections.extend(image_detections)
            annotation_path = args.annotated_dir / str(item["id"]) / f"{index:02d}.jpg"
            annotate_image(image, image_detections, annotation_path)
            image_reports.append({
                "image": str(path),
                "annotated": str(annotation_path),
                "detection_count": len(image_detections),
                "tiles_evaluated": len(tiles),
                "passes_evaluated": passes,
            })
        evidence = fused_decision(all_detections, fusion_config["fusion"])
        report.append({"item_id": str(item["id"]), "title": item.get("title", ""), **evidence, "images": image_reports})
        print(f"{item['id']} | {evidence['cpu_state']} | confidence={evidence['cpu_confidence']:.3f} | score={evidence['value_score']} review={evidence['needs_review']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

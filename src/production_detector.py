#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .object_detector import Detection, aggregate_evidence
    from .model_integrity import verify_registered_model
except ImportError:
    from object_detector import Detection, aggregate_evidence
    from model_integrity import verify_registered_model


def stable_bucket(item_id: str) -> float:
    value = int(hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8], 16)
    return value / 0xFFFFFFFF


def load_active_model(registry_path: Path) -> dict[str, Any] | None:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    active = registry.get("active_model")
    if not active:
        return None
    return next((model for model in registry.get("models", []) if model.get("name") == active), None)


def yolo_to_detections(result: Any, image_index: int) -> list[Detection]:
    detections: list[Detection] = []
    names = result.names
    boxes = result.boxes
    if boxes is None:
        return detections
    for xyxy, confidence, class_id in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
        label = str(names[int(class_id)])
        detections.append(Detection(label, round(float(confidence), 4), tuple(float(value) for value in xyxy), label, image_index))
    return detections


def run_trained_model(weights: Path, images: list[str]) -> dict[str, Any]:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError("ultralytics is required for trained-model inference") from error
    model = YOLO(str(weights))
    detections: list[Detection] = []
    image_rows = []
    for index, filename in enumerate(images, start=1):
        image = Image.open(filename).convert("RGB")
        prediction = model.predict(source=image, verbose=False)[0]
        rows = yolo_to_detections(prediction, index)
        detections.extend(rows)
        image_rows.append({"image": filename, "detection_count": len(rows)})
    evidence = aggregate_evidence(detections)
    evidence["images"] = image_rows
    return evidence


def select_backend(item_id: str, deployment: dict[str, Any], active_model: dict[str, Any] | None) -> str:
    mode = deployment.get("mode", "auto")
    if mode == "fallback" or active_model is None:
        return "fallback"
    if mode == "trained":
        return "trained"
    return "trained" if stable_bucket(item_id) < float(deployment.get("canary_fraction", 0.0)) else "fallback"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run promoted detector with deterministic canary and fallback routing")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, default=Path("config/deployment.json"))
    parser.add_argument("--fallback-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
    registry_path = Path(deployment["registry"])
    active_model = load_active_model(registry_path)
    active_model_error = None
    if active_model is not None:
        valid, active_model_error, resolved_weights = verify_registered_model(active_model, Path.cwd())
        if valid:
            active_model = dict(active_model)
            active_model["weights"] = str(resolved_weights)
        else:
            active_model = None
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fallback = {str(row["item_id"]): row for row in json.loads(args.fallback_results.read_text(encoding="utf-8"))}
    output = []
    for item in manifest:
        item_id = str(item["id"])
        backend = select_backend(item_id, deployment, active_model)
        if backend == "trained":
            try:
                result = run_trained_model(Path(active_model["weights"]), item.get("images", []))
                result.update({"item_id": item_id, "title": item.get("title", ""), "inference_backend": "trained", "model_name": active_model["name"]})
            except Exception as error:
                result = dict(fallback[item_id])
                result.update({"inference_backend": "fallback_after_error", "model_name": active_model["name"], "trained_error": str(error), "needs_review": True})
        else:
            result = dict(fallback[item_id])
            result.update({"inference_backend": "fallback", "model_name": None})
            if active_model_error:
                result["trained_model_unavailable"] = active_model_error
                result["needs_review"] = True
        output.append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(output), "trained": sum(row["inference_backend"] == "trained" for row in output), "fallback": sum(row["inference_backend"] != "trained" for row in output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

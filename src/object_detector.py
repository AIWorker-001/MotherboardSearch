#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
from PIL import Image, ImageDraw
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    box: tuple[float, float, float, float]
    query: str
    image_index: int | None = None

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


@dataclass
class DetectionConfig:
    classes: dict[str, dict[str, Any]]
    schema_version: int = 1

    @classmethod
    def load(cls, path: Path) -> "DetectionConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(classes=raw["classes"], schema_version=int(raw.get("schema_version", 1)))

    def queries(self) -> list[str]:
        return [query for spec in self.classes.values() for query in spec["queries"]]

    def query_to_class(self) -> dict[str, str]:
        return {query: label for label, spec in self.classes.items() for query in spec["queries"]}


def box_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    ix1, iy1 = max(lx1, rx1), max(ly1, ry1)
    ix2, iy2 = min(lx2, rx2), min(ly2, ry2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    left_area = max(0.0, lx2 - lx1) * max(0.0, ly2 - ly1)
    right_area = max(0.0, rx2 - rx1) * max(0.0, ry2 - ry1)
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def non_max_suppression(detections: Iterable[Detection], iou_threshold: float = 0.45) -> list[Detection]:
    kept: list[Detection] = []
    for detection in sorted(detections, key=lambda item: item.score, reverse=True):
        if all(detection.label != prior.label or box_iou(detection.box, prior.box) < iou_threshold for prior in kept):
            kept.append(detection)
    return kept


class ZeroShotHardwareDetector:
    def __init__(
        self,
        config: DetectionConfig,
        model_name: str = "IDEA-Research/grounding-dino-tiny",
        device: str | None = None,
    ) -> None:
        self.config = config
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self._query_to_class = config.query_to_class()

    def detect(self, image: Image.Image, *, image_index: int | None = None, threshold: float = 0.20) -> list[Detection]:
        queries = self.config.queries()
        inputs = self.processor(images=image, text=queries, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        target_sizes = torch.tensor([[image.height, image.width]], device=self.device)
        processed = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=threshold,
            text_threshold=threshold,
            target_sizes=target_sizes,
        )[0]
        detections: list[Detection] = []
        for score, box, text_label in zip(processed["scores"], processed["boxes"], processed["text_labels"]):
            query = str(text_label)
            label = self._query_to_class.get(query)
            if label is None:
                # Grounding DINO may normalize punctuation; select the closest exact-containing query.
                label = next((self._query_to_class[q] for q in queries if query.lower() in q.lower() or q.lower() in query.lower()), None)
            if label is None:
                continue
            confidence = float(score)
            if confidence < float(self.config.classes[label]["threshold"]):
                continue
            detections.append(Detection(label, round(confidence, 4), tuple(float(value) for value in box.tolist()), query, image_index))
        return non_max_suppression(detections)


def aggregate_evidence(detections: Iterable[Detection]) -> dict[str, Any]:
    rows = list(detections)
    maxima: dict[str, float] = {}
    counts: dict[str, int] = {}
    for detection in rows:
        maxima[detection.label] = max(maxima.get(detection.label, 0.0), detection.score)
        counts[detection.label] = counts.get(detection.label, 0) + 1

    cooler_labels = ("intel_stock_cooler", "amd_wraith_cooler", "tower_cpu_cooler", "aio_pump_block")
    cooler_score = max((maxima.get(label, 0.0) for label in cooler_labels), default=0.0)
    installed_score = maxima.get("cpu_installed", 0.0)
    empty_score = max(maxima.get("empty_lga_socket", 0.0), maxima.get("empty_amd_socket", 0.0))
    cover_score = maxima.get("socket_cover", 0.0)
    damage_score = max(maxima.get("bent_socket_pins", 0.0), maxima.get("burn_damage", 0.0), maxima.get("cracked_pcb", 0.0))

    if cooler_score >= 0.45:
        cpu_state, confidence = "cooler_attached_cpu_highly_likely", cooler_score
    elif installed_score >= 0.45 and installed_score >= empty_score + 0.08:
        cpu_state, confidence = "visible_cpu_likely", installed_score
    elif empty_score >= 0.45 and empty_score >= installed_score + 0.08:
        cpu_state, confidence = "empty_socket_likely", empty_score
    elif cover_score >= 0.45:
        cpu_state, confidence = "socket_cover_likely", cover_score
    else:
        cpu_state, confidence = "unclear", max(cooler_score, installed_score, empty_score, cover_score)

    review_reasons: list[str] = []
    if cpu_state == "unclear":
        review_reasons.append("socket_state_unclear")
    if 0.35 <= abs(installed_score - empty_score) + max(installed_score, empty_score) < 0.60:
        review_reasons.append("borderline_socket_evidence")
    if damage_score >= 0.38:
        review_reasons.append("possible_physical_damage")

    score = 0
    if cpu_state == "cooler_attached_cpu_highly_likely":
        score += 100
    elif cpu_state == "visible_cpu_likely":
        score += 80
    elif cpu_state == "empty_socket_likely":
        score -= 100
    elif cpu_state == "socket_cover_likely":
        score -= 60
    if maxima.get("ram_dimm", 0.0) >= 0.38:
        score += 35
    if maxima.get("nvme_ssd", 0.0) >= 0.38:
        score += 25
    if damage_score >= 0.38:
        score -= 100

    return {
        "cpu_state": cpu_state,
        "cpu_confidence": round(confidence, 4),
        "value_score": score,
        "maxima": {key: round(value, 4) for key, value in sorted(maxima.items())},
        "counts": counts,
        "damage_score": round(damage_score, 4),
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "detections": [asdict(row) for row in rows],
    }


def annotate_image(image: Image.Image, detections: Iterable[Detection], output: Path) -> None:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for detection in detections:
        draw.rectangle(detection.box, width=4)
        draw.text((detection.box[0] + 4, detection.box[1] + 4), f"{detection.label} {detection.score:.2f}")
    output.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(output, quality=90)

#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any, Iterable

from PIL import Image

try:
    from .object_detector import Detection, non_max_suppression
except ImportError:
    from object_detector import Detection, non_max_suppression

COOLERS = {"intel_stock_cooler", "amd_wraith_cooler", "tower_cpu_cooler", "aio_pump_block"}
SOCKET_INSTALLED = {"cpu_installed"}
SOCKET_EMPTY = {"empty_lga_socket", "empty_amd_socket", "exposed_lga_contact_field", "lga_center_rectangle", "open_lga_retention_frame"}
LGA_EMPTY_CUES = {"empty_lga_socket", "exposed_lga_contact_field", "lga_center_rectangle", "open_lga_retention_frame"}
DAMAGE = {"bent_socket_pins", "burn_damage", "cracked_pcb"}


def generate_tiles(image: Image.Image, tile_size: int, overlap: float) -> list[tuple[str, tuple[int, int, int, int], Image.Image]]:
    width, height = image.size
    if max(width, height) <= tile_size:
        return [("full", (0, 0, width, height), image)]
    stride = max(1, int(tile_size * (1.0 - overlap)))
    xs = list(range(0, max(1, width - tile_size + 1), stride))
    ys = list(range(0, max(1, height - tile_size + 1), stride))
    if not xs or xs[-1] + tile_size < width:
        xs.append(max(0, width - tile_size))
    if not ys or ys[-1] + tile_size < height:
        ys.append(max(0, height - tile_size))
    rows = [("full", (0, 0, width, height), image)]
    seen = set()
    for y in ys:
        for x in xs:
            box = (x, y, min(width, x + tile_size), min(height, y + tile_size))
            if box in seen:
                continue
            seen.add(box)
            rows.append((f"tile-{x}-{y}", box, image.crop(box)))
    return rows


def translate_detection(detection: Detection, offset_x: int, offset_y: int) -> Detection:
    x1, y1, x2, y2 = detection.box
    return Detection(
        detection.label,
        detection.score,
        (x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y),
        detection.query,
        detection.image_index,
    )


def geometry_filter(detections: Iterable[Detection], image_size: tuple[int, int], config: dict[str, Any]) -> list[Detection]:
    width, height = image_size
    image_area = max(1.0, float(width * height))
    output = []
    for detection in detections:
        ratio = detection.area / image_area
        minimum = float(config["minimum_area_ratio"])
        if detection.label in COOLERS:
            minimum = max(minimum, float(config["cooler_minimum_area_ratio"]))
            box_width = max(0.0, detection.box[2] - detection.box[0])
            box_height = max(0.0, detection.box[3] - detection.box[1])
            width_ratio = box_width / max(1.0, float(width))
            height_ratio = box_height / max(1.0, float(height))
            if ratio > float(config.get("cooler_maximum_area_ratio", config["maximum_area_ratio"])):
                continue
            if width_ratio > float(config.get("cooler_maximum_width_ratio", 1.0)):
                continue
            if height_ratio > float(config.get("cooler_maximum_height_ratio", 1.0)):
                continue
        elif detection.label in SOCKET_INSTALLED | SOCKET_EMPTY | {"socket_cover", "bent_socket_pins"}:
            minimum = max(minimum, float(config["socket_minimum_area_ratio"]))
        if minimum <= ratio <= float(config["maximum_area_ratio"]):
            output.append(detection)
    return output


def evidence_by_label(detections: Iterable[Detection], fusion: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Detection]] = defaultdict(list)
    for detection in detections:
        grouped[detection.label].append(detection)
    evidence = {}
    for label, rows in grouped.items():
        by_image: dict[int | None, float] = {}
        for row in rows:
            by_image[row.image_index] = max(by_image.get(row.image_index, 0.0), row.score)
        ordered = sorted(by_image.values(), reverse=True)
        score = ordered[0]
        if len(ordered) > 1:
            score += float(fusion["additional_image_weight"]) * sum(ordered[1:]) / max(1, len(ordered) - 1)
            score += float(fusion["corroboration_bonus"]) * min(2, len(ordered) - 1)
        evidence[label] = {
            "score": round(min(1.0, score), 4),
            "max_score": round(max(ordered), 4),
            "distinct_images": len(ordered),
            "detections": len(rows),
        }
    return evidence


def fused_decision(detections: Iterable[Detection], fusion: dict[str, Any]) -> dict[str, Any]:
    rows = list(detections)
    evidence = evidence_by_label(rows, fusion)

    def best(labels: set[str]) -> tuple[str | None, float, int]:
        choices = [(label, evidence.get(label, {}).get("score", 0.0), evidence.get(label, {}).get("distinct_images", 0)) for label in labels]
        return max(choices, key=lambda row: row[1], default=(None, 0.0, 0))

    cooler_label, cooler_score, cooler_images = best(COOLERS)
    installed_label, installed_score, installed_images = best(SOCKET_INSTALLED)
    empty_label, empty_score, empty_images = best(SOCKET_EMPTY)
    lga_cue_rows = [evidence[label] for label in LGA_EMPTY_CUES if label in evidence]
    if lga_cue_rows:
        lga_scores = sorted((float(row["score"]) for row in lga_cue_rows), reverse=True)
        lga_images = len({d.image_index for d in rows if d.label in LGA_EMPTY_CUES})
        lga_score = lga_scores[0]
        if len(lga_scores) > 1:
            lga_score += 0.18 * sum(lga_scores[1:]) / (len(lga_scores) - 1)
            lga_score += 0.05 * min(2, len(lga_scores) - 1)
        if lga_images > 1:
            lga_score += 0.05 * min(2, lga_images - 1)
        lga_score = min(1.0, lga_score)
        if lga_score > empty_score:
            empty_label, empty_score, empty_images = "empty_lga_visual_cues", round(lga_score, 4), lga_images
            evidence["empty_lga_visual_cues"] = {
                "score": round(lga_score, 4),
                "max_score": round(lga_scores[0], 4),
                "distinct_images": lga_images,
                "detections": sum(int(row["detections"]) for row in lga_cue_rows),
                "cue_labels": sorted(label for label in LGA_EMPTY_CUES if label in evidence),
            }
    cover_score = evidence.get("socket_cover", {}).get("score", 0.0)
    strong = float(fusion["strong_threshold"])
    moderate = float(fusion["moderate_threshold"])
    margin = float(fusion["conflict_margin"])

    review_reasons: list[str] = []
    conflict = installed_score >= moderate and empty_score >= moderate and abs(installed_score - empty_score) < margin
    empty_override_threshold = float(fusion.get("empty_socket_override_threshold", strong))
    empty_override_margin = float(fusion.get("empty_socket_override_margin", margin))
    cooler_single_min = float(fusion.get("cooler_minimum_single_score", strong))
    cooler_multi_min = float(fusion.get("cooler_minimum_corroborated_score", strong))
    # Socket evidence is physically primary. A clearly open socket means there is
    # no CPU and therefore no attached cooler, even if broad visual prompts
    # produce repeated weak cooler-like detections elsewhere on the board.
    if empty_score >= empty_override_threshold and empty_score >= installed_score + empty_override_margin:
        cpu_state = "empty_socket_likely"
        confidence = empty_score
        if cooler_score >= moderate:
            review_reasons.append("cooler_evidence_rejected_by_empty_socket")
    elif cover_score >= empty_override_threshold and cover_score >= installed_score + empty_override_margin:
        cpu_state = "socket_cover_likely"
        confidence = cover_score
        if cooler_score >= moderate:
            review_reasons.append("cooler_evidence_rejected_by_socket_cover")
    elif conflict:
        cpu_state = "unclear"
        confidence = max(installed_score, empty_score)
        review_reasons.append("conflicting_socket_evidence")
    elif cooler_score >= cooler_single_min and cooler_images >= 1:
        cpu_state = "cooler_attached_cpu_highly_likely"
        confidence = cooler_score
    elif installed_score >= strong and installed_score >= empty_score + margin:
        cpu_state = "visible_cpu_likely"
        confidence = installed_score
    elif empty_score >= strong and empty_score >= installed_score + margin:
        cpu_state = "empty_socket_likely"
        confidence = empty_score
    elif cooler_score >= cooler_multi_min and cooler_images >= 2:
        cpu_state = "cooler_attached_cpu_highly_likely"
        confidence = cooler_score
    elif installed_score >= moderate and installed_images >= 2 and installed_score >= empty_score + margin:
        cpu_state = "visible_cpu_likely"
        confidence = installed_score
    elif empty_score >= moderate and empty_images >= 2 and empty_score >= installed_score + margin:
        cpu_state = "empty_socket_likely"
        confidence = empty_score
    else:
        cpu_state = "unclear"
        confidence = max(cooler_score, installed_score, empty_score, cover_score)
        review_reasons.append("socket_state_unclear")

    damage_labels = []
    damage_score = 0.0
    for label in DAMAGE:
        row = evidence.get(label, {})
        score = float(row.get("score", 0.0))
        images = int(row.get("distinct_images", 0))
        if score >= strong and images >= int(fusion["minimum_distinct_images_for_damage"]):
            damage_labels.append(label)
            damage_score = max(damage_score, score)
    if damage_labels:
        review_reasons.append("possible_physical_damage")

    maxima = {label: values["score"] for label, values in evidence.items()}
    score = 0
    if cpu_state == "cooler_attached_cpu_highly_likely": score += 100
    elif cpu_state == "visible_cpu_likely": score += 80
    elif cpu_state == "empty_socket_likely": score -= 100
    elif cpu_state == "socket_cover_likely": score -= 60
    if evidence.get("ram_dimm", {}).get("score", 0.0) >= moderate: score += 35
    if evidence.get("nvme_ssd", {}).get("score", 0.0) >= moderate: score += 25
    if damage_labels: score -= 100

    return {
        "cpu_state": cpu_state,
        "cpu_confidence": round(confidence, 4),
        "value_score": score,
        "maxima": maxima,
        "evidence": evidence,
        "damage_score": round(damage_score, 4),
        "damage_labels": sorted(damage_labels),
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "detections": [asdict(row) for row in rows],
    }

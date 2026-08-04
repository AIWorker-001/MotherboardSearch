#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

PROMPTS = {
    "intel_cooler": "a motherboard with an Intel stock CPU cooler and fan mounted over the processor",
    "amd_cooler": "a motherboard with an AMD Wraith CPU cooler and fan mounted over the processor",
    "tower_cooler": "a motherboard with a tower CPU heatsink and fan mounted over the processor",
    "cpu_visible": "a motherboard with a silver metal CPU visibly installed in the socket",
    "empty_socket": "a motherboard with an empty CPU socket",
    "socket_cover": "a motherboard with a black plastic CPU socket cover",
    "ram": "a motherboard with RAM memory modules installed",
    "nvme": "a motherboard with an M.2 NVMe SSD installed",
    "none": "a motherboard without a CPU cooler or visible CPU",
}


@dataclass
class DetectionResult:
    item_id: str
    title: str
    cpu_state: str
    value_score: int
    maxima: dict[str, float]
    gallery_count: int
    images: list[dict[str, Any]]


def score_state(maxima: dict[str, float]) -> tuple[str, int]:
    cooler = max(maxima["intel_cooler"], maxima["amd_cooler"], maxima["tower_cooler"])
    cpu = maxima["cpu_visible"]
    empty = maxima["empty_socket"]
    cover = maxima["socket_cover"]

    if cooler >= 0.62 and cooler > max(empty, cover) + 0.08:
        state, score = "cooler_attached_cpu_highly_likely", 100
    elif cpu >= 0.68 and cpu > empty + 0.08:
        state, score = "visible_cpu_likely", 80
    elif empty >= 0.66 and empty > cpu + 0.08:
        state, score = "empty_socket_likely", -100
    elif cover >= 0.66:
        state, score = "socket_cover_likely", -60
    else:
        state, score = "unclear", 0

    if maxima["ram"] >= 0.60:
        score += 35
    if maxima["nvme"] >= 0.60:
        score += 25
    return state, score


def make_crops(image: Image.Image) -> list[tuple[str, Image.Image]]:
    width, height = image.size
    crops: list[tuple[str, Image.Image]] = [("full", image)]
    for grid in (2, 3):
        crop_w, crop_h = width // grid, height // grid
        for y in range(grid):
            for x in range(grid):
                box = (
                    max(0, x * crop_w - crop_w // 6),
                    max(0, y * crop_h - crop_h // 6),
                    min(width, (x + 1) * crop_w + crop_w // 6),
                    min(height, (y + 1) * crop_h + crop_h // 6),
                )
                crops.append((f"g{grid}-{x}-{y}", image.crop(box)))
    return crops


def analyze(galleries_path: Path, output_path: Path, cache_dir: Path) -> list[DetectionResult]:
    items = json.loads(galleries_path.read_text(encoding="utf-8"))
    labels = list(PROMPTS)
    prompts = [PROMPTS[label] for label in labels]
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model.eval()
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: list[DetectionResult] = []

    for item in items:
        per_image: list[dict[str, Any]] = []
        for index, url in enumerate(item.get("urls", []), start=1):
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
            image_path = cache_dir / f"{item['id']}_{index}.jpg"
            image.save(image_path, quality=90)

            best = {label: {"score": 0.0, "crop": None} for label in labels}
            for crop_name, crop in make_crops(image):
                inputs = processor(text=prompts, images=crop, return_tensors="pt", padding=True)
                with torch.no_grad():
                    probabilities = model(**inputs).logits_per_image.softmax(dim=1)[0].tolist()
                for label, probability in zip(labels, probabilities):
                    if probability > best[label]["score"]:
                        best[label] = {"score": round(float(probability), 4), "crop": crop_name}

            ocr = ""
            try:
                ocr = subprocess.run(
                    ["tesseract", str(image_path), "stdout"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                ).stdout
            except (OSError, subprocess.SubprocessError):
                pass
            per_image.append({"image": index, "url": url, "best": best, "ocr": ocr[:300]})

        maxima = {
            label: max((image["best"][label]["score"] for image in per_image), default=0.0)
            for label in labels
        }
        cpu_state, value_score = score_state(maxima)
        result = DetectionResult(
            item_id=str(item["id"]),
            title=item.get("title", ""),
            cpu_state=cpu_state,
            value_score=value_score,
            maxima={key: round(value, 3) for key, value in maxima.items()},
            gallery_count=len(item.get("urls", [])),
            images=per_image,
        )
        results.append(result)
        print(
            f"{result.item_id} | {result.cpu_state} | score={result.value_score} "
            f"| cooler={max(maxima['intel_cooler'], maxima['amd_cooler'], maxima['tower_cooler']):.3f} "
            f"cpu={maxima['cpu_visible']:.3f} empty={maxima['empty_socket']:.3f} "
            f"cover={maxima['socket_cover']:.3f} ram={maxima['ram']:.3f} nvme={maxima['nvme']:.3f}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Score ShopGoodwill motherboard galleries for AIWorker value")
    parser.add_argument("--galleries", type=Path, required=True, help="JSON produced by collect_true_galleries.js")
    parser.add_argument("--output", type=Path, default=Path("output/worker_value_report.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("cache/images"))
    args = parser.parse_args()
    analyze(args.galleries, args.output, args.cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

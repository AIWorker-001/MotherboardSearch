#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from .detection_fusion import fused_decision, geometry_filter
    from .listing_context import apply_listing_context
    from .object_detector import Detection, DetectionConfig, ZeroShotHardwareDetector, non_max_suppression
except ImportError:
    from detection_fusion import fused_decision, geometry_filter
    from listing_context import apply_listing_context
    from object_detector import Detection, DetectionConfig, ZeroShotHardwareDetector, non_max_suppression

SOCKET_LOCATOR_LABELS = {'intel_lga_socket', 'amd_cpu_socket', 'cpu_socket_region'}
COOLER_LOCATOR_LABELS = {'mounted_cpu_cooler_region'}
STATE_GROUPS = {'socket_state', 'damage'}
COOLER_GROUPS = {'cooler', 'cooler_structure'}


def expand_box(box: tuple[float, float, float, float], image_size: tuple[int, int], padding: float) -> tuple[int, int, int, int]:
    width, height = image_size
    x1, y1, x2, y2 = box
    pad_x = max(8.0, (x2 - x1) * padding)
    pad_y = max(8.0, (y2 - y1) * padding)
    return (
        max(0, int(x1 - pad_x)),
        max(0, int(y1 - pad_y)),
        min(width, int(x2 + pad_x)),
        min(height, int(y2 + pad_y)),
    )


def best_localization(rows: list[Detection], image_size: tuple[int, int], config: dict[str, Any]) -> dict[str, Any] | None:
    width, height = image_size
    image_area = max(1.0, float(width * height))
    minimum = float(config.get('minimum_socket_area_ratio', 0.008))
    maximum = float(config.get('maximum_socket_area_ratio', 0.30))
    candidates = []
    for row in rows:
        ratio = row.area / image_area
        if row.label not in SOCKET_LOCATOR_LABELS | COOLER_LOCATOR_LABELS:
            continue
        if not minimum <= ratio <= maximum:
            continue
        source = 'cooler_obscured' if row.label in COOLER_LOCATOR_LABELS else 'socket_visible'
        candidates.append((row.score, 1 if source == 'socket_visible' else 0, row, source, ratio))
    if not candidates:
        return None
    _, _, detection, source, ratio = max(candidates, key=lambda value: (value[0], value[1]))
    return {
        'label': detection.label,
        'score': detection.score,
        'box': list(detection.box),
        'query': detection.query,
        'source': source,
        'area_ratio': round(ratio, 5),
    }


def classify_socket_crop(
    crop: Image.Image,
    detector: ZeroShotHardwareDetector,
    fusion_config: dict[str, Any],
    image_index: int,
    title: str,
    listing_context_config: dict[str, Any],
    localization_source: str,
) -> tuple[dict[str, Any], list[Detection]]:
    state_rows = detector.detect(crop, image_index=image_index, threshold=0.14, groups=STATE_GROUPS)
    state_rows = geometry_filter(state_rows, crop.size, fusion_config['geometry'])
    cooler_rows = detector.detect(crop, image_index=image_index, threshold=0.14, groups=COOLER_GROUPS)
    cooler_rows = geometry_filter(cooler_rows, crop.size, fusion_config['geometry'])
    rows = non_max_suppression(state_rows + cooler_rows, iou_threshold=0.40)
    evidence = fused_decision(rows, fusion_config['fusion'])
    evidence = apply_listing_context(evidence, title, listing_context_config)
    evidence['localization_source'] = localization_source
    return evidence, rows


def detect_item(
    item: dict[str, Any],
    detector: ZeroShotHardwareDetector,
    fusion_config: dict[str, Any],
    socket_config: dict[str, Any],
    listing_context_config: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    image_results = []
    focused_evidence = []
    for index, filename in enumerate(item.get('images', []), start=1):
        path = Path(filename)
        image = Image.open(path).convert('RGB')
        locator_rows = detector.detect(image, image_index=index, threshold=float(socket_config.get('localization_threshold', 0.18)), groups={'socket_locator'})
        locator_rows = non_max_suppression(locator_rows, iou_threshold=0.35)
        localization = best_localization(locator_rows, image.size, socket_config)
        if localization is None:
            image_results.append({'image': str(path), 'status': 'socket_not_found', 'locator_detections': [asdict(row) for row in locator_rows]})
            continue
        bounds = expand_box(tuple(localization['box']), image.size, float(socket_config.get('crop_padding', 0.18)))
        crop = image.crop(bounds)
        evidence, rows = classify_socket_crop(
            crop,
            detector,
            fusion_config,
            index,
            str(item.get('title') or ''),
            listing_context_config,
            localization['source'],
        )
        crop_path = output_dir / str(item['id']) / f'{index:02d}-socket.jpg'
        overlay_path = output_dir / str(item['id']) / f'{index:02d}-overlay.jpg'
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(crop_path, quality=92)
        overlay = image.copy()
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(bounds, outline='red', width=6)
        draw.text((bounds[0] + 6, bounds[1] + 6), f"socket ROI {evidence['cpu_state']} {evidence['cpu_confidence']:.2f}")
        overlay.save(overlay_path, quality=90)
        focused_evidence.append(evidence)
        image_results.append({
            'image': str(path),
            'status': 'socket_classified',
            'localization': localization,
            'bounds': list(bounds),
            'crop': str(crop_path),
            'overlay': str(overlay_path),
            'classification': evidence,
            'detections': [asdict(row) for row in rows],
        })
    if not focused_evidence:
        final = {
            'cpu_state': 'socket_not_found',
            'cpu_confidence': 0.0,
            'needs_review': True,
            'review_reasons': ['cpu_socket_not_found'],
            'value_score': 0,
        }
    else:
        actionable = [row for row in focused_evidence if row.get('cpu_state') not in {'unclear', 'unavailable'}]
        choices = actionable or focused_evidence
        final = max(choices, key=lambda row: float(row.get('cpu_confidence') or 0.0))
    return {
        'item_id': str(item['id']),
        'title': item.get('title', ''),
        'detector_source': 'socket_first',
        'socket_localized_images': sum(row['status'] == 'socket_classified' for row in image_results),
        'images_evaluated': len(image_results),
        **{key: value for key, value in final.items() if key not in {'detections'}},
        'images': image_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Locate the CPU socket first, then classify only the socket region')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/detection_classes.json'))
    parser.add_argument('--fusion-config', type=Path, default=Path('config/detection_fusion.json'))
    parser.add_argument('--socket-config', type=Path, default=Path('config/socket_first.json'))
    parser.add_argument('--listing-context-config', type=Path, default=Path('config/listing_context.json'))
    parser.add_argument('--model', default='IDEA-Research/grounding-dino-tiny')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    args = parser.parse_args()
    detector = ZeroShotHardwareDetector(DetectionConfig.load(args.config), args.model)
    fusion_config = json.loads(args.fusion_config.read_text(encoding='utf-8'))
    socket_config = json.loads(args.socket_config.read_text(encoding='utf-8'))
    listing_context_config = json.loads(args.listing_context_config.read_text(encoding='utf-8'))
    items = json.loads(args.manifest.read_text(encoding='utf-8'))
    rows = [detect_item(item, detector, fusion_config, socket_config, listing_context_config, args.artifact_dir) for item in items]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'items': len(rows), 'socket_found': sum(row['socket_localized_images'] > 0 for row in rows)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .detection_fusion import fused_decision, geometry_filter
    from .object_detector import DetectionConfig, ZeroShotHardwareDetector, annotate_image, non_max_suppression
except ImportError:
    from detection_fusion import fused_decision, geometry_filter
    from object_detector import DetectionConfig, ZeroShotHardwareDetector, annotate_image, non_max_suppression

SOCKET_REGION_NAMES = {'cpu_socket', 'socket', 'processor_socket'}
FOCUSED_GROUPS = {'socket_state', 'cooler', 'cooler_structure', 'damage'}


def socket_crops(verification: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in verification.get('region_crops', [])
        if str(row.get('name', '')).lower() in SOCKET_REGION_NAMES and row.get('crop')
    ]


def detect_socket_regions(
    verification_rows: list[dict[str, Any]],
    detector: ZeroShotHardwareDetector,
    fusion_config: dict[str, Any],
    annotated_dir: Path,
) -> list[dict[str, Any]]:
    output = []
    for verification in verification_rows:
        item_id = str(verification['item_id'])
        crops = socket_crops(verification)
        detections = []
        crop_reports = []
        for index, crop in enumerate(crops, start=1):
            path = Path(crop['crop'])
            if not path.exists():
                continue
            image = Image.open(path).convert('RGB')
            rows = detector.detect(image, image_index=index, threshold=0.16, groups=FOCUSED_GROUPS)
            rows = geometry_filter(rows, image.size, fusion_config['geometry'])
            rows = non_max_suppression(rows, iou_threshold=0.40)
            detections.extend(rows)
            annotation = annotated_dir / item_id / f'{index:02d}.jpg'
            annotate_image(image, rows, annotation)
            crop_reports.append({
                'crop': str(path),
                'annotated': str(annotation),
                'bounds': crop.get('bounds'),
                'detection_count': len(rows),
            })
        if detections:
            evidence = fused_decision(detections, fusion_config['fusion'])
            status = 'focused_detection_complete'
        else:
            evidence = {
                'cpu_state': 'unavailable',
                'cpu_confidence': 0.0,
                'value_score': 0,
                'maxima': {},
                'evidence': {},
                'damage_score': 0.0,
                'damage_labels': [],
                'needs_review': False,
                'review_reasons': [],
                'cooler_validation': {'accepted': 0, 'rejected': 0, 'maximum_rejected_score': 0.0},
                'detections': [],
            }
            status = 'no_socket_crop'
        output.append({
            'item_id': item_id,
            'reference_status': verification.get('status'),
            'identity_score': verification.get('identity_score', 0.0),
            'status': status,
            **evidence,
            'crops': crop_reports,
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description='Run focused CPU/socket detection on reference-projected socket crops')
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/detection_classes.json'))
    parser.add_argument('--fusion-config', type=Path, default=Path('config/detection_fusion.json'))
    parser.add_argument('--model', default='IDEA-Research/grounding-dino-tiny')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--annotated-dir', type=Path, required=True)
    args = parser.parse_args()
    detector = ZeroShotHardwareDetector(DetectionConfig.load(args.config), args.model)
    fusion_config = json.loads(args.fusion_config.read_text(encoding='utf-8'))
    rows = detect_socket_regions(
        json.loads(args.verification.read_text(encoding='utf-8')),
        detector,
        fusion_config,
        args.annotated_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'items': len(rows), 'focused': sum(row['status'] == 'focused_detection_complete' for row in rows)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

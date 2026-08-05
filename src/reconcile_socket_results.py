#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ACTIONABLE_STATES = {
    'empty_socket_likely',
    'socket_cover_likely',
    'visible_cpu_likely',
    'cooler_attached_cpu_highly_likely',
}


def reconcile_item(base: dict[str, Any], focused: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    if not focused or focused.get('status') != 'focused_detection_complete':
        result['socket_region_detection'] = focused
        return result
    minimum_identity = float(config.get('minimum_reference_identity_score', 0.58))
    minimum_confidence = float(config.get('minimum_focused_confidence', 0.50))
    identity_score = float(focused.get('identity_score') or 0.0)
    focused_confidence = float(focused.get('cpu_confidence') or 0.0)
    focused_state = focused.get('cpu_state')
    base_state = base.get('cpu_state')
    result['socket_region_detection'] = focused
    result['full_image_cpu_state'] = base_state
    result['full_image_cpu_confidence'] = float(base.get('cpu_confidence') or 0.0)
    if identity_score < minimum_identity or focused_confidence < minimum_confidence or focused_state not in ACTIONABLE_STATES:
        reasons = list(result.get('review_reasons', []))
        if 'focused_socket_detection_inconclusive' not in reasons:
            reasons.append('focused_socket_detection_inconclusive')
        result['review_reasons'] = reasons
        result['needs_review'] = True
        return result
    result['cpu_state'] = focused_state
    result['cpu_confidence'] = focused_confidence
    result['value_score'] = int(base.get('value_score') or 0) + int(focused.get('value_score') or 0)
    result['detector_source'] = f"{base.get('detector_source', 'detector')}+reference_socket_region"
    if base_state != focused_state:
        reasons = [reason for reason in result.get('review_reasons', []) if reason != 'socket_state_unclear']
        reasons.append('full_image_overridden_by_reference_socket_region')
        result['review_reasons'] = sorted(set(reasons))
        result['needs_review'] = bool(focused.get('needs_review'))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Reconcile full-image detector results with reference-projected socket crops')
    parser.add_argument('--base-results', type=Path, required=True)
    parser.add_argument('--focused-results', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/socket_region_reconciliation.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    base = json.loads(args.base_results.read_text(encoding='utf-8'))
    focused = {str(row['item_id']): row for row in json.loads(args.focused_results.read_text(encoding='utf-8'))}
    rows = [reconcile_item(row, focused.get(str(row['item_id'])), config) for row in base]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'items': len(rows), 'overridden': sum('reference_socket_region' in row.get('detector_source', '') for row in rows)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

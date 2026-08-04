#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def select_alerts(values: list[dict[str, Any]], run_report: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for row in values:
        if (
            row.get('recommendation') == 'bid'
            and float(row.get('expected_profit', 0.0)) >= float(config['minimum_expected_profit'])
            and float(row.get('confidence', 0.0)) >= float(config['minimum_confidence'])
            and float(row.get('recommended_max_bid', 0.0)) <= float(config['maximum_recommended_bid'])
        ):
            alerts.append({'type': 'bid_candidate', 'item_id': row['item_id'], 'title': row.get('title', ''), 'expected_profit': row.get('expected_profit'), 'recommended_max_bid': row.get('recommended_max_bid'), 'confidence': row.get('confidence')})
    if config.get('include_drift') and run_report.get('rollback_recommended'):
        alerts.append({'type': 'model_drift', 'reasons': run_report.get('rollback_reasons', [])})
    if config.get('include_crawler_failures'):
        error_count = sum(len(run_report.get(key, [])) for key in ('search_errors', 'gallery_errors', 'image_download_errors'))
        if error_count:
            alerts.append({'type': 'crawler_errors', 'count': error_count})
    return alerts


def build_report(values: list[dict[str, Any]], run_report: dict[str, Any], health: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    bid = [row for row in values if row.get('recommendation') == 'bid'][: int(config['report']['top_bid_candidates'])]
    review = [row for row in values if row.get('recommendation') == 'review'][: int(config['report']['top_review_candidates'])]
    alerts = select_alerts(values, run_report, config['alerts'])
    return {
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'summary': {
            'status': run_report.get('status'),
            'listings_found': run_report.get('listings_found', 0),
            'processed': run_report.get('processed', 0),
            'bid_candidates': len([row for row in values if row.get('recommendation') == 'bid']),
            'review_candidates': len([row for row in values if row.get('recommendation') == 'review']),
            'healthy': health.get('healthy', False),
        },
        'health': health,
        'alerts': alerts,
        'top_bid_candidates': bid,
        'top_review_candidates': review,
    }


def render_html(report: dict[str, Any]) -> str:
    def money(value: Any) -> str:
        try:
            return f'${float(value):,.2f}'
        except (TypeError, ValueError):
            return '-'

    rows = []
    for item in report['top_bid_candidates']:
        rows.append(f"<tr><td>{html.escape(str(item.get('item_id','')))}</td><td>{html.escape(str(item.get('title','')))}</td><td>{money(item.get('current_bid'))}</td><td>{money(item.get('expected_profit'))}</td><td>{money(item.get('recommended_max_bid'))}</td><td>{float(item.get('confidence',0)):.2f}</td></tr>")
    review_rows = []
    for item in report['top_review_candidates']:
        review_rows.append(f"<tr><td>{html.escape(str(item.get('item_id','')))}</td><td>{html.escape(str(item.get('title','')))}</td><td>{html.escape(', '.join(item.get('reasons', [])))}</td><td>{float(item.get('confidence',0)):.2f}</td></tr>")
    alerts = ''.join(f"<li>{html.escape(json.dumps(alert, sort_keys=True))}</li>" for alert in report['alerts']) or '<li>None</li>'
    summary = report['summary']
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>MotherboardSearch Daily Report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.45rem;text-align:left}}th{{background:#eee}}.ok{{color:green}}.bad{{color:#b00020}}</style></head>
<body><h1>MotherboardSearch Daily Report</h1><p>Generated {html.escape(report['generated_at'])}</p>
<h2>Summary</h2><p class="{'ok' if summary['healthy'] else 'bad'}">Health: {'Healthy' if summary['healthy'] else 'Needs attention'}</p>
<ul><li>Listings found: {summary['listings_found']}</li><li>Processed: {summary['processed']}</li><li>Bid candidates: {summary['bid_candidates']}</li><li>Review candidates: {summary['review_candidates']}</li></ul>
<h2>Alerts</h2><ul>{alerts}</ul>
<h2>Top bid candidates</h2><table><thead><tr><th>Item</th><th>Title</th><th>Current bid</th><th>Expected profit</th><th>Max bid</th><th>Confidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Top review candidates</h2><table><thead><tr><th>Item</th><th>Title</th><th>Reasons</th><th>Confidence</th></tr></thead><tbody>{''.join(review_rows)}</tbody></table>
</body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description='Build JSON and HTML daily reports')
    parser.add_argument('--values', type=Path, required=True)
    parser.add_argument('--run-report', type=Path, required=True)
    parser.add_argument('--health', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/operations.json'))
    parser.add_argument('--json-output', type=Path, required=True)
    parser.add_argument('--html-output', type=Path, required=True)
    args = parser.parse_args()
    values = json.loads(args.values.read_text(encoding='utf-8'))
    run_report = json.loads(args.run_report.read_text(encoding='utf-8'))
    health = json.loads(args.health.read_text(encoding='utf-8'))
    config = json.loads(args.config.read_text(encoding='utf-8'))
    report = build_report(values, run_report, health, config)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    args.html_output.write_text(render_html(report), encoding='utf-8')
    print(json.dumps(report['summary']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

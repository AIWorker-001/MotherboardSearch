from __future__ import annotations

import re
from typing import Any

INTEL_CHIPSETS = re.compile(r'\b(?:H|B|Z|Q|W|P|X)(?:6[1-9]|7[5-9]|8[1-9]|9[1-9]|1[0-9]{2}|2[0-9]{2}|3[0-9]{2}|4[0-9]{2}|5[0-9]{2}|6[0-9]{2}|7[0-9]{2})\b', re.I)
AMD_CHIPSETS = re.compile(r'\b(?:A|B|X)(?:3[0-9]{2}|4[0-9]{2}|5[0-9]{2}|6[0-9]{2})\b|\bAM[2345]\b', re.I)
COOLER_WORDS = re.compile(r'\b(?:cpu\s+fan|cpu\s+cooler|heatsink|heat\s+sink|wraith|stock\s+cooler|tower\s+cooler|aio)\b', re.I)


def platform_hint(title: str) -> str | None:
    if AMD_CHIPSETS.search(title):
        return 'amd'
    if INTEL_CHIPSETS.search(title):
        return 'intel'
    return None


def title_cooler_evidence(title: str) -> bool:
    return bool(COOLER_WORDS.search(title))


def apply_listing_context(result: dict[str, Any], title: str, config: dict[str, Any]) -> dict[str, Any]:
    row = dict(result)
    maxima = dict(row.get('maxima') or {})
    reasons = list(row.get('review_reasons') or [])
    platform = platform_hint(title)
    cooler_in_title = title_cooler_evidence(title)
    row['listing_context'] = {'platform_hint': platform, 'cooler_in_title': cooler_in_title}

    exposed = float(maxima.get('exposed_lga_contact_field') or 0.0)
    empty_amd = float(maxima.get('empty_amd_socket') or 0.0)
    cover = float(maxima.get('socket_cover') or 0.0)
    current = str(row.get('cpu_state') or 'unclear')
    confidence = float(row.get('cpu_confidence') or 0.0)

    intel_weak_empty = float(config.get('intel_weak_empty_threshold', 0.46))
    amd_cover_as_empty = float(config.get('amd_cover_as_empty_threshold', 0.50))
    title_cooler_min = float(config.get('title_cooler_minimum_visual_score', 0.0))

    if cooler_in_title and current == 'unclear' and confidence >= title_cooler_min:
        row['cpu_state'] = 'cooler_attached_cpu_highly_likely'
        row['cpu_confidence'] = round(max(confidence, float(config.get('title_cooler_confidence', 0.62))), 4)
        row['value_score'] = int(row.get('value_score') or 0) + 100
        reasons = [reason for reason in reasons if reason != 'socket_state_unclear']
        reasons.append('cooler_supported_by_listing_title')
        row['needs_review'] = True
    elif platform == 'intel' and current == 'unclear' and exposed >= intel_weak_empty:
        row['cpu_state'] = 'empty_socket_likely'
        row['cpu_confidence'] = round(exposed, 4)
        row['value_score'] = int(row.get('value_score') or 0) - 100
        reasons = [reason for reason in reasons if reason != 'socket_state_unclear']
        reasons.append('intel_empty_socket_supported_by_platform_context')
        row['needs_review'] = exposed < float(config.get('context_auto_accept_threshold', 0.58))
    elif platform == 'amd' and current == 'socket_cover_likely' and cover >= amd_cover_as_empty and empty_amd < cover:
        row['cpu_state'] = 'empty_socket_likely'
        row['cpu_confidence'] = round(cover, 4)
        row['value_score'] = int(row.get('value_score') or 0) - 40
        reasons.append('amd_socket_cover_reinterpreted_as_empty_socket')
        row['needs_review'] = True

    row['review_reasons'] = sorted(set(reasons))
    return row

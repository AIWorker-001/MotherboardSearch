from __future__ import annotations

from typing import Any


def polygon_center(region: Any) -> tuple[float, float]:
    points = region_points(region)
    return (
        sum(float(point[0]) for point in points) / len(points),
        sum(float(point[1]) for point in points) / len(points),
    )


def validate_reference_layout(annotation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    regions = annotation.get('normalized_regions') or {}
    x16 = regions.get('pcie_x16_slots') or []
    x1 = regions.get('pcie_x1_slots') or []
    dimms = regions.get('dimm_slots') or []
    io_rectangle = regions.get('io_rectangle')
    cpu_socket = regions.get('cpu_socket')

    if not x16:
        errors.append('at least one PCIe x16 slot is required')
    expected_x1 = int(annotation.get('expected_counts', {}).get('pcie_x1', 0))
    if expected_x1 and len(x1) != expected_x1:
        errors.append(f'expected {expected_x1} PCIe x1 slots, found {len(x1)}')
    expected_x16 = int(annotation.get('expected_counts', {}).get('pcie_x16', len(x16)))
    if expected_x16 and len(x16) != expected_x16:
        errors.append(f'expected {expected_x16} PCIe x16 slots, found {len(x16)}')
    expected_dimms = int(annotation.get('expected_counts', {}).get('dimm', len(dimms)))
    if expected_dimms and len(dimms) != expected_dimms:
        errors.append(f'expected {expected_dimms} DIMM slots, found {len(dimms)}')
    if not io_rectangle:
        errors.append('rear I/O rectangle is required')
    if not cpu_socket:
        errors.append('CPU socket polygon is required')

    all_pcie = x16 + x1
    if io_rectangle and all_pcie:
        io_center = polygon_center(io_rectangle)
        pcie_center_x = sum(polygon_center(slot)[0] for slot in all_pcie) / len(all_pcie)
        if io_center[0] <= pcie_center_x:
            errors.append('rear I/O must be to the right of the PCIe bank in canonical orientation')

    if all_pcie:
        pcie_center_x = sum(polygon_center(slot)[0] for slot in all_pcie) / len(all_pcie)
        pcie_center_y = sum(polygon_center(slot)[1] for slot in all_pcie) / len(all_pcie)
        if pcie_center_x > 0.55 or pcie_center_y > 0.62:
            errors.append('PCIe bank must occupy the upper-left canonical board region')

    dimm_labels = [str(slot.get('label') or '') for slot in dimms if isinstance(slot, dict)]
    if dimm_labels and dimm_labels != ['DIMM1', 'DIMM2', 'DIMM3', 'DIMM4'][:len(dimm_labels)]:
        errors.append('DIMM slots must be ordered from CPU outward as DIMM1..DIMM4')

    return errors


def region_points(region: Any) -> list[list[float]]:
    if isinstance(region, dict):
        return region['polygon']
    return region

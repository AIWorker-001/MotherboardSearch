from src.layout_schema import validate_reference_layout


def valid_layout():
    return {
        'expected_counts': {'pcie_x16': 1, 'pcie_x1': 1, 'dimm': 2},
        'normalized_regions': {
            'io_rectangle': [[.8,.1],[.95,.1],[.95,.5],[.8,.5]],
            'pcie_x16_slots': [{'label':'X16','polygon':[[.1,.1],[.15,.1],[.15,.5],[.1,.5]]}],
            'pcie_x1_slots': [{'label':'X1','polygon':[[.2,.2],[.25,.2],[.25,.3],[.2,.3]]}],
            'dimm_slots': [
                {'label':'DIMM1','polygon':[[.5,.7],[.9,.7],[.9,.73],[.5,.73]]},
                {'label':'DIMM2','polygon':[[.5,.75],[.9,.75],[.9,.78],[.5,.78]]},
            ],
            'cpu_socket': [[.55,.3],[.7,.3],[.7,.55],[.55,.55]],
        }
    }


def test_valid_layout_passes_orientation_rules():
    assert validate_reference_layout(valid_layout()) == []


def test_io_left_of_pcie_is_rejected():
    layout=valid_layout()
    layout['normalized_regions']['io_rectangle']=[[0,.1],[.08,.1],[.08,.5],[0,.5]]
    assert any('rear I/O' in error for error in validate_reference_layout(layout))


def test_missing_x1_slot_is_rejected():
    layout=valid_layout(); layout['normalized_regions']['pcie_x1_slots']=[]
    assert any('PCIe x1' in error for error in validate_reference_layout(layout))

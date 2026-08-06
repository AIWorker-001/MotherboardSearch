from src.reference_board_editor import build_editor_html

def test_editor_contains_all_required_features():
    html=build_editor_html('board.jpg',1024,768)
    for text in ['PCIe x16 slot','PCIe x1 slot','DIMM slot','Rear I/O edge polygon','CPU socket','Rear CPU bracket']:
        assert text in html
    assert 'polygon_normalized' in html

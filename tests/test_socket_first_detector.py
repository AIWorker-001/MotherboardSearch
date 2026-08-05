from src.object_detector import Detection
from src.socket_first_detector import best_localization, expand_box


def d(label,score,box):
    return Detection(label,score,box,label,1)


def test_expand_box_clamps_to_image():
    assert expand_box((0,0,100,100),(500,400),0.2)==(0,0,120,120)


def test_socket_visible_wins_equal_score_over_cooler():
    rows=[
        d('mounted_cpu_cooler_region',0.8,(100,100,400,400)),
        d('intel_lga_socket',0.8,(150,150,350,350)),
    ]
    result=best_localization(rows,(1000,800),{'minimum_socket_area_ratio':0.006,'maximum_socket_area_ratio':0.32})
    assert result['source']=='socket_visible'
    assert result['label']=='intel_lga_socket'


def test_rejects_motherboard_sized_socket_box():
    rows=[d('cpu_socket_region',0.9,(0,0,950,750))]
    assert best_localization(rows,(1000,800),{'minimum_socket_area_ratio':0.006,'maximum_socket_area_ratio':0.32}) is None


def test_geometry_fast_path_is_gated_to_intel_without_cooler_title():
    from src.listing_context import platform_hint, title_cooler_evidence
    assert platform_hint('Gigabyte Z370 Aorus Gaming 5')=='intel'
    assert not title_cooler_evidence('Gigabyte Z370 Aorus Gaming 5')
    assert title_cooler_evidence('ASUS P8P67 EVO with CPU fan and heatsink')

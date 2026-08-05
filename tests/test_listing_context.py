from src.listing_context import apply_listing_context, platform_hint, title_cooler_evidence

CONFIG={
    'intel_weak_empty_threshold':0.46,
    'amd_cover_as_empty_threshold':0.50,
    'title_cooler_minimum_visual_score':0.0,
    'title_cooler_confidence':0.62,
    'context_auto_accept_threshold':0.58,
}


def base(state='unclear',confidence=0.47,maxima=None):
    return {'cpu_state':state,'cpu_confidence':confidence,'value_score':0,'maxima':maxima or {},'review_reasons':['socket_state_unclear'],'needs_review':True}


def test_platform_and_title_cues():
    assert platform_hint('Gigabyte B450 Aorus M AM4')=='amd'
    assert platform_hint('Gigabyte Z370 Aorus Gaming 5')=='intel'
    assert title_cooler_evidence('ASUS P8P67 EVO with CPU Fan and Heatsinks')


def test_p8p67_title_promotes_cooler_without_silently_auto_accepting():
    row=apply_listing_context(base(maxima={'exposed_lga_contact_field':0.4738}),'Asus P8p67 Evo Motherboard With Cpu Fan And Heatsinks',CONFIG)
    assert row['cpu_state']=='cooler_attached_cpu_highly_likely'
    assert row['cpu_confidence']>=0.62
    assert row['needs_review'] is True


def test_z370_weak_lga_cue_becomes_empty():
    row=apply_listing_context(base(maxima={'exposed_lga_contact_field':0.4798}),'Gigabyte Z370 Aorus Gaming 5 Atx Motherboard',CONFIG)
    assert row['cpu_state']=='empty_socket_likely'


def test_b450_socket_cover_is_reinterpreted_as_empty():
    row=apply_listing_context(base('socket_cover_likely',0.5208,{'socket_cover':0.5208}),'Gigabyte B450 Aorus M Micro-atx Am4 Motherboard',CONFIG)
    assert row['cpu_state']=='empty_socket_likely'
    assert 'amd_socket_cover_reinterpreted_as_empty_socket' in row['review_reasons']

from PIL import Image

from src.detection_fusion import fused_decision, generate_tiles, geometry_filter
from src.object_detector import Detection


def d(label, score, image_index=1, box=(10,10,210,210)):
    return Detection(label, score, box, label, image_index)


def test_multi_image_corroboration_promotes_moderate_cpu_evidence():
    result = fused_decision([d('cpu_installed', 0.49, 1), d('cpu_installed', 0.48, 2)], {
        'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2
    })
    assert result['cpu_state'] == 'visible_cpu_likely'
    assert result['evidence']['cpu_installed']['distinct_images'] == 2


def test_conflicting_installed_and_empty_routes_to_review():
    result = fused_decision([d('cpu_installed', 0.62, 1), d('empty_lga_socket', 0.60, 2)], {
        'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2
    })
    assert result['cpu_state'] == 'unclear'
    assert 'conflicting_socket_evidence' in result['review_reasons']


def test_damage_requires_two_images():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2}
    one=fused_decision([d('bent_socket_pins',0.9,1)],config)
    two=fused_decision([d('bent_socket_pins',0.7,1),d('bent_socket_pins',0.7,2)],config)
    assert 'possible_physical_damage' not in one['review_reasons']
    assert 'possible_physical_damage' in two['review_reasons']


def test_tiling_and_geometry_filter():
    image=Image.new('RGB',(1600,1200))
    tiles=generate_tiles(image,768,0.2)
    assert len(tiles)>2
    config={'minimum_area_ratio':0.001,'maximum_area_ratio':0.65,'socket_minimum_area_ratio':0.002,'cooler_minimum_area_ratio':0.01}
    tiny=d('cpu_installed',0.9,1,(0,0,10,10))
    normal=d('cpu_installed',0.8,1,(0,0,200,200))
    kept=geometry_filter([tiny,normal],image.size,config)
    assert tiny not in kept and normal in kept


def test_rejects_motherboard_sized_cooler_box():
    config={'minimum_area_ratio':0.001,'maximum_area_ratio':0.65,'socket_minimum_area_ratio':0.002,'cooler_minimum_area_ratio':0.01,'cooler_maximum_area_ratio':0.22,'cooler_maximum_width_ratio':0.62,'cooler_maximum_height_ratio':0.62}
    huge=d('tower_cpu_cooler',0.9,1,(10,10,1900,900))
    plausible=d('tower_cpu_cooler',0.8,1,(500,250,1000,750))
    kept=geometry_filter([huge,plausible],(2000,1400),config)
    assert huge not in kept
    assert plausible in kept


def test_empty_socket_overrides_weak_cooler_evidence():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05}
    result=fused_decision([d('empty_lga_socket',0.72,1),d('tower_cpu_cooler',0.44,2),d('tower_cpu_cooler',0.43,3)],config)
    assert result['cpu_state']=='empty_socket_likely'


def test_multiple_lga_empty_cues_form_strong_empty_socket_evidence():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05}
    result=fused_decision([
        d('exposed_lga_contact_field',0.48,1),
        d('lga_center_rectangle',0.46,1),
        d('open_lga_retention_frame',0.43,2),
    ],config)
    assert result['cpu_state']=='empty_socket_likely'
    assert result['maxima']['empty_lga_visual_cues'] >= 0.58


def test_lga_empty_cues_override_false_cooler():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05}
    result=fused_decision([
        d('exposed_lga_contact_field',0.55,1),
        d('lga_center_rectangle',0.50,1),
        d('tower_cpu_cooler',0.44,2),
        d('tower_cpu_cooler',0.43,3),
    ],config)
    assert result['cpu_state']=='empty_socket_likely'


def test_uncorroborated_cooler_is_rejected():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05,'cooler_structure_minimum_overlap':0.35}
    result=fused_decision([d('tower_cpu_cooler',0.90,1,(100,100,500,500))],config)
    assert result['cpu_state']=='unclear'
    assert result['cooler_validation']['accepted']==0
    assert result['cooler_validation']['rejected']==1
    assert 'uncorroborated_cooler_detections_rejected' in result['review_reasons']


def test_cooler_requires_overlapping_positive_structure():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05,'cooler_structure_minimum_overlap':0.35}
    result=fused_decision([
        d('tower_cpu_cooler',0.75,1,(100,100,500,500)),
        d('heatsink_fin_stack',0.65,1,(180,150,420,480)),
    ],config)
    assert result['cpu_state']=='cooler_attached_cpu_highly_likely'
    assert result['cooler_validation']['accepted']==1


def test_distant_fan_filter_does_not_validate_cooler():
    config={'additional_image_weight':0.35,'corroboration_bonus':0.08,'strong_threshold':0.58,'moderate_threshold':0.46,'conflict_margin':0.10,'minimum_distinct_images_for_damage':2,'cooler_minimum_single_score':0.58,'cooler_minimum_corroborated_score':0.52,'empty_socket_override_threshold':0.50,'empty_socket_override_margin':0.05,'cooler_structure_minimum_overlap':0.35}
    result=fused_decision([
        d('tower_cpu_cooler',0.80,1,(100,100,500,500)),
        d('cpu_fan_blades',0.80,1,(700,700,900,900)),
    ],config)
    assert result['cpu_state']=='unclear'
    assert result['cooler_validation']['accepted']==0

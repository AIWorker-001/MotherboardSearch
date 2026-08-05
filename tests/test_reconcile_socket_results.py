from src.reconcile_socket_results import reconcile_item


def base():
    return {'item_id':'1','cpu_state':'cooler_attached_cpu_highly_likely','cpu_confidence':0.62,'value_score':100,'detector_source':'phase2','needs_review':False,'review_reasons':[]}


def test_focused_empty_socket_overrides_full_image_cooler():
    focused={'status':'focused_detection_complete','identity_score':0.90,'cpu_state':'empty_socket_likely','cpu_confidence':0.82,'value_score':-100,'needs_review':False}
    row=reconcile_item(base(),focused,{'minimum_reference_identity_score':0.58,'minimum_focused_confidence':0.50})
    assert row['cpu_state']=='empty_socket_likely'
    assert row['full_image_cpu_state']=='cooler_attached_cpu_highly_likely'
    assert 'full_image_overridden_by_reference_socket_region' in row['review_reasons']


def test_low_identity_cannot_override():
    focused={'status':'focused_detection_complete','identity_score':0.40,'cpu_state':'empty_socket_likely','cpu_confidence':0.90,'value_score':-100,'needs_review':False}
    row=reconcile_item(base(),focused,{'minimum_reference_identity_score':0.58,'minimum_focused_confidence':0.50})
    assert row['cpu_state']=='cooler_attached_cpu_highly_likely'
    assert row['needs_review'] is True

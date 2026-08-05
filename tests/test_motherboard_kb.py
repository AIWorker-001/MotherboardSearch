import json
from pathlib import Path
import cv2
import numpy as np
from src.motherboard_kb import model_key, serialize_features, match_reference, project_region, verify_model


def patterned(path: Path, shift=(0,0)):
    image=np.full((500,700,3),255,np.uint8)
    cv2.rectangle(image,(80+shift[0],60+shift[1]),(620+shift[0],440+shift[1]),(0,0,0),5)
    for x in range(120,600,60): cv2.circle(image,(x+shift[0],200+shift[1]),12,(0,0,0),-1)
    cv2.putText(image,'Z370 AORUS 5',(150+shift[0],350+shift[1]),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),3)
    cv2.imwrite(str(path),image)


def test_model_key(): assert model_key('Gigabyte Z370 AORUS Gaming 5')=='GIGABYTE-Z370-AORUS-GAMING-5'


def test_reference_match_and_projection(tmp_path):
    ref=tmp_path/'ref.jpg'; query=tmp_path/'query.jpg'; features=tmp_path/'ref.npz'
    patterned(ref); patterned(query)
    info=serialize_features(ref,features)
    record={'id':'r1','feature_file':str(features),'trust':1.0,'approved':True,'source_type':'manufacturer'}
    match=match_reference(query,record,0.75)
    assert match['good_matches'] >= 18
    assert match['inlier_ratio'] >= 0.32
    assert project_region([[0,0],[10,0],[10,10],[0,10]], [[1,0,5],[0,1,7],[0,0,1]]) == [[5.0,7.0],[15.0,7.0],[15.0,17.0],[5.0,17.0]]


def test_missing_reference_routes_safely():
    result=verify_model({'matching':{}},{'boards':{}},'ASUS P8P67 EVO',[])
    assert result['status']=='no_reference'


def test_reference_catalog_records_storage_objects(tmp_path):
    from src.motherboard_kb import add_reference, load_catalog
    image=tmp_path/'ref.jpg'; patterned(image)
    config={
        'reference_root':str(tmp_path/'references'),
        'feature_root':str(tmp_path/'features'),
        'storage':{'backend':'local','cache_root':str(tmp_path/'cache')},
        'sources':{'manufacturer':{'trust':1.0,'requires_manual_approval':False}},
    }
    catalog_path=tmp_path/'catalog.json'
    record=add_reference(config,catalog_path,model='Test Board Z370',source_type='manufacturer',source=str(image),approved=False)
    assert record['image_object']['backend']=='local'
    assert record['feature_object']['backend']=='local'
    assert load_catalog(catalog_path)['boards']['TEST-BOARD-Z370']['references'][0]['feature_object']

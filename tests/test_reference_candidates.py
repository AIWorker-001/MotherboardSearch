from pathlib import Path
import cv2
import numpy as np
from src.reference_candidates import compare_feature_files, prepare_candidates, review_candidates


def patterned(path: Path, text='BOARD'):
    image=np.full((500,700,3),255,np.uint8)
    cv2.rectangle(image,(80,60),(620,440),(0,0,0),5)
    for x in range(120,600,60): cv2.circle(image,(x,200),12,(0,0,0),-1)
    cv2.putText(image,text,(180,350),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),3)
    cv2.imwrite(str(path),image)


def config(tmp_path: Path):
    return {
        'matching':{'ratio_test':0.75},
        'candidate_review':{'minimum_pair_score':0.52,'minimum_agreeing_candidates':2},
        'sources':{
            'manufacturer':{'trust':1.0,'requires_manual_approval':False},
            'ebay':{'trust':0.72,'requires_manual_approval':True},
        },
    }


def test_prepare_and_review_matching_candidates(tmp_path):
    first=tmp_path/'one.jpg'; second=tmp_path/'two.jpg'
    patterned(first); patterned(second)
    rows=prepare_candidates(config(tmp_path),[
        {'model':'Example Z370','source_type':'manufacturer','source':str(first)},
        {'model':'Example Z370','source_type':'manufacturer','source':str(second)},
    ],tmp_path/'work')
    reviewed=review_candidates(config(tmp_path),rows)
    assert all(row['recommendation']=='approve' for row in reviewed)
    assert reviewed[0]['agreements'][0]['score'] >= 0.52


def test_marketplace_candidate_requires_manual_approval(tmp_path):
    first=tmp_path/'one.jpg'; second=tmp_path/'two.jpg'
    patterned(first); patterned(second)
    rows=prepare_candidates(config(tmp_path),[
        {'model':'Example Z370','source_type':'ebay','source':str(first)},
        {'model':'Example Z370','source_type':'ebay','source':str(second)},
    ],tmp_path/'work')
    reviewed=review_candidates(config(tmp_path),rows)
    assert all(row['recommendation']=='manual_approval' for row in reviewed)

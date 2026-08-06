import cv2
import numpy as np
from src.connector_line_detector import detect_connector_candidates

def test_detects_long_narrow_connector_pairs():
    image=np.full((500,700,3),180,np.uint8)
    for x in [100,190,280]:
        cv2.rectangle(image,(x,90),(x+18,360),(25,25,25),-1)
        cv2.rectangle(image,(x+5,95),(x+13,355),(100,100,100),1)
    candidates=detect_connector_candidates(image,{'minimum_line_length':80,'maximum_candidates':50})
    assert len(candidates)>=3
    assert max(c['length'] for c in candidates)>200

import cv2
import numpy as np
from src.connector_bank_detector import detect_banks


def synthetic_board():
    image=np.full((700,1000,3),175,np.uint8)
    for x,length in [(100,300),(190,300),(280,300),(145,95),(235,95)]:
        cv2.rectangle(image,(x,100),(x+18,100+length),(25,25,25),-1)
        cv2.rectangle(image,(x+5,105),(x+13,95+length),(100,100,100),1)
    for y in [480,520,560,600]:
        cv2.rectangle(image,(560,y),(900,y+18),(25,25,25),-1)
        cv2.rectangle(image,(565,y+5),(895,y+13),(100,100,100),1)
    return image


def test_detects_pcie_and_dimm_banks():
    result=detect_banks(synthetic_board(),{'candidate_detector':{'minimum_line_length':70,'maximum_candidates':100}})
    assert result['pcie_bank'] is not None
    assert result['dimm_bank'] is not None

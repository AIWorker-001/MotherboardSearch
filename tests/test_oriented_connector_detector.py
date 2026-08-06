import cv2
import numpy as np
from src.oriented_connector_detector import detect


def test_oriented_detector_finds_repeated_dark_slots():
    image=np.full((600,900,3),190,np.uint8)
    for x in [90,170,250]: cv2.rectangle(image,(x,90),(x+18,350),(20,20,20),-1)
    for y in [410,445,480,515]: cv2.rectangle(image,(500,y),(820,y+16),(20,20,20),-1)
    config={'angles':[0,90],'kernel_lengths':[60,100,180,260,340],'kernel_height':9,'threshold':15,'minimum_aspect':5,'minimum_length':45,'maximum_width':30}
    result=detect(image,config)
    assert result['pcie_bank'] is not None
    assert result['dimm_bank'] is not None

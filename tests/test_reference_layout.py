import cv2
import numpy as np
from src.reference_layout import infer_cpu_search_region, analyze_reference


def synthetic_board():
    image=np.full((800,1000,3),245,np.uint8)
    cv2.rectangle(image,(80,60),(920,740),(40,110,45),-1)
    # rear IO block
    cv2.rectangle(image,(80,120),(145,360),(130,130,130),-1)
    # DIMM slots, vertical, right side
    for x in [670,700,730,760]: cv2.rectangle(image,(x,130),(x+10,450),(20,20,20),2)
    # PCIe slots, horizontal, lower half
    for y in [500,550,610]: cv2.rectangle(image,(230,y),(790,y+12),(20,20,20),2)
    # empty socket with pin grid
    cv2.rectangle(image,(300,190),(540,420),(180,180,180),8)
    cv2.rectangle(image,(330,220),(510,390),(80,80,80),4)
    for y in range(235,380,9):
        for x in range(345,500,9): cv2.circle(image,(x,y),1,(230,230,230),-1)
    cv2.rectangle(image,(395,280),(445,330),(30,30,30),-1)
    return image


def test_cpu_region_uses_dimm_and_pcie_anchors():
    region=infer_cpu_search_region((0,0,1000,800),{'dimm_bank':{'axis_center':730},'pcie_bank':{'axis_center':520}},0.065)
    assert region[0][0] >= 100
    assert region[1][0] < 730
    assert region[2][1] < 520


def test_analyze_reference_finds_socket_in_constrained_region(tmp_path):
    image=synthetic_board(); path=tmp_path/'board.jpg'; cv2.imwrite(str(path),image)
    result=analyze_reference(path,{'minimum_area_ratio':.006,'maximum_area_ratio':.09,'reference_minimum_area_ratio':.015,'reference_maximum_area_ratio':.45,'minimum_empty_lga_score':.35,'minimum_periodic_pin_score':.2,'port_buffer_ratio':.065})
    assert result['socket_candidate'] is not None
    x1,y1,x2,y2=result['socket_candidate']['box']
    assert 250 <= x1 <= 430
    assert 150 <= y1 <= 330

import cv2
import numpy as np
from src.board_orientation import evaluate_rotations, rotate_image


def canonical_board():
    image=np.full((500,800,3),80,np.uint8)
    for x in [90,140,190]: cv2.rectangle(image,(x,90),(x+16,330),(10,10,10),3)
    for y in [360,395,430,465]: cv2.rectangle(image,(380,y),(720,y+12),(10,10,10),3)
    return image


def test_rotation_helpers_cover_all_four_orientations():
    image=np.zeros((40,80,3),np.uint8)
    assert rotate_image(image,0).shape[:2]==(40,80)
    assert rotate_image(image,90).shape[:2]==(80,40)
    assert rotate_image(image,180).shape[:2]==(40,80)
    assert rotate_image(image,270).shape[:2]==(80,40)


def test_canonical_orientation_scores_best_when_pcie_is_left():
    image=canonical_board()
    config={'slot_geometry':{'minimum_aspect_ratio':5,'minimum_length_ratio':.1,'minimum_area_ratio':.0003,'maximum_area_ratio':.1,'angle_tolerance_degrees':12,'spacing_tolerance_ratio':.15}}
    results=evaluate_rotations(image,config)
    assert results[0]['rotation']==0

import cv2
import numpy as np
from src.board_normalizer import detect_board_quad, infer_top_right_from_top_edge, normalize_board, order_quad


def synthetic_board():
    image=np.full((600,900,3),30,np.uint8)
    quad=np.array([[120,90],[790,70],[820,520],[90,540]],np.int32)
    cv2.fillConvexPoly(image,quad,(70,120,70))
    cv2.polylines(image,[quad],True,(220,220,220),8)
    return image


def test_order_quad():
    points=np.array([[90,540],[790,70],[120,90],[820,520]],np.float32)
    assert order_quad(points).astype(int).tolist()==[[120,90],[790,70],[820,520],[90,540]]


def test_detects_and_normalizes_synthetic_board():
    image=synthetic_board()
    result=detect_board_quad(image)
    assert len(result['quad'])==4
    normalized,_=normalize_board(image,result['quad'])
    assert normalized.shape[1] > normalized.shape[0]


def test_repairs_inset_top_right_by_extending_top_edge():
    quad=[[120,100],[760,80],[820,520],[90,540]]
    result=infer_top_right_from_top_edge(quad,(900,600),minimum_inset_ratio=.04)
    assert result['applied'] is True
    inferred=result['inferred_top_right']
    assert inferred[0]==820.0
    assert 77 <= inferred[1] <= 79


def test_does_not_repair_corner_already_at_right_edge():
    quad=[[120,100],[815,80],[820,520],[90,540]]
    result=infer_top_right_from_top_edge(quad,(900,600),minimum_inset_ratio=.04)
    assert result['applied'] is False

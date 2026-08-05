import cv2
import numpy as np
from src.socket_geometry import detect_empty_lga, rectangle_candidates


def synthetic_socket(size=600):
    image=np.full((size,size,3),45,np.uint8)
    cv2.rectangle(image,(150,140),(450,460),(170,170,170),12)
    cv2.rectangle(image,(190,180),(410,420),(85,85,85),5)
    for y in range(195,410,10):
        for x in range(205,400,10):
            cv2.circle(image,(x,y),1,(220,220,220),-1)
    cv2.rectangle(image,(270,270),(330,330),(35,35,35),-1)
    return image


def test_rectangle_candidates_find_pin_window():
    rows=rectangle_candidates(synthetic_socket(),{'minimum_area_ratio':.006,'maximum_area_ratio':.5,'minimum_empty_lga_score':.4})
    assert rows
    assert max(row['periodic_pin_score'] for row in rows)>.25


def test_detect_empty_lga_on_synthetic(tmp_path):
    path=tmp_path/'socket.jpg';cv2.imwrite(str(path),synthetic_socket())
    result=detect_empty_lga(path,{'minimum_area_ratio':.006,'maximum_area_ratio':.5,'minimum_empty_lga_score':.35,'minimum_periodic_pin_score':.20})
    assert result['detected'] is True

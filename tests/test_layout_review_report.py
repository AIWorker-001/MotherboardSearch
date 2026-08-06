import json
from pathlib import Path
import cv2
import numpy as np
from src.layout_review_report import build_report, polygon_distance


def test_polygon_distance_centers():
    assert round(polygon_distance([[0,0],[10,0],[10,10],[0,10]], [[3,4],[13,4],[13,14],[3,14]]), 2) == 5.0


def test_build_report(tmp_path: Path):
    image=tmp_path/'board.jpg'; cv2.imwrite(str(image),np.full((300,400,3),80,np.uint8))
    annotation=tmp_path/'annotation.json'; annotation.write_text(json.dumps({
        'board':[[10,10],[390,10],[390,290],[10,290]],
        'io_rectangle':[[10,10],[70,10],[70,160],[10,160]],
        'pcie_slots':[[[40,70],[60,70],[60,230],[40,230]]],
        'dimm_slots':[[[180,240],[350,240],[350,255],[180,255]]],
        'cpu_search_region':[[150,60],[340,60],[340,220],[150,220]],
        'cpu_socket':[[220,90],[300,90],[300,170],[220,170]],
        'rear_cpu_bracket':[[218,88],[302,88],[302,172],[218,172]],
    }))
    observed=tmp_path/'observed.json'; observed.write_text(json.dumps({'state':'EMPTY SOCKET','confidence':.94,'polygon':[[222,92],[302,92],[302,172],[222,172]]}))
    result=build_report(image,annotation,tmp_path/'review.jpg',observed)
    assert Path(result['overlay']).exists()
    assert result['status']['Observed socket']=='EMPTY SOCKET'

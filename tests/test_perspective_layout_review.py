import json
from pathlib import Path
import cv2
import numpy as np
from src.perspective_layout_review import order_corners, project_polygon, render


def test_order_corners_returns_tl_tr_br_bl():
    points=[[90,90],[10,10],[90,10],[10,90]]
    assert order_corners(points).astype(int).tolist()==[[10,10],[90,10],[90,90],[10,90]]


def test_render_writes_both_views(tmp_path: Path):
    image=tmp_path/'input.jpg'; cv2.imwrite(str(image),np.full((300,400,3),80,np.uint8))
    annotation=tmp_path/'annotation.json'
    annotation.write_text(json.dumps({
      'board_corners':[[20,20],[380,30],[370,280],[30,270]],
      'expected_counts':{'pcie_x16':1,'pcie_x1':1,'dimm':1},
      'canonical_size':[500,400],
      'normalized_regions':{
        'io_rectangle':[[.82,.1],[.97,.1],[.97,.7],[.82,.7]],
        'pcie_x16_slots':[{'label':'X16','polygon':[[.2,.2],[.24,.2],[.24,.7],[.2,.7]]}],
        'pcie_x1_slots':[{'label':'X1','polygon':[[.28,.25],[.31,.25],[.31,.36],[.28,.36]]}],
        'dimm_slots':[{'label':'DIMM1','polygon':[[.55,.75],[.9,.75],[.9,.79],[.55,.79]]}],
        'cpu_search_region':[[.4,.2],[.8,.2],[.8,.7],[.4,.7]],
        'cpu_socket':[[.52,.3],[.7,.3],[.7,.55],[.52,.55]],
        'rear_cpu_bracket':[[.5,.28],[.72,.28],[.72,.57],[.5,.57]],
      }
    }))
    result=render(image,annotation,tmp_path/'normalized.jpg',tmp_path/'original.jpg')
    assert Path(result['normalized_overlay']).exists()
    assert Path(result['original_overlay']).exists()
    assert result['canonical_size']==[500,400]

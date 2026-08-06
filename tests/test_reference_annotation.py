import json
from pathlib import Path
import cv2
import numpy as np
from src.reference_annotation import annotate_reference


def test_reference_annotation_writes_overlay(tmp_path: Path):
    image=tmp_path/'board.jpg'; cv2.imwrite(str(image),np.full((300,400,3),100,np.uint8))
    annotation=tmp_path/'annotation.json'
    annotation.write_text(json.dumps({
        'board':[[10,10],[390,10],[390,290],[10,290]],
        'pcie_slots':[[[50,50],[70,50],[70,200],[50,200]]],
        'dimm_slots':[[[200,220],[350,220],[350,235],[200,235]]],
        'cpu_search_region':[[160,60],[340,60],[340,210],[160,210]],
        'cpu_socket':[[220,90],[300,90],[300,170],[220,170]],
    }))
    result=annotate_reference(image,annotation,tmp_path/'overlay.jpg')
    assert Path(result['overlay']).exists()
    assert result['image_size']==[400,300]

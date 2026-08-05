from pathlib import Path
from PIL import Image
from src.reference_regions import normalize_polygon, projected_regions, set_region, write_region_crops


def test_normalize_and_set_region():
    catalog={'boards':{'TEST-BOARD':{'model':'Test Board','regions':{}}}}
    region=set_region(catalog,model='Test Board',name='cpu_socket',points=[[10,20],[110,20],[110,120],[10,120]],reference_width=200,reference_height=200)
    assert region['polygon_normalized'][0]==[0.05,0.1]
    assert catalog['boards']['TEST-BOARD']['regions']['cpu_socket']==region


def test_project_regions_with_identity_homography():
    board={'regions':{'cpu_socket':{'polygon_normalized':[[0.1,0.2],[0.3,0.2],[0.3,0.4],[0.1,0.4]],'reference_id':None}}}
    best={'homography':[[1,0,0],[0,1,0],[0,0,1]],'reference_size':[1000,500],'reference_id':'r1'}
    regions=projected_regions(board,best)
    assert regions['cpu_socket']==[[100.0,100.0],[300.0,100.0],[300.0,200.0],[100.0,200.0]]


def test_write_region_crop(tmp_path: Path):
    image_path=tmp_path/'board.jpg'
    Image.new('RGB',(400,300),'white').save(image_path)
    rows=write_region_crops(image_path,{'cpu_socket':[[100,80],[220,80],[220,200],[100,200]]},tmp_path/'out')
    assert Path(rows[0]['crop']).exists()
    assert Path(rows[0]['overlay']).exists()
    assert rows[0]['bounds'][0] < 100

#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
import cv2,numpy as np

COLORS={'manual':(0,255,0),'predicted':(0,0,255)}

def center(points:list[list[float]])->np.ndarray:return np.mean(np.asarray(points,dtype=np.float32),axis=0)
def points(row:Any):return row.get('polygon',row) if isinstance(row,dict) else row

def compare(image_path:Path,manual_path:Path,predicted_path:Path,output:Path)->dict[str,Any]:
 image=cv2.imread(str(image_path)); manual=json.loads(manual_path.read_text()); predicted=json.loads(predicted_path.read_text())
 if image is None: raise ValueError(f'cannot decode {image_path}')
 rows=[]; canvas=image.copy(); mg=manual.get('annotations',manual.get('normalized_regions',{})); pg=predicted.get('annotations',predicted.get('normalized_regions',{}))
 for kind,mitems in mg.items():
  pitems=pg.get(kind,[])
  if isinstance(mitems,dict):mitems=[mitems]
  if isinstance(pitems,dict):pitems=[pitems]
  for i,m in enumerate(mitems):
   mp=points(m); cv2.polylines(canvas,[np.asarray(mp,np.int32)],True,COLORS['manual'],4)
   if i<len(pitems):
    pp=points(pitems[i]);cv2.polylines(canvas,[np.asarray(pp,np.int32)],True,COLORS['predicted'],3)
    mc,pc=center(mp),center(pp);cv2.arrowedLine(canvas,tuple(np.rint(pc).astype(int)),tuple(np.rint(mc).astype(int)),(255,255,255),2)
    rows.append({'type':kind,'index':i,'center_error_pixels':round(float(np.linalg.norm(mc-pc)),2)})
 output.parent.mkdir(parents=True,exist_ok=True);cv2.imwrite(str(output),canvas)
 return {'overlay':str(output),'comparisons':rows}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--manual',type=Path,required=True);p.add_argument('--predicted',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--json-output',type=Path,required=True);a=p.parse_args();r=compare(a.image,a.manual,a.predicted,a.output);a.json_output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0
if __name__=='__main__':raise SystemExit(main())

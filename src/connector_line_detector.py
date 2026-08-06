#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def line_angle(p1: np.ndarray, p2: np.ndarray) -> float:
    dx, dy = float(p2[0]-p1[0]), float(p2[1]-p1[1])
    angle = math.degrees(math.atan2(dy, dx)) % 180.0
    return angle


def angle_distance(a: float, b: float) -> float:
    delta = abs(a-b) % 180.0
    return min(delta, 180.0-delta)


def canonical_line(line: np.ndarray) -> dict[str, Any]:
    x1, y1, x2, y2 = [float(v) for v in np.asarray(line).reshape(-1)]
    p1=np.array([x1,y1],np.float32); p2=np.array([x2,y2],np.float32)
    if (p2[0] < p1[0]) or (p2[0] == p1[0] and p2[1] < p1[1]):
        p1,p2=p2,p1
    vec=p2-p1
    length=float(np.linalg.norm(vec))
    axis=vec/max(length,1e-6)
    normal=np.array([-axis[1],axis[0]],np.float32)
    center=(p1+p2)/2
    return {'p1':p1,'p2':p2,'center':center,'axis':axis,'normal':normal,'length':length,'angle':line_angle(p1,p2)}


def segment_overlap(a: dict[str,Any], b: dict[str,Any]) -> float:
    axis=a['axis']
    a_vals=sorted([float(np.dot(a['p1'],axis)),float(np.dot(a['p2'],axis))])
    b_vals=sorted([float(np.dot(b['p1'],axis)),float(np.dot(b['p2'],axis))])
    overlap=max(0.0,min(a_vals[1],b_vals[1])-max(a_vals[0],b_vals[0]))
    return overlap/max(1e-6,min(a['length'],b['length']))


def make_candidate(a: dict[str,Any], b: dict[str,Any], gray: np.ndarray) -> dict[str,Any] | None:
    if angle_distance(a['angle'],b['angle'])>4.5:
        return None
    if max(a['length'],b['length'])/max(1.0,min(a['length'],b['length']))>1.35:
        return None
    overlap=segment_overlap(a,b)
    if overlap<0.72:
        return None
    sep=abs(float(np.dot(b['center']-a['center'],a['normal'])))
    if not 4.0<=sep<=34.0:
        return None
    axis=(a['axis']+b['axis'])/2
    axis=axis/max(1e-6,float(np.linalg.norm(axis)))
    normal=np.array([-axis[1],axis[0]],np.float32)
    center=(a['center']+b['center'])/2
    length=min(a['length'],b['length'])*overlap
    width=sep
    p0=center-axis*length/2-normal*width/2
    p1=center+axis*length/2-normal*width/2
    p2=center+axis*length/2+normal*width/2
    p3=center-axis*length/2+normal*width/2
    poly=np.array([p0,p1,p2,p3],np.float32)
    mask=np.zeros(gray.shape,np.uint8)
    cv2.fillConvexPoly(mask,np.rint(poly).astype(np.int32),255)
    inside=float(cv2.mean(gray,mask=mask)[0])
    outer_poly=center+ (poly-center)*1.45
    outer=np.zeros(gray.shape,np.uint8)
    cv2.fillConvexPoly(outer,np.rint(outer_poly).astype(np.int32),255)
    ring=cv2.subtract(outer,mask)
    outside=float(cv2.mean(gray,mask=ring)[0]) if cv2.countNonZero(ring) else inside
    darkness=max(0.0,min(1.0,(outside-inside+18.0)/80.0))
    aspect=length/max(width,1e-6)
    if aspect<4.0:
        return None
    score=0.35*min(1.0,aspect/12.0)+0.25*overlap+0.25*darkness+0.15*(1.0-min(1.0,abs(a['length']-b['length'])/max(a['length'],b['length'])))
    return {'polygon':np.rint(poly).astype(int).tolist(),'center':[round(float(center[0]),2),round(float(center[1]),2)],'angle':round(float((a['angle']+b['angle'])/2),2),'length':round(length,2),'width':round(width,2),'aspect':round(aspect,2),'inside_gray':round(inside,1),'outside_gray':round(outside,1),'score':round(float(score),4)}


def iou_box(a:list[list[int]],b:list[list[int]])->float:
    ax=[p[0] for p in a]; ay=[p[1] for p in a]; bx=[p[0] for p in b]; by=[p[1] for p in b]
    x1=max(min(ax),min(bx));y1=max(min(ay),min(by));x2=min(max(ax),max(bx));y2=min(max(ay),max(by))
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=(max(ax)-min(ax))*(max(ay)-min(ay));bb=(max(bx)-min(bx))*(max(by)-min(by))
    return inter/max(1.0,aa+bb-inter)


def detect_connector_candidates(image: np.ndarray, config: dict[str,Any]) -> list[dict[str,Any]]:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gray=cv2.createCLAHE(2.0,(8,8)).apply(gray)
    lsd=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines=lsd.detect(gray)[0]
    if lines is None:
        return []
    min_len=float(config.get('minimum_line_length',45))
    parsed=[canonical_line(line) for line in lines if canonical_line(line)['length']>=min_len]
    candidates=[]
    for i,a in enumerate(parsed):
        for b in parsed[i+1:]:
            c=make_candidate(a,b,gray)
            if c is not None:
                candidates.append(c)
    candidates.sort(key=lambda r:r['score'],reverse=True)
    dedup=[]
    for c in candidates:
        if any(iou_box(c['polygon'],d['polygon'])>0.45 and angle_distance(c['angle'],d['angle'])<6 for d in dedup):
            continue
        dedup.append(c)
        if len(dedup)>=int(config.get('maximum_candidates',120)):
            break
    return dedup


def cluster_candidates(candidates:list[dict[str,Any]], image_shape:tuple[int,int,int]) -> list[dict[str,Any]]:
    h,w=image_shape[:2]
    clusters=[]
    for c in candidates:
        placed=False
        cc=np.array(c['center'],np.float32)
        for cluster in clusters:
            mean_angle=sum(x['angle'] for x in cluster)/len(cluster)
            if angle_distance(c['angle'],mean_angle)>7:
                continue
            axis=np.array([math.cos(math.radians(mean_angle)),math.sin(math.radians(mean_angle))],np.float32)
            normal=np.array([-axis[1],axis[0]],np.float32)
            centers=[np.array(x['center'],np.float32) for x in cluster]
            if min(abs(float(np.dot(cc-x,normal))) for x in centers)>0.18*min(w,h):
                continue
            cluster.append(c);placed=True;break
        if not placed:clusters.append([c])
    out=[]
    for cluster in clusters:
        if len(cluster)<2:continue
        lengths=sorted(x['length'] for x in cluster)
        mean_angle=sum(x['angle'] for x in cluster)/len(cluster)
        centers=np.array([x['center'] for x in cluster],np.float32)
        spread=float(np.linalg.norm(centers.max(axis=0)-centers.min(axis=0)))
        out.append({'count':len(cluster),'angle':round(mean_angle,2),'median_length':round(float(np.median(lengths)),2),'spread':round(spread,2),'members':cluster})
    return sorted(out,key=lambda c:(c['count'],c['spread']),reverse=True)


def draw(image:np.ndarray,candidates:list[dict[str,Any]],clusters:list[dict[str,Any]])->np.ndarray:
    out=image.copy()
    cluster_map={id(m):idx for idx,c in enumerate(clusters) for m in c['members']}
    for idx,c in enumerate(candidates,1):
        pts=np.array(c['polygon'],np.int32)
        cv2.polylines(out,[pts],True,(0,255,255),2,cv2.LINE_AA)
        x,y=map(int,c['center'])
        cv2.putText(out,f"{idx} L{int(c['length'])} W{int(c['width'])} A{int(c['angle'])}",(x+4,y-4),cv2.FONT_HERSHEY_SIMPLEX,.38,(0,255,255),1,cv2.LINE_AA)
    return out


def main()->int:
    p=argparse.ArgumentParser(description='Over-detect connector-like line pairs on a raw motherboard image')
    p.add_argument('--image',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--config',type=Path)
    a=p.parse_args(); cfg=json.loads(a.config.read_text()) if a.config else {}
    image=cv2.imread(str(a.image))
    if image is None:raise ValueError(f'cannot decode {a.image}')
    candidates=detect_connector_candidates(image,cfg);clusters=cluster_candidates(candidates,image.shape)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    overlay=a.output_dir/'connector-candidates-overlay.jpg';report=a.output_dir/'connector-candidates.json'
    cv2.imwrite(str(overlay),draw(image,candidates,clusters))
    report.write_text(json.dumps({'image':str(a.image),'candidate_count':len(candidates),'cluster_count':len(clusters),'candidates':candidates,'clusters':clusters,'overlay':str(overlay)},indent=2)+'\n')
    print(json.dumps({'candidate_count':len(candidates),'cluster_count':len(clusters),'overlay':str(overlay),'report':str(report)}))
    return 0
if __name__=='__main__':raise SystemExit(main())

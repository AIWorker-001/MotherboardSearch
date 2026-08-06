#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def rotate_bound(image: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0]); sin = abs(matrix[0, 1])
    nw = int(h * sin + w * cos); nh = int(h * cos + w * sin)
    matrix[0, 2] += nw / 2.0 - center[0]
    matrix[1, 2] += nh / 2.0 - center[1]
    return cv2.warpAffine(image, matrix, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), matrix


def inverse_affine(matrix: np.ndarray) -> np.ndarray:
    return cv2.invertAffineTransform(matrix)


def transform_polygon(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.transform(points, matrix).reshape(-1, 2)


def dark_slot_candidates(image: np.ndarray, angle: float, config: dict[str, Any]) -> list[dict[str, Any]]:
    rotated, matrix = rotate_bound(image, -angle)
    inverse = inverse_affine(matrix)
    gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    candidates: list[dict[str, Any]] = []
    for kernel_length in config.get('kernel_lengths', [70, 110, 160, 220, 300]):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(kernel_length), int(config.get('kernel_height', 9))))
        response = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
        _, binary = cv2.threshold(response, int(config.get('threshold', 18)), 255, cv2.THRESH_BINARY)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3)), iterations=1)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if h <= 0:
                continue
            aspect = w / h
            if aspect < float(config.get('minimum_aspect', 5.0)):
                continue
            if w < float(config.get('minimum_length', 45)) or h > float(config.get('maximum_width', 34)):
                continue
            if w > rotated.shape[1] * 0.65:
                continue
            roi = response[y:y+h, x:x+w]
            strength = float(np.mean(roi)) if roi.size else 0.0
            poly = np.asarray([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype=np.float32)
            original_poly = transform_polygon(poly, inverse)
            center = original_poly.mean(axis=0)
            candidates.append({
                'angle': round(angle % 180.0, 2),
                'length': round(float(w), 2),
                'width': round(float(h), 2),
                'aspect': round(float(aspect), 2),
                'strength': round(strength, 2),
                'polygon': np.rint(original_poly).astype(int).tolist(),
                'center': [round(float(center[0]), 2), round(float(center[1]), 2)],
                'kernel_length': int(kernel_length),
            })
    return candidates


def bbox_iou(a: list[list[int]], b: list[list[int]]) -> float:
    ax = [p[0] for p in a]; ay = [p[1] for p in a]
    bx = [p[0] for p in b]; by = [p[1] for p in b]
    x1=max(min(ax),min(bx)); y1=max(min(ay),min(by)); x2=min(max(ax),max(bx)); y2=min(max(ay),max(by))
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=max(1,(max(ax)-min(ax))*(max(ay)-min(ay)))
    bb=max(1,(max(bx)-min(bx))*(max(by)-min(by)))
    return inter/max(1.0,aa+bb-inter)


def dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = sorted(candidates, key=lambda c: (c['strength'], c['aspect'], c['length']), reverse=True)
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        if any(bbox_iou(candidate['polygon'], prior['polygon']) > 0.45 for prior in kept):
            continue
        kept.append(candidate)
    return kept


def bank_score(group: list[dict[str, Any]], image_shape: tuple[int, int, int], target: str) -> float:
    if len(group) < 2:
        return 0.0
    h, w = image_shape[:2]
    lengths = np.asarray([c['length'] for c in group], dtype=np.float32)
    centers = np.asarray([c['center'] for c in group], dtype=np.float32)
    mean_angle = float(np.mean([c['angle'] for c in group]))
    axis = np.asarray([math.cos(math.radians(mean_angle)), math.sin(math.radians(mean_angle))], dtype=np.float32)
    normal = np.asarray([-axis[1], axis[0]], dtype=np.float32)
    offsets = sorted(float(np.dot(center, normal)) for center in centers)
    gaps = np.diff(offsets) if len(offsets)>1 else np.asarray([])
    spacing_cv = float(np.std(gaps)/max(1e-6,np.mean(gaps))) if len(gaps)>1 else 0.0
    count = len(group)
    center_x = float(np.mean(centers[:,0]))/w
    center_y = float(np.mean(centers[:,1]))/h
    length_cv = float(np.std(lengths)/max(1e-6,np.mean(lengths)))
    if target == 'dimm':
        return max(0.0, min(1.0,
            0.32*max(0.0,1.0-abs(count-4)/3.0)+
            0.26*max(0.0,1.0-length_cv/0.28)+
            0.22*max(0.0,1.0-spacing_cv/0.45)+
            0.20*max(0.0,min(1.0,(center_x-0.45)/0.4))
        ))
    long_count = int(np.sum(lengths >= np.median(lengths)*0.82))
    short_count = int(np.sum(lengths <= np.median(lengths)*0.65))
    return max(0.0, min(1.0,
        0.25*max(0.0,min(1.0,(count-2)/5.0))+
        0.20*max(0.0,1.0-spacing_cv/0.75)+
        0.20*max(0.0,min(1.0,(0.6-center_x)/0.5))+
        0.15*max(0.0,min(1.0,(0.75-center_y)/0.6))+
        0.20*min(1.0,(long_count+short_count)/max(1,count))
    ))


def group_by_angle_and_neighborhood(candidates: list[dict[str, Any]], image_shape: tuple[int,int,int]) -> list[list[dict[str, Any]]]:
    h,w=image_shape[:2]
    groups: list[list[dict[str, Any]]] = []
    for candidate in candidates:
        center=np.asarray(candidate['center'],np.float32)
        placed=False
        for group in groups:
            mean_angle=float(np.mean([c['angle'] for c in group]))
            delta=abs((candidate['angle']-mean_angle+90)%180-90)
            if delta>5.5:
                continue
            centers=[np.asarray(c['center'],np.float32) for c in group]
            if min(float(np.linalg.norm(center-other)) for other in centers)>0.28*min(w,h):
                continue
            group.append(candidate); placed=True; break
        if not placed:
            groups.append([candidate])
    return groups


def detect(image: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    all_candidates=[]
    for angle in config.get('angles', list(range(0,180,5))):
        all_candidates.extend(dark_slot_candidates(image,float(angle),config))
    candidates=dedupe(all_candidates)
    groups=group_by_angle_and_neighborhood(candidates,image.shape)
    scored=[]
    for group in groups:
        if len(group)<2:
            continue
        scored.append({
            'count':len(group),
            'mean_angle':round(float(np.mean([c['angle'] for c in group])),2),
            'pcie_score':round(bank_score(group,image.shape,'pcie'),4),
            'dimm_score':round(bank_score(group,image.shape,'dimm'),4),
            'members':group,
        })
    scored.sort(key=lambda g:max(g['pcie_score'],g['dimm_score']),reverse=True)
    pcie=max(scored,key=lambda g:g['pcie_score'],default=None)
    dimm=max(scored,key=lambda g:g['dimm_score'],default=None)
    return {'candidate_count':len(candidates),'groups':scored,'pcie_bank':pcie,'dimm_bank':dimm}


def draw(image: np.ndarray, result: dict[str, Any]) -> np.ndarray:
    out=image.copy()
    for key,color in [('pcie_bank',(0,255,0)),('dimm_bank',(0,255,255))]:
        bank=result.get(key)
        if not bank:
            continue
        for idx,c in enumerate(bank['members'],1):
            pts=np.asarray(c['polygon'],np.int32)
            cv2.polylines(out,[pts],True,color,3,cv2.LINE_AA)
            x,y=map(int,c['center'])
            cv2.putText(out,f'{key.split("_")[0].upper()}{idx}',(x+4,y-4),cv2.FONT_HERSHEY_SIMPLEX,.5,color,2,cv2.LINE_AA)
    return out


def main()->int:
    p=argparse.ArgumentParser(description='Dedicated oriented dark-slot detector for PCIe and DIMM banks')
    p.add_argument('--image',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--config',type=Path,default=Path('config/oriented_connector_detector.json'))
    a=p.parse_args();image=cv2.imread(str(a.image))
    if image is None:raise ValueError(f'cannot decode {a.image}')
    config=json.loads(a.config.read_text())
    result=detect(image,config)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    overlay=a.output_dir/'oriented-connectors-overlay.jpg';report=a.output_dir/'oriented-connectors.json'
    cv2.imwrite(str(overlay),draw(image,result));report.write_text(json.dumps({**result,'overlay':str(overlay)},indent=2)+'\n')
    print(json.dumps({'candidate_count':result['candidate_count'],'pcie_score':None if not result['pcie_bank'] else result['pcie_bank']['pcie_score'],'dimm_score':None if not result['dimm_bank'] else result['dimm_bank']['dimm_score'],'overlay':str(overlay),'report':str(report)}))
    return 0
if __name__=='__main__':raise SystemExit(main())

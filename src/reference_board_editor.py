#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

FEATURES = [
    ('board_corners', 'Board corners', 4, '#2563eb'),
    ('rear_io', 'Rear I/O edge polygon', 4, '#f59e0b'),
    ('pcie_x16', 'PCIe x16 slot', 4, '#22c55e'),
    ('pcie_x1', 'PCIe x1 slot', 4, '#22d3ee'),
    ('dimm', 'DIMM slot', 4, '#fde047'),
    ('cpu_search', 'CPU search region', 4, '#d946ef'),
    ('cpu_socket', 'CPU socket', 4, '#ef4444'),
    ('rear_cpu_bracket', 'Rear CPU bracket', 4, '#92400e'),
]


def build_editor_html(image_name: str, width: int, height: int, initial: dict[str, Any] | None = None) -> str:
    initial_json = json.dumps(initial or {}, separators=(',', ':'))
    feature_json = json.dumps([
        {'key': key, 'label': label, 'points': points, 'color': color}
        for key, label, points, color in FEATURES
    ])
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Motherboard Reference Editor</title>
<style>
body{{margin:0;font-family:system-ui;background:#111;color:#eee;display:grid;grid-template-columns:330px 1fr;height:100vh}}
aside{{padding:14px;overflow:auto;border-right:1px solid #444}} main{{overflow:auto;display:flex;align-items:flex-start;justify-content:center;padding:16px}}
canvas{{max-width:none;box-shadow:0 0 0 1px #555;background:#222;cursor:crosshair}}
button,select,input{{width:100%;margin:5px 0;padding:8px;background:#222;color:#eee;border:1px solid #555}}
.row{{display:flex;gap:6px}} .row button{{width:50%}} pre{{white-space:pre-wrap;font-size:11px;background:#181818;padding:8px}}
.small{{font-size:12px;color:#bbb}} .swatch{{display:inline-block;width:12px;height:12px;margin-right:6px}}
</style></head>
<body><aside>
<h2>Reference Board Editor</h2>
<p class="small">Click the exact connector corners in the photo. Do not use guessed canonical rectangles. Save polygons in image coordinates; normalization happens automatically.</p>
<select id="feature"></select>
<input id="label" placeholder="Label, e.g. PCIEX16_1 or DIMM_A1">
<div class="row"><button id="finish">Finish polygon</button><button id="undo">Undo point</button></div>
<div class="row"><button id="delete">Delete selected</button><button id="clear">Clear all</button></div>
<button id="download">Download annotation JSON</button>
<button id="downloadOverlay">Download overlay PNG</button>
<p id="status"></p><div id="items"></div><pre id="json"></pre>
</aside><main><canvas id="canvas" width="{width}" height="{height}"></canvas></main>
<script>
const features={feature_json}; const initial={initial_json};
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d');
const img=new Image(); img.src={json.dumps(image_name)};
let records=[]; let active=[]; let selected=-1;
const feature=document.getElementById('feature'),label=document.getElementById('label');
for(const f of features){{const o=document.createElement('option');o.value=f.key;o.textContent=f.label;feature.appendChild(o)}}
function meta(key){{return features.find(x=>x.key===key)}}
function normalize(points){{return points.map(([x,y])=>[+(x/canvas.width).toFixed(6),+(y/canvas.height).toFixed(6)])}}
function exportData(){{const groups={{}};for(const r of records){{(groups[r.type]??=[]).push({{label:r.label,polygon:r.points,polygon_normalized:normalize(r.points)}})}}
return {{schema_version:3,image:img.src.split('/').pop(),image_size:[canvas.width,canvas.height],annotations:groups}}}}
function draw(){{ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
for(let i=0;i<records.length;i++) drawPoly(records[i],i===selected); if(active.length) drawPoly({{type:feature.value,label:label.value||'ACTIVE',points:active}},true); renderSide()}}
function drawPoly(r,sel){{const m=meta(r.type);ctx.beginPath();r.points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));if(r.points.length>2)ctx.closePath();ctx.strokeStyle=m.color;ctx.lineWidth=sel?6:3;ctx.stroke();ctx.fillStyle=m.color;for(const [x,y] of r.points){{ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill()}}if(r.points.length){{ctx.font='bold 18px sans-serif';ctx.fillText(r.label||m.label,r.points[0][0]+7,r.points[0][1]-7)}}}}
function renderSide(){{document.getElementById('status').textContent=`Active points: ${{active.length}} / ${{meta(feature.value).points}}`;
const items=document.getElementById('items');items.innerHTML='';records.forEach((r,i)=>{{const b=document.createElement('button');b.innerHTML=`<span class=swatch style="background:${{meta(r.type).color}}"></span>${{r.label||r.type}}`;b.onclick=()=>{{selected=i;draw()}};items.appendChild(b)}});document.getElementById('json').textContent=JSON.stringify(exportData(),null,2)}}
canvas.onclick=e=>{{const rect=canvas.getBoundingClientRect();const x=(e.clientX-rect.left)*canvas.width/rect.width,y=(e.clientY-rect.top)*canvas.height/rect.height;active.push([Math.round(x),Math.round(y)]);if(active.length===meta(feature.value).points)finish();else draw()}}
function finish(){{if(active.length<3)return;const base=label.value.trim()||meta(feature.value).label;records.push({{type:feature.value,label:base,points:active}});active=[];label.value='';selected=records.length-1;draw()}}
document.getElementById('finish').onclick=finish;document.getElementById('undo').onclick=()=>{{active.pop();draw()}};
document.getElementById('delete').onclick=()=>{{if(selected>=0)records.splice(selected,1);selected=-1;draw()}};
document.getElementById('clear').onclick=()=>{{if(confirm('Clear all annotations?')){{records=[];active=[];selected=-1;draw()}}}};
function download(blob,name){{const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}}
document.getElementById('download').onclick=()=>download(new Blob([JSON.stringify(exportData(),null,2)],{{type:'application/json'}}),'reference-annotation.json');
document.getElementById('downloadOverlay').onclick=()=>canvas.toBlob(b=>download(b,'reference-overlay.png'));
img.onload=()=>{{if(initial.annotations){{for(const [type,rows] of Object.entries(initial.annotations))for(const row of rows)records.push({{type,label:row.label,points:row.polygon}})}}draw()}};
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate a standalone browser editor for exact motherboard reference polygons')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial', type=Path)
    args = parser.parse_args()
    from PIL import Image
    with Image.open(args.image) as image:
        width, height = image.size
    initial = json.loads(args.initial.read_text()) if args.initial else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_editor_html(args.image.name, width, height, initial), encoding='utf-8')
    target = args.output.parent / args.image.name
    if target.resolve() != args.image.resolve():
        target.write_bytes(args.image.read_bytes())
    print(json.dumps({'editor': str(args.output), 'image': str(target), 'size': [width, height]}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

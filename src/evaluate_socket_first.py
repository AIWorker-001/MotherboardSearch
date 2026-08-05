#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main()->int:
 p=argparse.ArgumentParser(description='Evaluate socket-first detector against human labels')
 p.add_argument('--results',type=Path,required=True);p.add_argument('--benchmark',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();results={str(r['item_id']):r for r in json.loads(a.results.read_text())};bench=json.loads(a.benchmark.read_text())['items']
 rows=[]
 for expected in bench:
  actual=results.get(str(expected['item_id']),{})
  rows.append({'item_id':expected['item_id'],'expected_cpu_state':expected['expected_cpu_state'],'actual_cpu_state':actual.get('cpu_state'),'correct':actual.get('cpu_state')==expected['expected_cpu_state'],'socket_localized':int(actual.get('socket_localized_images') or 0)>0})
 summary={'items':len(rows),'correct':sum(r['correct'] for r in rows),'accuracy':round(sum(r['correct'] for r in rows)/max(1,len(rows)),4),'socket_localized':sum(r['socket_localized'] for r in rows),'rows':rows}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
try:
    from .motherboard_kb import load_catalog, verify_model
except ImportError:
    from motherboard_kb import load_catalog, verify_model


def main() -> int:
    parser=argparse.ArgumentParser(description='Verify stated motherboard models against the reference knowledge base')
    parser.add_argument('--identifications',type=Path,required=True)
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path('config/motherboard_kb.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    catalog=load_catalog(Path(config['catalog']))
    rows=[]
    for item in json.loads(args.identifications.read_text()):
        board=item.get('motherboard') or {}
        model=board.get('text')
        images=sorted(args.cache_dir.glob(f"{item['item_id']}_*.jpg"))
        result=verify_model(config,catalog,model,images) if model else {'model':None,'status':'model_unknown','identity_score':0.0,'best_match':None}
        result['item_id']=item['item_id']
        result['manual_review_required']=result['status'] in {'reference_conflict','reference_uncertain'}
        rows.append(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'items':len(rows),'confirmed':sum(r['status']=='reference_confirmed' for r in rows),'review':sum(r['manual_review_required'] for r in rows)}))
    return 0
if __name__=='__main__': raise SystemExit(main())

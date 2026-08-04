import json,re,requests,subprocess
from io import BytesIO
from pathlib import Path
from PIL import Image
import torch
from transformers import CLIPModel,CLIPProcessor
items=json.load(open('/tmp/sgw/true_galleries.json'))
prompts=['a motherboard with a silver CPU visibly installed in the socket','a motherboard with an empty CPU socket','a motherboard with a black CPU socket protective cover','a motherboard with a CPU cooler installed over the socket','a motherboard photo where the CPU socket is not visible']
labels=['installed','empty','cover','cooler','unclear']
model=CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); proc=CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); model.eval()
res=[]; root=Path('/tmp/sgw/true_gallery_images');root.mkdir(exist_ok=True)
for item in items:
 rows=[]
 for i,u in enumerate(item['urls'],1):
  r=requests.get(u,timeout=30);r.raise_for_status();im=Image.open(BytesIO(r.content)).convert('RGB');p=root/f"{item['id']}_{i}.jpg";im.save(p)
  inp=proc(text=prompts,images=im,return_tensors='pt',padding=True)
  with torch.no_grad(): probs=model(**inp).logits_per_image.softmax(1)[0].tolist()
  ocr=subprocess.run(['tesseract',str(p),'stdout'],capture_output=True,text=True).stdout
  rows.append({'i':i,'url':u,'scores':{labels[j]:round(v,4) for j,v in enumerate(probs)},'ocr':ocr[:250]})
 best_inst=max((x['scores']['installed'] for x in rows),default=0);best_empty=max((x['scores']['empty'] for x in rows),default=0);best_cover=max((x['scores']['cover'] for x in rows),default=0);best_cooler=max((x['scores']['cooler'] for x in rows),default=0)
 cpu_text=any(re.search(r'\b(INTEL|RYZEN|CORE\s*I[3579]|AMD)\b',x['ocr'],re.I) for x in rows)
 if cpu_text or best_inst>=0.58: verdict='CPU visible/likely installed'
 elif best_empty>=0.58: verdict='Empty socket visible'
 elif best_cover>=0.58: verdict='Socket cover visible'
 elif best_cooler>=0.60: verdict='Cooler present; CPU not directly visible'
 else: verdict='Unclear'
 item.update({'verdict':verdict,'installed':round(best_inst,3),'empty':round(best_empty,3),'cover':round(best_cover,3),'cooler':round(best_cooler,3),'cpu_text':cpu_text,'images':rows});res.append(item)
 print(item['id'],verdict,best_inst,best_empty,best_cover,best_cooler,cpu_text,flush=True)
Path('/tmp/sgw/true_gallery_report.json').write_text(json.dumps(res,indent=2))

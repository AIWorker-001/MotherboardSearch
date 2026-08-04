import json,torch
from pathlib import Path
from PIL import Image
from transformers import CLIPModel,CLIPProcessor
items=json.load(open('/tmp/sgw/true_gallery_report.json'))
model=CLIPModel.from_pretrained('openai/clip-vit-base-patch32');proc=CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32');model.eval()
prompts=['a close-up of a silver metal CPU installed in a motherboard socket','a close-up of an empty CPU socket on a motherboard','a close-up of a black plastic CPU socket cover','a close-up of motherboard components not showing the CPU socket']
for item in items:
 best=[(0,None,None) for _ in prompts]
 for imeta in item['images']:
  p=Path('/tmp/sgw/true_gallery_images')/f"{item['id']}_{imeta['i']}.jpg"
  im=Image.open(p).convert('RGB');w,h=im.size
  crops=[]
  # full plus overlapping 2x2 and 3x3 crops
  crops.append(('full',im))
  for grid in (2,3):
   cw,ch=w//grid,h//grid
   for y in range(grid):
    for x in range(grid):
     box=(max(0,x*cw-cw//5),max(0,y*ch-ch//5),min(w,(x+1)*cw+cw//5),min(h,(y+1)*ch+ch//5))
     crops.append((f'g{grid}-{x}-{y}',im.crop(box)))
  for name,c in crops:
   inp=proc(text=prompts,images=c,return_tensors='pt',padding=True)
   with torch.no_grad(): probs=model(**inp).logits_per_image.softmax(1)[0].tolist()
   for j,v in enumerate(probs):
    if v>best[j][0]:best[j]=(v,imeta['i'],name)
 print(item['id'],'installed',best[0],'empty',best[1],'cover',best[2],'other',best[3])

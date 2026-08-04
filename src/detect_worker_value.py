import json, re, subprocess
from io import BytesIO
from pathlib import Path
import requests, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

# Use corrected true galleries when available; otherwise skip.
items=json.load(open('/tmp/sgw/true_galleries.json'))
model=CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
proc=CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
model.eval()
prompts=[
 'a motherboard with an Intel stock CPU cooler and fan mounted over the processor',
 'a motherboard with an AMD Wraith CPU cooler and fan mounted over the processor',
 'a motherboard with a tower CPU heatsink and fan mounted over the processor',
 'a motherboard with a silver metal CPU visibly installed in the socket',
 'a motherboard with an empty CPU socket',
 'a motherboard with a black plastic CPU socket cover',
 'a motherboard with RAM memory modules installed',
 'a motherboard with an M.2 NVMe SSD installed',
 'a motherboard without a CPU cooler or visible CPU',
]
labels=['intel_cooler','amd_cooler','tower_cooler','cpu_visible','empty_socket','socket_cover','ram','nvme','none']
root=Path('/tmp/sgw/value_images');root.mkdir(exist_ok=True)
results=[]
for item in items:
    per=[]
    for i,u in enumerate(item.get('urls',[]),1):
        r=requests.get(u,timeout=30);r.raise_for_status()
        im=Image.open(BytesIO(r.content)).convert('RGB');p=root/f"{item['id']}_{i}.jpg";im.save(p)
        w,h=im.size
        crops=[('full',im)]
        for grid in (2,3):
            cw,ch=w//grid,h//grid
            for y in range(grid):
                for x in range(grid):
                    box=(max(0,x*cw-cw//6),max(0,y*ch-ch//6),min(w,(x+1)*cw+cw//6),min(h,(y+1)*ch+ch//6))
                    crops.append((f'g{grid}-{x}-{y}',im.crop(box)))
        best={k:(0,None) for k in labels}
        for cname,c in crops:
            inp=proc(text=prompts,images=c,return_tensors='pt',padding=True)
            with torch.no_grad(): probs=model(**inp).logits_per_image.softmax(1)[0].tolist()
            for j,v in enumerate(probs):
                if v>best[labels[j]][0]:best[labels[j]]=(float(v),cname)
        ocr=subprocess.run(['tesseract',str(p),'stdout'],capture_output=True,text=True).stdout
        per.append({'image':i,'best':{k:{'score':round(v[0],4),'crop':v[1]} for k,v in best.items()},'ocr':ocr[:300]})
    maxima={k:max((x['best'][k]['score'] for x in per),default=0) for k in labels}
    # Conservative rules: mounted cooler is decisive; bare CPU requires stronger evidence than empty socket.
    cooler=max(maxima['intel_cooler'],maxima['amd_cooler'],maxima['tower_cooler'])
    cpu=maxima['cpu_visible']; empty=maxima['empty_socket']; cover=maxima['socket_cover']
    if cooler>=0.62 and cooler>max(empty,cover)+0.08:
        cpu_state='cooler_attached_cpu_highly_likely'
    elif cpu>=0.68 and cpu>empty+0.08:
        cpu_state='visible_cpu_likely'
    elif empty>=0.66 and empty>cpu+0.08:
        cpu_state='empty_socket_likely'
    elif cover>=0.66:
        cpu_state='socket_cover_likely'
    else:
        cpu_state='unclear'
    value_score=0
    if cpu_state=='cooler_attached_cpu_highly_likely': value_score+=100
    elif cpu_state=='visible_cpu_likely': value_score+=80
    elif cpu_state=='empty_socket_likely': value_score-=100
    elif cpu_state=='socket_cover_likely': value_score-=60
    if maxima['ram']>=0.60:value_score+=35
    if maxima['nvme']>=0.60:value_score+=25
    result={'id':item['id'],'title':item['title'],'cpu_state':cpu_state,'value_score':value_score,'maxima':{k:round(v,3) for k,v in maxima.items()},'images':per}
    results.append(result)
    print(item['id'],cpu_state,'score',value_score,'cooler',round(cooler,3),'cpu',round(cpu,3),'empty',round(empty,3),'cover',round(cover,3),'ram',round(maxima['ram'],3),'nvme',round(maxima['nvme'],3))
Path('/tmp/sgw/worker_value_report.json').write_text(json.dumps(results,indent=2))

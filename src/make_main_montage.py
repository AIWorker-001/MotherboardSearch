import json, urllib.request
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
items=json.load(open('galleries.json'))
# image 2 in each stored list is the listing's primary image; logo is image 1
thumbs=[]
for item in items:
    url=item['urls'][1]
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    data=urllib.request.urlopen(req,timeout=30).read()
    im=Image.open(BytesIO(data)).convert('RGB')
    im.thumbnail((300,220))
    thumbs.append((item['id'],im.copy()))
out=Image.new('RGB',(900,5*250),'white')
d=ImageDraw.Draw(out); font=ImageFont.load_default()
for i,(item_id,im) in enumerate(thumbs):
    x=(i%3)*300; y=(i//3)*250
    d.text((x+4,y+4),item_id,fill='black',font=font)
    out.paste(im,(x+(300-im.width)//2,y+25+(220-im.height)//2))
out.save('motherboard_main_montage.jpg',quality=68,optimize=True)
print('motherboard_main_montage.jpg',out.size)

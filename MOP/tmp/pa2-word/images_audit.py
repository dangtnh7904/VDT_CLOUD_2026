from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from PIL import Image, ImageOps, ImageDraw
src=Path(r'D:\career\VDT\GD2\upgrade_Ceph\MOP\MOP OSD.docx')
out=Path(r'D:\career\VDT\GD2\upgrade_Ceph\MOP\tmp\pa2-word')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(src) as z:
    for f in z.namelist():
        if f.startswith('word/media/'):
            p=out/Path(f).name; p.write_bytes(z.read(f))
    for p in etree.fromstring(z.read('word/document.xml')).xpath('.//w:body/w:p[w:r/w:drawing]',namespaces=ns):
        prev=p.getprevious();print('After:', ''.join(prev.xpath('.//w:t/text()',namespaces=ns)) if prev is not None else '')
files=[f for f in out.glob('image*') if f.suffix.lower() in ['.png','.jpg','.jpeg']]
thumbs=[]
for f in files:
    im=Image.open(f).convert('RGB'); im.thumbnail((640,350))
    tile=Image.new('RGB',(660,390),'white');tile.paste(im,((660-im.width)//2,25));ImageDraw.Draw(tile).text((10,5),f.name,fill='black');thumbs.append(tile)
canvas=Image.new('RGB',(1320,390*((len(thumbs)+1)//2)),'#dddddd')
for i,im in enumerate(thumbs):canvas.paste(im,((i%2)*660,(i//2)*390))
canvas.save(out/'reference-images.png')
print('IMAGES',len(files))


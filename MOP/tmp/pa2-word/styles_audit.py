from pathlib import Path
from lxml import etree
from zipfile import ZipFile
p=Path(r'D:\career\VDT\GD2\upgrade_Ceph\MOP\MOP OSD.docx')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(p) as z:
    root=etree.fromstring(z.read('word/styles.xml'))
    for sid in ['Normal','Title','Heading1','Heading2','Heading3','ListParagraph']:
        e=root.xpath('//w:style[@w:styleId="'+sid+'"]',namespaces=ns)
        print(sid, etree.tostring(e[0]).decode() if e else 'MISSING')
    print('FEATURES',[(x,len(etree.fromstring(z.read('word/document.xml')).xpath('.//w:'+x,namespaces=ns))) for x in ['drawing','fldChar','sdt','sectPr']])

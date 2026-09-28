import docx
from docx.oxml.ns import qn
import zipfile
import xml.etree.ElementTree as ET

# 1. Check raw document.xml for highlight
with zipfile.ZipFile('REPORT_TECNICO_PIPELINE_ECDC Con correzioni.docx') as z:
    doc_xml = z.read('word/document.xml').decode('utf-8')
    print("Contains 'w:highlight':", 'w:highlight' in doc_xml)
    print("Contains 'highlight':", 'highlight' in doc_xml)
    print("Contains 'comment':", 'comment' in doc_xml)
    
    # Check what files are in the zip
    print("\nFiles in docx zip:")
    for name in z.namelist():
        if 'comment' in name or 'track' in name:
            print("  Special part:", name)

# Let's find any occurrences of 'highlight' or 'shd' or comments in the XML
tree = ET.fromstring(doc_xml)
namespaces = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
}

highlights = tree.findall('.//w:highlight', namespaces)
print(f"Total w:highlight elements: {len(highlights)}")
for h in highlights:
    print("Highlight attr:", h.attrib)

# Let's inspect paragraphs containing highlight or yellow shading
for p in tree.findall('.//w:p', namespaces):
    hl_runs = p.findall('.//w:r[w:rPr/w:highlight]', namespaces)
    if hl_runs:
        texts = [t.text for t in p.findall('.//w:t', namespaces) if t.text]
        hl_texts = ["".join([t.text for t in r.findall('.//w:t', namespaces) if t.text]) for r in hl_runs]
        print(f"\n--- Paragraph with highlight: ---")
        print("Full:", "".join(texts))
        print("Highlighted:", hl_texts)

# What about shading on runs (w:rPr/w:shd)?
shd_runs = tree.findall('.//w:r[w:rPr/w:shd]', namespaces)
print(f"Total w:r with w:shd: {len(shd_runs)}")
for r in shd_runs:
    shd = r.find('w:rPr/w:shd', namespaces)
    t = "".join([x.text for x in r.findall('.//w:t', namespaces) if x.text])
    print(f"Run shd {shd.attrib}: '{t}'")


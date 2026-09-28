import pymupdf, glob, re

p = glob.glob(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1\CLINICAL_DIARIES*\*.pdf")[0]
doc = pymupdf.open(p)

for idx, page in enumerate(doc):
    text = page.get_text()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_lines = lines[:10]
    dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', text)
    giornate = re.findall(r'\b\d+°?\s*giornata\b', text, re.IGNORECASE)
    timestamps = [l for l in lines if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', l)]
    print(f"Page {idx+1}: Giornate={giornate} | Dates={dates[:4]}... | Times={timestamps[:3]}")

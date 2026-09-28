import pymupdf, glob, re
from datetime import datetime

p = glob.glob(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1\CLINICAL_DIARIES*\*.pdf")[0]
doc = pymupdf.open(p)

for idx, page in enumerate(doc):
    raw_text = page.get_text()
    # Strip footer after "Documento firmato digitalmente"
    footer_split = re.split(r"Documento firmato digitalmente", raw_text, flags=re.IGNORECASE)
    body_text = footer_split[0]
    
    # Extract dates in body text
    body_dates = re.findall(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', body_text)
    giornate = re.findall(r'\b(\d+)°?\s*giornata\b', body_text, re.IGNORECASE)
    times = re.findall(r'\b(\d{1,2}:\d{2}:\d{2})\b', body_text)
    
    print(f"Page {idx+1:02d}: Giornate={giornate} | Body Dates={body_dates[:3]} | First Time={times[0] if times else None}")

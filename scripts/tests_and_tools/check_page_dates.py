import pymupdf, glob, re

p = glob.glob(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1\CLINICAL_DIARIES*\*.pdf")[0]
doc = pymupdf.open(p)

for idx, page in enumerate(doc):
    text = page.get_text()
    # Remove the print stamp at the bottom
    # Often "Stampa \n Documento firmato digitalmente ... \n 03/01/2000"
    clean = re.split(r"Documento firmato digitalmente", text)[0]
    # Look for dates
    dates = re.findall(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', clean)
    giornate = re.findall(r'\b(\d+)°?\s*giornata\b', clean, re.IGNORECASE)
    # Also look for dates in prescription lines like "dal 08:00" or "termina domani" or dates
    print(f"Page {idx+1:02d}: Body dates: {dates} | Giornate: {giornate}")

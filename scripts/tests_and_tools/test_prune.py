import os
from pipeline.config import DATA_DIR
from pipeline.ingestion_parser import IngestionParser
import re

candidates = [os.path.join(DATA_DIR, d) for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
parser = IngestionParser(candidates[0] if candidates else DATA_DIR)
data = parser.parse_all()

def prune_admission_text(text: str, max_chars: int = 3000) -> str:
    # Remove large repetitive blanks / boilerplate
    clean = re.sub(r"\n\s*\n+", "\n", text)
    clean = re.sub(r"[_\.]{4,}", "", clean)
    clean = re.sub(r"Sede Legale[\s\S]*?Verbale di Pronto Soccorso", "Verbale di Pronto Soccorso", clean, flags=re.IGNORECASE)
    # If still very long, extract primary clinical sections
    if len(clean) > max_chars:
        # Keep first max_chars which contains Triage, Motivo visita, Valutazione, Parametri, Anamnesi
        clean = clean[:max_chars] + "\n[... Estratto sezioni cliniche primarie ...]"
    return clean

print("Original admission lengths:")
for r in data["admission_reports"]:
    print(f"  {r['filename']}: {len(r['text'])} chars -> pruned: {len(prune_admission_text(r['text']))} chars")

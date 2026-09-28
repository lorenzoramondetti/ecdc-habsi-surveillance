import os
from pipeline.config import DATA_DIR
from pipeline.ingestion_parser import IngestionParser

if __name__ == '__main__':
    candidates = [os.path.join(DATA_DIR, d) for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    if not candidates:
        print("[!] Nessun paziente trovato in DATA_DIR")
        exit(0)
    parser = IngestionParser(candidates[0])
    micro = parser.parse_microbiology()
    print(f"Microbiology reports count for {os.path.basename(candidates[0])}: {len(micro)}")
    for m in micro:
        print(f"File: {m['filename']} | Specimen: {m['specimen']} | Prelievo: {m['prelievo_date']} | Positive: {m['is_positive']} | Isolates: {m['isolates']}")

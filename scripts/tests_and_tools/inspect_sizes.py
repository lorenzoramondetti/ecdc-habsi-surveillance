import os
from pipeline.config import DATA_DIR
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker

if __name__ == '__main__':
    candidates = [os.path.join(DATA_DIR, d) for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    if not candidates:
        print("[!] Nessun paziente trovato in DATA_DIR")
        exit(0)
    parser = IngestionParser(candidates[0])
    data = parser.parse_all()

    print(f"--- ADMISSION REPORTS ({os.path.basename(candidates[0])}) ---")
    for rep in data["admission_reports"]:
        print(f"Report: {rep['filename']} - Pages: {rep['pages']} - Chars: {len(rep['text'])}")

    print("\n--- CLINICAL DIARIES ---")
    for d in data["clinical_diaries"]:
        print(f"Page {d['page_number']}: Chars: {len(d['text'])} - Dates: {d['dates']} - Giornate: {d['giornate']}")

    print("\n--- MICROBIOLOGY ---")
    for m in data["microbiology_reports"]:
        print(f"Micro: {m['filename']} - Chars: {len(m['full_text'])}")

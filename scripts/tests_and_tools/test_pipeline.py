import os
import sys
import pandas as pd
from pipeline.config import DATA_DIR, GOLD_STANDARD_PATH
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.benchmark import BenchmarkEvaluator

def test_all():
    print("=== TEST INGESTION & CHUNKING SU TUTTI I 10 PAZIENTI ===")
    patients = sorted([d for d in os.listdir(DATA_DIR) if d.startswith("Paziente_")])
    assert len(patients) == 10, f"Attesi 10 pazienti, trovati {len(patients)}"
    print(f"Trovati {len(patients)} pazienti:")

    total_chunks = 0
    for p in patients:
        pdir = os.path.join(DATA_DIR, p)
        parser = IngestionParser(pdir)
        data = parser.parse_all()
        chunker = TemporalChunker(data)
        chunks = chunker.build_daily_chunks()
        total_chunks += len(chunks)
        print(f"  - {p}: {len(chunks)} giorni ({chunks[0]['date']} -> {chunks[-1]['date']}) | Micro: {len(data['microbiology_reports'])}")

    print(f"\nTotale chunk giornalieri generati per i 10 pazienti: {total_chunks}")

    print("\n=== TEST CARICAMENTO GOLD STANDARD ===")
    evaluator = BenchmarkEvaluator(GOLD_STANDARD_PATH)
    print(f"Righe caricate da gold standard: {len(evaluator.gold_df)}")
    print("Primi 5 pazienti nel gold standard:")
    print(evaluator.gold_df[["Codice cartella cartella ", "BSI?", "HA BSI?", "Origine dell'infezione", "Luogo acquisizione"]].head(5).to_string())

    print("\n[V] Tutti i test di base sono stati superati con successo!")

if __name__ == "__main__":
    test_all()

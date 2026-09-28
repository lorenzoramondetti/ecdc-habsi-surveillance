import os
import sys
import json
import time
import argparse
from typing import List, Dict, Any

from pipeline.config import (
    DATA_DIR, CHUNKS_DIR, EXTRACTIONS_DIR, DEFAULT_MODEL, BENCHMARK_MODELS, AVAILABLE_MODELS
)
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.llm_client import OllamaClient
from pipeline.ecdc_classifier import ECDCClassifier
from pipeline.tabulator import Tabulator
from pipeline.benchmark import BenchmarkEvaluator

def process_patient(patient_dir: str, model_name: str, force_recompute: bool = False) -> Dict[str, Any]:
    patient_id = os.path.basename(patient_dir).replace("Paziente_", "")
    print(f"\n=======================================================")
    print(f"[*] Elaborazione Paziente: {patient_id} con modello: {model_name}")
    print(f"=======================================================")

    t_patient_start = time.time()

    # 1. Ingestion
    print("[1/4] Ingestione e parsing documenti suddivisi per sottocartella...")
    parser = IngestionParser(patient_dir)
    data = parser.parse_all()
    parsed_microbiology = data.get("microbiology_reports", [])
    print(f"      -> Ingestiti {len(data['admission_reports'])} verbali ingresso, {len(data['clinical_diaries'])} pagine diario, {len(parsed_microbiology)} referti micro.")

    # 2. Chunking
    print("[2/4] Chunking temporale per data e giornata di degenza...")
    chunker = TemporalChunker(data)
    chunks = chunker.build_daily_chunks()
    chunker.save_chunks(CHUNKS_DIR)
    print(f"      -> Generati {len(chunks)} chunk giornalieri compatti.")

    # 3. LLM Extraction (Sequential & VRAM Safe)
    print(f"[3/4] Estrazione entità cliniche con LLM ({model_name})...")
    client = OllamaClient(model_name=model_name)
    daily_extractions = []
    total_model_latency = 0.0

    for idx, c in enumerate(chunks):
        print(f"      [Day {c['day_number']:02d} - {c['date']}] Elaborazione (~{int(c['token_estimate'])} token)...")
        ext = client.extract_from_chunk(c, force_recompute=force_recompute)
        daily_extractions.append(ext)
        lat = ext.get("latency_seconds", 0.0)
        total_model_latency += lat
        print(f"      -> Concluso in {lat}s.")

    # 4. Deterministic ECDC Classification with Integrated Lab Microbiology
    print("[4/4] Applicazione motore deterministico ECDC...")
    classifier = ECDCClassifier(
        patient_id=patient_id,
        daily_extractions=daily_extractions,
        parsed_microbiology=parsed_microbiology
    )
    classification = classifier.classify()

    total_patient_wall_time = time.time() - t_patient_start

    print("\n>>> RISULTATO CLASSIFICAZIONE ECDC:")
    print(f"    - BSI: {classification['bsi']}")
    print(f"    - HA-BSI: {classification['ha_bsi']}")
    print(f"    - Origine: {classification['origine']}")
    print(f"    - Luogo di Acquisizione: {classification['luogo_acquisizione']}")
    print(f"    - Patogeno: {classification.get('diagnostic_pathogen')}")
    print(f"    - Tempo totale: {total_patient_wall_time:.1f}s (Latenza LLM: {total_model_latency:.1f}s)")
    print("    - Audit Trail:")
    for step in classification["audit_trail"]:
        print(f"      * {step}")

    return {
        "patient_id": patient_id,
        "daily_extractions": daily_extractions,
        "parsed_microbiology": parsed_microbiology,
        "classification": classification,
        "latency_seconds": total_model_latency,
        "wall_time_seconds": total_patient_wall_time
    }

def run_benchmark(patient_dirs: List[str], models: List[str], force_recompute: bool = False):
    benchmark_evaluator = BenchmarkEvaluator()
    model_reports = []

    for model in models:
        print(f"\n#######################################################")
        print(f"### AVVIO BENCHMARK PER IL MODELLO: {model}")
        print(f"#######################################################")

        model_patient_extractions = {}
        model_patient_microbiology = {}
        model_predictions = {}
        patient_latencies = {}

        for pdir in patient_dirs:
            pid = os.path.basename(pdir).replace("Paziente_", "")
            res = process_patient(pdir, model_name=model, force_recompute=force_recompute)
            model_patient_extractions[pid] = res["daily_extractions"]
            model_patient_microbiology[pid] = res["parsed_microbiology"]
            model_predictions[pid] = res["classification"]
            patient_latencies[pid] = res["latency_seconds"]

        # Tabulate results for this model
        clean_name = OllamaClient(model_name=model).clean_model_name
        tabulator = Tabulator(model_patient_extractions, model_patient_microbiology)
        tab_xlsx = tabulator.save_timeline_table(filename_prefix=f"timeline_{clean_name}")
        db_xlsx = tabulator.populate_db_schema(model_predictions, filename_prefix=f"db_populated_{clean_name}")
        print(f"\n[+] Tabelle salvate:")
        print(f"    Master Timeline: {tab_xlsx}")
        print(f"    CRF DB 199 colonne: {db_xlsx}")

        # Evaluate against human gold standard with Cohen's Kappa & Time Analysis
        rep = benchmark_evaluator.evaluate_model(
            model_name=model,
            predictions=model_predictions,
            patient_latencies=patient_latencies
        )
        model_reports.append(rep)

        # Unload model to release VRAM before next model
        OllamaClient(model_name=model).unload_model()

    # Final multi-model comparison
    final_report_path = benchmark_evaluator.save_benchmark_report(model_reports)
    print(f"\n=======================================================")
    print(f"[V] BENCHMARK COMPLETATO! Report salvato in: {final_report_path}")
    print(f"=======================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline di sorveglianza e benchmark BSI ECDC")
    parser.add_argument("--patient", type=str, default=None, help="ID o cartella del singolo paziente (es. 0E691DF1)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Nome del modello Ollama da usare")
    parser.add_argument("--benchmark", action="store_true", help="Esegui il benchmark su tutti i modelli e pazienti")
    parser.add_argument("--force", action="store_true", help="Forza il ricalcolo ignorando la cache")
    parser.add_argument("--ui", action="store_true", help="Avvia l'interfaccia web dedicata minimale")
    parser.add_argument("--port", type=int, default=5050, help="Porta per l'interfaccia web (default: 5050)")

    args = parser.parse_args()

    if args.ui:
        from pipeline.app_server import run_server
        run_server(port=args.port)
        sys.exit(0)

    all_patients = [
        os.path.join(DATA_DIR, d)
        for d in sorted(os.listdir(DATA_DIR))
        if os.path.isdir(os.path.join(DATA_DIR, d)) and d.startswith("Paziente_")
    ]

    if args.patient:
        target_dir = None
        for p in all_patients:
            if args.patient in p:
                target_dir = p
                break
        if not target_dir:
            print(f"Paziente {args.patient} non trovato in {DATA_DIR}")
            sys.exit(1)
        res = process_patient(target_dir, model_name=args.model, force_recompute=args.force)
    elif args.benchmark:
        run_benchmark(patient_dirs=all_patients, models=BENCHMARK_MODELS, force_recompute=args.force)
    else:
        # Default: process first patient
        res = process_patient(all_patients[0], model_name=args.model, force_recompute=args.force)

import os
import sys

# Ensure immediate unbuffered console and log output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

import json
import time
import argparse
import pandas as pd
from typing import List, Dict, Any

from pipeline.config import (
    BASE_DIR, DATA_DIR, CHUNKS_DIR, EXTRACTIONS_DIR, TABLES_DIR, BENCHMARK_DIR,
    GOLD_STANDARD_PATH
)
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.llm_client import OllamaClient
from pipeline.ecdc_classifier import ECDCClassifier
from pipeline.tabulator import Tabulator
from pipeline.benchmark import BenchmarkEvaluator

BENCHMARK_MODELS_CONFIG = [
    {
        "name": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
        "label": "Qwen 3.8 27B",
        "clean_dir": "Qwen3.8-27B"
    },
    {
        "name": "gemma4:e4b",
        "label": "Gemma 4 e4b",
        "clean_dir": "Gemma4-e4b"
    },
    {
        "name": "glm-4.7-flash:latest",
        "label": "GLM-4.7-Flash",
        "clean_dir": "GLM"
    },
    {
        "name": "gemma4:12b",
        "label": "Gemma 4 12B",
        "clean_dir": "Gemma4-12b"
    }
]

def load_validated_patient_ids() -> List[str]:
    """Loads validated patient IDs from Etichette cartelle_validazione umana.xlsx."""
    df = pd.read_excel(GOLD_STANDARD_PATH, sheet_name="Suddivisione Cartelle")
    valid_df = df[df["BSI?"].notna() & (df["BSI?"].astype(str).str.strip().isin(["SI", "NO", "si", "no"]))].copy()
    valid_ids = []
    for c in valid_df["Codice cartella cartella "].dropna().astype(str).str.strip():
        pid = c if c.startswith("Paziente_") else f"Paziente_{c}"
        if pid not in valid_ids:
            valid_ids.append(pid)
    return valid_ids

def run_benchmark_for_model(
    model_cfg: Dict[str, str],
    validated_patients: List[str],
    evaluator: BenchmarkEvaluator,
    force_recompute: bool = False
) -> Dict[str, Any]:
    model_name = model_cfg["name"]
    model_label = model_cfg["label"]
    clean_dir = model_cfg["clean_dir"]
    
    print("\n" + "="*80)
    print(f"[*] AVVIO BENCHMARK PER: {model_label} ({model_name})")
    print(f"[*] Totale pazienti validati da elaborare: {len(validated_patients)}")
    print("="*80 + "\n")
    
    client = OllamaClient(model_name=model_name)
    model_patient_extractions = {}
    model_patient_microbiology = {}
    model_predictions = {}
    patient_latencies = {}
    
    total_start = time.time()
    
    for p_idx, p_code in enumerate(validated_patients, 1):
        p_path = os.path.join(DATA_DIR, p_code)
        if not os.path.exists(p_path):
            print(f"[-] ATTENZIONE: Cartella non trovata per {p_code} in {DATA_DIR}. Skip.")
            continue
            
        pid_clean = p_code.replace("Paziente_", "")
        t_pz_start = time.time()
        
        # 1. Parsing
        parser = IngestionParser(p_path)
        data = parser.parse_all()
        micro = data.get("microbiology_reports", [])
        model_patient_microbiology[pid_clean] = micro
        
        # 2. Chunking
        chunker = TemporalChunker(data)
        chunks = chunker.build_daily_chunks()
        
        # 3. LLM Extraction
        daily_ext = []
        tot_model_lat = 0.0
        cached_count = 0
        new_count = 0
        
        for c in chunks:
            # Check cache
            day_num = c["day_number"]
            d_clean = c["date"].replace("/", "-")
            cache_file = os.path.join(
                EXTRACTIONS_DIR, client.clean_model_name, p_code, f"extraction_day_{day_num:02d}_{d_clean}.json"
            )
            is_cached = os.path.exists(cache_file) and not force_recompute
            
            ext = client.extract_from_chunk(c, force_recompute=force_recompute)
            daily_ext.append(ext)
            lat = ext.get("latency_seconds", 0.0)
            tot_model_lat += lat
            if is_cached:
                cached_count += 1
            else:
                new_count += 1
                
        model_patient_extractions[pid_clean] = daily_ext
        patient_latencies[pid_clean] = tot_model_lat
        
        # 4. ECDC Classifier
        clf = ECDCClassifier(
            patient_id=pid_clean,
            daily_extractions=daily_ext,
            parsed_microbiology=micro,
            admission_reports=data.get("admission_reports", [])
        )
        classification = clf.classify()
        model_predictions[pid_clean] = classification
        
        pz_wall_time = time.time() - t_pz_start
        status_cache = f"({cached_count} cache, {new_count} inferiti)"
        print(f"[{p_idx:02d}/{len(validated_patients)}] {p_code} | Giorni: {len(chunks)} {status_cache} | LLM Lat: {tot_model_lat:.1f}s (Wall: {pz_wall_time:.1f}s) | BSI: {classification['bsi']} | HA: {classification['ha_bsi']} | Origine: {classification['origine']}")
    
    # Tabulation
    print(f"\n[+] Generazione tabelle per {model_label}...")
    tabulator = Tabulator(model_patient_extractions, model_patient_microbiology)
    model_bench_dir = os.path.join(BENCHMARK_DIR, clean_dir)
    os.makedirs(model_bench_dir, exist_ok=True)
    
    tab_xlsx = tabulator.save_timeline_table(filename_prefix=f"timeline_{client.clean_model_name}")
    db_xlsx = tabulator.populate_db_schema(model_predictions, filename_prefix=f"db_populated_{client.clean_model_name}")
    
    # Copy/Save into Benchmark model folder as well
    import shutil
    shutil.copy2(tab_xlsx, os.path.join(model_bench_dir, f"benchmark_timeline_{client.clean_model_name}.xlsx"))
    shutil.copy2(db_xlsx, os.path.join(model_bench_dir, f"benchmark_db_{client.clean_model_name}.xlsx"))
    
    # Also mirror into root Benchmark/clean_dir
    root_bench_dir = os.path.join(BASE_DIR, "Benchmark", clean_dir)
    os.makedirs(root_bench_dir, exist_ok=True)
    shutil.copy2(tab_xlsx, os.path.join(root_bench_dir, f"benchmark_timeline_{client.clean_model_name}.xlsx"))
    shutil.copy2(db_xlsx, os.path.join(root_bench_dir, f"benchmark_db_{client.clean_model_name}.xlsx"))
    
    # Evaluation against Gold Standard
    print(f"[+] Calcolo metriche diagnostiche ed efficienza per {model_label}...")
    rep = evaluator.evaluate_model(
        model_name=model_label,
        predictions=model_predictions,
        patient_latencies=patient_latencies
    )
    
    # Unload model from VRAM
    client.unload_model()
    
    met = rep["metrics"]
    t = rep["time_analysis"]
    print("\n" + "-"*60)
    print(f"=== RISULTATI CONSOLIDATI ({len(model_predictions)} Pazienti): {model_label} ===")
    print(f"  Accuratezza BSI:  {met['accuracy']*100:.1f}%  (IC 95%: {met['accuracy_ci95'][0]*100:.1f}% - {met['accuracy_ci95'][1]*100:.1f}%)")
    print(f"  Sensibilità BSI:  {met['sensitivity']*100:.1f}%  (IC 95%: {met['sensitivity_ci95'][0]*100:.1f}% - {met['sensitivity_ci95'][1]*100:.1f}%)")
    print(f"  Specificità BSI:  {met['specificity']*100:.1f}%  (IC 95%: {met['specificity_ci95'][0]*100:.1f}% - {met['specificity_ci95'][1]*100:.1f}%)")
    print(f"  PPV: {met['ppv']*100:.1f}% | NPV: {met['npv']*100:.1f}% | F1: {met['f1_score']:.3f} | Cohen Kappa BSI: {met['cohen_kappa_bsi']:.3f}")
    print(f"  Accuratezza HA-BSI: {met['ha_bsi_accuracy']*100:.1f}% | Cohen Kappa HA: {met['cohen_kappa_ha_bsi']:.3f}")
    print(f"  Accuratezza Origine: {met['origin_accuracy']*100:.1f}% | Accuratezza Setting: {met['setting_accuracy']*100:.1f}%")
    print(f"  Tempo Umano: {t['total_human_time_min']:.1f} min | Tempo LLM: {t['total_llm_time_min']:.2f} min ({t['total_llm_time_sec']:.1f}s) | Risparmiato: {t['time_saved_percent']:.1f}%")
    print("-"*60 + "\n")
    
    return rep

def main():
    parser = argparse.ArgumentParser(description="Esecuzione del Benchmark Clinico ECDC sui pazienti validati umanamente")
    parser.add_argument("--models", type=str, default=None, help="Elenco modelli separati da virgola (default: tutti i 4 modelli)")
    parser.add_argument("--limit", type=int, default=None, help="Limita il numero di pazienti elaborati")
    parser.add_argument("--force", action="store_true", help="Forza il ricalcolo ignorando le estrazioni in cache")
    args = parser.parse_args()
    
    validated_patients = load_validated_patient_ids()
    print(f"[*] Individuati {len(validated_patients)} pazienti con etichetta validata nel Gold Standard.")
    
    if args.limit:
        validated_patients = validated_patients[:args.limit]
        print(f"[*] Limitato a {len(validated_patients)} pazienti per test rapido.")
        
    evaluator = BenchmarkEvaluator()
    
    # Filter models to run
    models_to_run = BENCHMARK_MODELS_CONFIG
    if args.models:
        filter_keys = [k.strip().lower() for k in args.models.split(",")]
        models_to_run = [
            m for m in BENCHMARK_MODELS_CONFIG
            if any(k in m["label"].lower() or k in m["name"].lower() or k in m["clean_dir"].lower() for k in filter_keys)
        ]
        
    print(f"[*] Modelli da benchmarkare ({len(models_to_run)}): {[m['label'] for m in models_to_run]}")
    
    all_reports = []
    for m_cfg in models_to_run:
        rep = run_benchmark_for_model(
            model_cfg=m_cfg,
            validated_patients=validated_patients,
            evaluator=evaluator,
            force_recompute=args.force
        )
        all_reports.append(rep)
        
        # Save intermediate report after each model finishes
        final_xlsx = evaluator.save_benchmark_report(all_reports)
        import shutil
        shutil.copy2(final_xlsx, os.path.join(BASE_DIR, "Benchmark", "benchmark_comparison_models.xlsx"))
        md_src = os.path.join(BENCHMARK_DIR, "benchmark_comparison_models.md")
        if os.path.exists(md_src):
            shutil.copy2(md_src, os.path.join(BASE_DIR, "Benchmark", "benchmark_comparison_models.md"))
        print(f"[V] Report intermedio salvato con {len(all_reports)} modello/i completati.\n")
        
    print("\n" + "#"*80)
    print("### BENCHMARK COMPLETATO SU TUTTI I MODELLI! ###")
    print("#"*80)
    for r in all_reports:
        m = r["model_name"]
        met = r["metrics"]
        t = r["time_analysis"]
        print(f"{m:15s} | BSI Acc: {met['accuracy']*100:5.1f}% | Sens: {met['sensitivity']*100:5.1f}% | Spec: {met['specificity']*100:5.1f}% | Kappa: {met['cohen_kappa_bsi']:.3f} | HA Acc: {met['ha_bsi_accuracy']*100:5.1f}% | LLM Min: {t['total_llm_time_min']:6.2f} min")

if __name__ == "__main__":
    main()

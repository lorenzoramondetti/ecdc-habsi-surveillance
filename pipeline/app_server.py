import os
import json
import time
import threading
from typing import Dict, Any, List
from flask import Flask, request, jsonify, send_from_directory, send_file
import pandas as pd
import requests

from pipeline.config import (
    BASE_DIR, DATA_DIR, OUTPUT_DIR, TABLES_DIR, EXTRACTIONS_DIR,
    TESSY_DIR, BENCHMARK_DIR, DEFAULT_MODEL, AVAILABLE_MODELS,
    GOLD_STANDARD_PATH, OLLAMA_URL
)
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.llm_client import OllamaClient
from pipeline.ecdc_classifier import ECDCClassifier
from pipeline.tabulator import Tabulator
from pipeline.benchmark import BenchmarkEvaluator
from pipeline.tessy_exporter import TESSyExporter
from run_pipeline import process_patient

WEB_DIR = os.path.join(BASE_DIR, "web")
os.makedirs(WEB_DIR, exist_ok=True)

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")

# Dynamic state tracking for asynchronous multi-model benchmarking
benchmark_lock = threading.Lock()
benchmark_state = {
    "status": "idle",       # "idle", "running", "completed", "error", "cancelled"
    "progress": 0.0,
    "current_model": "",
    "current_patient": "",
    "patient_index": 0,
    "total_patients": 0,
    "model_index": 0,
    "total_models": 0,
    "elapsed_seconds": 0.0,
    "logs": [],
    "error_message": "",
    "results": None,
    "downloads": {}
}
stop_benchmark_flag = False

# Active data directory (can be switched dynamically from UI)
CURRENT_DATA_DIR = DATA_DIR

def log_bench_message(msg: str):
    with benchmark_lock:
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        benchmark_state["logs"].append(entry)
        if len(benchmark_state["logs"]) > 200:
            benchmark_state["logs"].pop(0)
    print(f"[*] {msg}")

@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/benchmark/<path:filename>")
def serve_benchmark_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, "Benchmark"), filename)

@app.route("/api/config", methods=["GET"])
def get_config():
    global CURRENT_DATA_DIR
    available_dirs = []
    
    # Check possible candidate data directories in workspace
    for item in os.listdir(BASE_DIR):
        p = os.path.join(BASE_DIR, item)
        if os.path.isdir(p) and ("cartell" in item.lower() or "data" in item.lower() or "pazient" in item.lower()):
            available_dirs.append({"name": item, "path": p, "is_active": (p == CURRENT_DATA_DIR)})

    return jsonify({
        "current_data_dir": CURRENT_DATA_DIR,
        "available_dirs": available_dirs,
        "base_dir": BASE_DIR,
        "gold_standard_path": GOLD_STANDARD_PATH
    })

@app.route("/api/config/data_dir", methods=["POST"])
def set_data_dir():
    global CURRENT_DATA_DIR
    data = request.json or {}
    new_dir = data.get("data_dir", "").strip()

    if not new_dir:
        return jsonify({"error": "Percorso cartella mancante"}), 400

    # Support relative paths
    if not os.path.isabs(new_dir):
        new_dir = os.path.join(BASE_DIR, new_dir)

    if not os.path.exists(new_dir) or not os.path.isdir(new_dir):
        return jsonify({"error": f"La cartella specificata non esiste: {new_dir}"}), 404

    CURRENT_DATA_DIR = new_dir
    log_bench_message(f"Cartella dati clinici impostata su: {CURRENT_DATA_DIR}")
    return jsonify({"status": "success", "current_data_dir": CURRENT_DATA_DIR})

@app.route("/api/models", methods=["GET"])
def get_models():
    """Dynamically queries Ollama daemon to return all installed models."""
    detected_models = []
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            tags = resp.json().get("models", [])
            for m in tags:
                name = m.get("name", "")
                if name and name not in detected_models:
                    detected_models.append(name)
    except Exception:
        pass

    # Merge with default known models
    final_models = list(detected_models)
    for m in AVAILABLE_MODELS:
        if m not in final_models:
            final_models.append(m)

    return jsonify({
        "models": final_models,
        "default": DEFAULT_MODEL,
        "ollama_active": len(detected_models) > 0
    })

@app.route("/api/patients", methods=["GET"])
def get_patients():
    global CURRENT_DATA_DIR
    try:
        evaluator = BenchmarkEvaluator()
        gold_df = evaluator.gold_df
    except Exception:
        gold_df = pd.DataFrame()

    patients = []
    if os.path.exists(CURRENT_DATA_DIR):
        for item in sorted(os.listdir(CURRENT_DATA_DIR)):
            item_path = os.path.join(CURRENT_DATA_DIR, item)
            if os.path.isdir(item_path) and ("Paziente_" in item or "synthetic" in item or "pz" in item.lower()):
                pid = item.replace("Paziente_", "")
                gold_label = "-"
                gold_ha = "-"
                gold_origin = "-"
                if not gold_df.empty:
                    match = gold_df[gold_df["clean_id"] == item]
                    if not match.empty:
                        gold_label = str(match.iloc[0].get("BSI?", "-"))
                        gold_ha = str(match.iloc[0].get("HA BSI?", "-"))
                        gold_origin = str(match.iloc[0].get("Origine dell'infezione", "-"))

                subfolders = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d))]
                patients.append({
                    "id": pid,
                    "folder_name": item,
                    "subfolders": subfolders,
                    "gold_bsi": gold_label,
                    "gold_ha_bsi": gold_ha,
                    "gold_origin": gold_origin
                })
    return jsonify({"patients": patients, "data_dir": CURRENT_DATA_DIR})

@app.route("/api/run", methods=["POST"])
def run_single():
    global CURRENT_DATA_DIR
    data = request.json or {}
    patient_id = data.get("patient_id", "").strip()
    model_name = data.get("model_name", DEFAULT_MODEL).strip()
    force = bool(data.get("force", False))

    if not patient_id:
        return jsonify({"error": "Parametro patient_id obbligatorio"}), 400

    target_dir = os.path.join(CURRENT_DATA_DIR, f"Paziente_{patient_id}")
    if not os.path.exists(target_dir):
        for item in os.listdir(CURRENT_DATA_DIR):
            if patient_id in item:
                target_dir = os.path.join(CURRENT_DATA_DIR, item)
                break

    if not os.path.exists(target_dir):
        return jsonify({"error": f"Cartella per paziente {patient_id} non trovata in {CURRENT_DATA_DIR}"}), 404

    try:
        res = process_patient(target_dir, model_name=model_name, force_recompute=force)
        pid = res["patient_id"]

        tabulator = Tabulator({pid: res["daily_extractions"]}, {pid: res.get("parsed_microbiology", [])})
        clean_model = OllamaClient(model_name=model_name).clean_model_name
        timeline_rows = tabulator.generate_timeline_rows()
        timeline_xlsx = tabulator.save_timeline_table(f"timeline_{pid}_{clean_model}")
        db_xlsx = tabulator.populate_db_schema({pid: res["classification"]}, f"db_{pid}_{clean_model}")

        # TESSy export for single patient
        exporter = TESSyExporter()
        tessy_csv = exporter.export_to_csv({pid: res["classification"]}, filename=f"tessy_{pid}_{clean_model}.csv")

        # Benchmark evaluation comparison with Gold Standard
        evaluator = BenchmarkEvaluator()
        gold_row = evaluator.gold_df[evaluator.gold_df["clean_id"] == f"Paziente_{pid}"]
        gold_data = {}
        if not gold_row.empty:
            g = gold_row.iloc[0]
            gold_data = {
                "bsi": str(g.get("BSI?", "")).strip(),
                "ha_bsi": str(g.get("HA BSI?", "")).strip(),
                "origine": str(g.get("Origine dell'infezione", "")).strip(),
                "luogo": str(g.get("Luogo acquisizione", "")).strip()
            }

        human_time_min = evaluator.get_human_time_minutes(pid)
        llm_time_sec = res["latency_seconds"]
        llm_time_min = llm_time_sec / 60.0
        time_saved_min = max(0.0, human_time_min - llm_time_min)
        time_saved_pct = (time_saved_min / human_time_min * 100.0) if human_time_min > 0 else 0.0

        return jsonify({
            "status": "success",
            "patient_id": pid,
            "model_name": model_name,
            "classification": res["classification"],
            "gold_standard": gold_data,
            "time_analysis": {
                "human_time_min": round(human_time_min, 1),
                "llm_time_sec": round(llm_time_sec, 1),
                "llm_time_min": round(llm_time_min, 2),
                "time_saved_min": round(time_saved_min, 1),
                "time_saved_percent": round(time_saved_pct, 1)
            },
            "timeline": timeline_rows,
            "downloads": {
                "timeline_xlsx": f"/api/download/table/timeline_{pid}_{clean_model}.xlsx",
                "db_xlsx": f"/api/download/table/db_{pid}_{clean_model}.xlsx",
                "tessy_csv": f"/api/download/tessy/tessy_{pid}_{clean_model}.csv"
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------------------------------------
# Asynchronous Multi-Model Benchmark Runner
# -------------------------------------------------------------
def _async_benchmark_worker(models: List[str], patient_ids: List[str], force: bool, data_dir: str):
    global benchmark_state, stop_benchmark_flag

    log_bench_message(f"Avvio sessione di benchmark su {len(models)} modelli e {len(patient_ids)} pazienti.")
    start_time = time.time()
    model_reports = []

    try:
        evaluator = BenchmarkEvaluator()
        total_steps = len(models) * len(patient_ids)
        current_step = 0

        for m_idx, model in enumerate(models, 1):
            if stop_benchmark_flag:
                log_bench_message("Benchmark interrotto dall'utente.")
                break

            with benchmark_lock:
                benchmark_state["current_model"] = model
                benchmark_state["model_index"] = m_idx
                benchmark_state["total_models"] = len(models)

            log_bench_message(f"--- Modello [{m_idx}/{len(models)}]: {model} ---")

            model_extractions = {}
            model_microbiology = {}
            model_predictions = {}
            patient_latencies = {}

            for p_idx, pid in enumerate(patient_ids, 1):
                if stop_benchmark_flag:
                    break

                target_dir = os.path.join(data_dir, f"Paziente_{pid}")
                if not os.path.exists(target_dir):
                    for item in os.listdir(data_dir):
                        if pid in item:
                            target_dir = os.path.join(data_dir, item)
                            break

                with benchmark_lock:
                    benchmark_state["current_patient"] = pid
                    benchmark_state["patient_index"] = p_idx
                    benchmark_state["total_patients"] = len(patient_ids)
                    current_step += 1
                    benchmark_state["progress"] = round((current_step / total_steps) * 100.0, 1)
                    benchmark_state["elapsed_seconds"] = round(time.time() - start_time, 1)

                log_bench_message(f"[{m_idx}/{len(models)}] {model} | Paziente [{p_idx}/{len(patient_ids)}]: {pid}")

                res = process_patient(target_dir, model_name=model, force_recompute=force)
                model_extractions[pid] = res["daily_extractions"]
                model_microbiology[pid] = res.get("parsed_microbiology", [])
                model_predictions[pid] = res["classification"]
                patient_latencies[pid] = res["latency_seconds"]

            if stop_benchmark_flag:
                break

            # Tabulate model results
            clean_name = OllamaClient(model_name=model).clean_model_name
            tabulator = Tabulator(model_extractions, model_microbiology)
            tab_xlsx = tabulator.save_timeline_table(filename_prefix=f"benchmark_timeline_{clean_name}")
            db_xlsx = tabulator.populate_db_schema(model_predictions, filename_prefix=f"benchmark_db_{clean_name}")

            # Export TESSy CSV
            tessy_exp = TESSyExporter()
            tessy_file = tessy_exp.export_to_csv(model_predictions, filename=f"tessy_benchmark_{clean_name}.csv")

            # Evaluate against Gold Standard
            rep = evaluator.evaluate_model(model_name=model, predictions=model_predictions, patient_latencies=patient_latencies)
            model_reports.append(rep)

            # Unload model to release VRAM before next model
            OllamaClient(model_name=model).unload_model()

        if not stop_benchmark_flag:
            evaluator.save_benchmark_report(model_reports)
            with benchmark_lock:
                benchmark_state["status"] = "completed"
                benchmark_state["progress"] = 100.0
                benchmark_state["results"] = model_reports
                benchmark_state["downloads"] = {
                    "benchmark_excel": "/api/download/benchmark/benchmark_comparison_models.xlsx",
                    "tessy_export": "/api/download/tessy/tessy_benchmark_all.csv"
                }
            log_bench_message("Benchmark completato con successo su tutti i modelli selezionati!")
        else:
            with benchmark_lock:
                benchmark_state["status"] = "cancelled"

    except Exception as e:
        with benchmark_lock:
            benchmark_state["status"] = "error"
            benchmark_state["error_message"] = str(e)
        log_bench_message(f"ERRORE durante il benchmark: {str(e)}")

@app.route("/api/benchmark/start", methods=["POST"])
def start_benchmark():
    global benchmark_state, stop_benchmark_flag, CURRENT_DATA_DIR

    with benchmark_lock:
        if benchmark_state["status"] == "running":
            return jsonify({"error": "Un benchmark è già in esecuzione"}), 400

    data = request.json or {}
    models = data.get("models", [DEFAULT_MODEL])
    if isinstance(models, str):
        models = [models]

    req_patients = data.get("patients", "all")
    force = bool(data.get("force", False))
    chosen_data_dir = data.get("data_dir", CURRENT_DATA_DIR)

    # Resolve patients list
    patient_ids = []
    if os.path.exists(chosen_data_dir):
        for item in sorted(os.listdir(chosen_data_dir)):
            item_path = os.path.join(chosen_data_dir, item)
            if os.path.isdir(item_path) and ("Paziente_" in item or "synthetic" in item or "pz" in item.lower()):
                pid = item.replace("Paziente_", "")
                if req_patients == "all" or pid in req_patients or item in req_patients:
                    patient_ids.append(pid)

    if not patient_ids:
        return jsonify({"error": f"Nessun paziente trovato in {chosen_data_dir}"}), 400

    with benchmark_lock:
        stop_benchmark_flag = False
        benchmark_state["status"] = "running"
        benchmark_state["progress"] = 0.0
        benchmark_state["logs"] = []
        benchmark_state["results"] = None
        benchmark_state["error_message"] = ""

    t = threading.Thread(
        target=_async_benchmark_worker,
        args=(models, patient_ids, force, chosen_data_dir),
        daemon=True
    )
    t.start()

    return jsonify({
        "status": "started",
        "models": models,
        "patients_count": len(patient_ids),
        "data_dir": chosen_data_dir
    })

@app.route("/api/benchmark/status", methods=["GET"])
def get_benchmark_status():
    with benchmark_lock:
        return jsonify(dict(benchmark_state))

@app.route("/api/benchmark/stop", methods=["POST"])
def stop_benchmark():
    global stop_benchmark_flag
    stop_benchmark_flag = True
    log_bench_message("Segnale di interruzione inviato...")
    return jsonify({"status": "stopping"})

@app.route("/api/download/<folder_type>/<path:filename>")
def download_file(folder_type, filename):
    if folder_type == "table":
        folder = TABLES_DIR
    elif folder_type == "benchmark":
        folder = os.path.join(BASE_DIR, "Benchmark")
    elif folder_type == "tessy":
        folder = TESSY_DIR
    else:
        folder = OUTPUT_DIR
    return send_from_directory(folder, filename, as_attachment=True)

def run_server(host="127.0.0.1", port=5050):
    print(f"\n=======================================================")
    print(f"[*] Avvio Server Web Sorveglianza ECDC...")
    print(f"    URL: http://{host}:{port}")
    print(f"=======================================================\n")
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    run_server()

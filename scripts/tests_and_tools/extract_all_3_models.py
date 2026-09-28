import os, json
import pandas as pd
from pipeline.benchmark import BenchmarkEvaluator
from pipeline.ecdc_classifier import ECDCClassifier
from pipeline.ingestion_parser import IngestionParser

evaluator = BenchmarkEvaluator()
models = {
    "Qwen 3.8 27B": "Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest",
    "Gemma 4 12B": "gemma4_12b",
    "GLM-4.7-Flash": "glm-4.7-flash_latest"
}

all_reports = []

for m_label, m_dir in models.items():
    ext_base = os.path.join("output", "extractions", m_dir)
    predictions = {}
    latencies = {}
    
    for p_folder in sorted(os.listdir(ext_base)):
        p_path = os.path.join(ext_base, p_folder)
        if not os.path.isdir(p_path):
            continue
        pid = p_folder.replace("Paziente_", "")
        
        daily = []
        tot_lat = 0.0
        for f in sorted(os.listdir(p_path)):
            if f.endswith(".json"):
                with open(os.path.join(p_path, f), "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                    daily.append(data)
                    tot_lat += data.get("latency_seconds", 0.0)
                    
        raw_pdir = os.path.join("Prime cartelle cliniche anonimizzate", p_folder)
        parser = IngestionParser(raw_pdir)
        raw_data = parser.parse_all()
        micro = raw_data.get("microbiology_reports", [])
        
        clf = ECDCClassifier(patient_id=pid, daily_extractions=daily, parsed_microbiology=micro)
        res = clf.classify()
        
        predictions[pid] = res
        latencies[pid] = tot_lat
        
    rep = evaluator.evaluate_model(model_name=m_label, predictions=predictions, patient_latencies=latencies)
    all_reports.append(rep)

print("=== SUMMARY METRICS ===")
for r in all_reports:
    m = r["model_name"]
    met = r["metrics"]
    t = r["time_analysis"]
    print(f"\nModel: {m}")
    print(f"  Acc BSI: {met['accuracy']*100:.1f}% {met['accuracy_ci95']}")
    print(f"  Sens BSI: {met['sensitivity']*100:.1f}% {met['sensitivity_ci95']}")
    print(f"  Spec BSI: {met['specificity']*100:.1f}% {met['specificity_ci95']}")
    print(f"  PPV: {met['ppv']*100:.1f}% | NPV: {met['npv']*100:.1f}% | F1: {met['f1_score']} | Kappa BSI: {met['cohen_kappa_bsi']}")
    print(f"  HA Acc: {met['ha_bsi_accuracy']*100:.1f}% | HA Kappa: {met['cohen_kappa_ha_bsi']}")
    print(f"  Orig Acc: {met['origin_accuracy']*100:.1f}% | Setting Acc: {met['setting_accuracy']*100:.1f}")
    print(f"  Human Time: {t['total_human_time_min']:.1f} min | LLM Time: {t['total_llm_time_min']:.2f} min ({t['total_llm_time_sec']:.1f}s) | Saved: {t['time_saved_percent']:.1f}%")

# Print per-patient comparison for all 3 models
print("\n=== PER PATIENT LATENCY (SECONDS) ===")
lat_table = []
for pid in [c["Paziente"] for c in all_reports[0]["comparisons"]]:
    row = {"Paziente": pid}
    for r in all_reports:
        m = r["model_name"]
        for c in r["comparisons"]:
            if c["Paziente"] == pid:
                row[f"Time_{m}"] = c["Tempo_LLM_Sec"]
                row[f"Pred_BSI_{m}"] = c["Pred_BSI"]
                row[f"Pred_HA_{m}"] = c["Pred_HA_BSI"]
    lat_table.append(row)
print(pd.DataFrame(lat_table).to_string())

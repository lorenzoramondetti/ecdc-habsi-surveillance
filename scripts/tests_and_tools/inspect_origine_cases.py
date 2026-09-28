import os, sys, json
sys.path.insert(0, os.path.abspath("."))
from pipeline.benchmark import BenchmarkEvaluator
from pipeline.config import DATA_DIR, EXTRACTIONS_DIR
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.ecdc_classifier import ECDCClassifier

evaluator = BenchmarkEvaluator()
gold_df = evaluator.gold_df
orig_df = gold_df[gold_df["Origine dell'infezione"].notna()].copy()
print(f"Total validated Origine cases: {len(orig_df)}")

model_dir = os.path.join(EXTRACTIONS_DIR, "Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest")

for _, row in orig_df.iterrows():
    raw_id = str(row['clean_id']).strip()
    pid = raw_id.replace('Paziente_', '')
    gold_val = str(row["Origine dell'infezione"]).strip()
    p_code = f"Paziente_{pid}"
    p_path = os.path.join(DATA_DIR, p_code)
    if not os.path.exists(p_path):
        print(f"Skip missing {p_code}")
        continue
    data = IngestionParser(p_path).parse_all()
    micro = data.get("microbiology_reports", [])
    chunks = TemporalChunker(data).build_daily_chunks()
    p_cache_dir = os.path.join(model_dir, p_code)
    existing_files = os.listdir(p_cache_dir) if os.path.exists(p_cache_dir) else []
    
    daily_ext = []
    for c in chunks:
        d_clean = c['date'].replace('/', '-')
        day_num = c['day_number']
        exact_name = f"extraction_day_{day_num:02d}_{d_clean}.json"
        loaded = None
        if exact_name in existing_files:
            with open(os.path.join(p_cache_dir, exact_name), "r", encoding="utf-8") as f:
                loaded = json.load(f)
        else:
            match = [f for f in existing_files if f.endswith(f"_{d_clean}.json")]
            if match:
                with open(os.path.join(p_cache_dir, match[0]), "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    loaded['day_number'] = day_num
        if not loaded:
            loaded = {'patient_id': pid, 'date': c['date'], 'day_number': day_num, 'entities': {}}
        daily_ext.append(loaded)
        
    clf = ECDCClassifier(
        patient_id=pid,
        daily_extractions=daily_ext,
        parsed_microbiology=micro,
        admission_reports=data.get("admission_reports", [])
    )
    res = clf.classify()
    pred_orig = res['origine']
    print(f"Paziente: {pid} | Gold: {gold_val:7s} | Pred: {str(pred_orig):10s} | BSI: {res['bsi']} | CVC in sede: {res.get('details', {}).get('cvc_in_sede')}")

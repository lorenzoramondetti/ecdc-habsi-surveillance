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

model_dir = os.path.join(EXTRACTIONS_DIR, "Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest")

def classify_source_refined(clf, diagnostic_pathogen, diagnostic_day, blood_cultures, other_cultures, foci_by_day, catheters_by_day, admission_text):
    # 1. Catheter microbiologically confirmed
    dtp_cvc = any("cvc" in bc.get("tipo", "").lower() and bc.get("dtp") and any(k in str(bc["dtp"]).lower() for k in [">", "120", "2h", "2 h", "2 ore", "anticipo", "positivo"]) for bc in blood_cultures)
    tip_match = any(
        oc.get("sito") == "PUNTA_CATETERE" and oc.get("microrganismo") and diagnostic_pathogen and
        (clf._normalize_organism(diagnostic_pathogen) in clf._normalize_organism(oc["microrganismo"]) or
         clf._normalize_organism(oc["microrganismo"]) in clf._normalize_organism(diagnostic_pathogen))
        for oc in other_cultures
    )
    if dtp_cvc or tip_match:
        return "CRI3-CVC"

    # 2. Microbiological match in other cultures
    matching_foci = []
    for oc in other_cultures:
        oc_norm = clf._normalize_organism(oc.get("microrganismo"))
        diag_norm = clf._normalize_organism(diagnostic_pathogen)
        is_match = bool(oc_norm and diag_norm and (oc_norm in diag_norm or diag_norm in oc_norm))
        if is_match:
            sito = str(oc.get("sito", "")).upper()
            if "URIN" in sito or "UROCOLTURA" in sito: matching_foci.append("S-UTI")
            elif any(k in sito for k in ["POLM", "RESP", "BAL", "ESCREATO"]): matching_foci.append("S-PUL")
            elif any(k in sito for k in ["FERITA", "CHIRURG"]): matching_foci.append("S-SSI")
            elif any(k in sito for k in ["CUTE", "TESSUTI"]): matching_foci.append("S-SST")
            elif any(k in sito for k in ["DIGEST", "ADDOM", "PERITON"]): matching_foci.append("S-DIG")
    if matching_foci:
        return matching_foci[0]

    # Skin contaminants do NOT cause pneumonia/abdominal secondary BSI without micro match
    if clf._is_skin_contaminant(diagnostic_pathogen):
        has_catheter_pus = any(catheters_by_day.get(d, {}).get("segni_infezione_sito") for d in catheters_by_day)
        has_impr = any(catheters_by_day.get(d, {}).get("miglioramento_post_rimozione") for d in catheters_by_day)
        if has_catheter_pus or has_impr:
            return "C-CVC"
        return "UO"

    # 3. Clinical foci active near diagnostic day (+- 3 days)
    near_days = range(max(1, (diagnostic_day or 1) - 3), (diagnostic_day or 1) + 4)
    active_foci = []
    for d in near_days:
        f = foci_by_day.get(d, {})
        for site_key, site_label in [
            ("sito_chirurgico_S_SSI", "S-SSI"),
            ("cute_tessuti_molli_S_SST", "S-SST"),
            ("digestivo_addominale_S_DIG", "S-DIG"),
            ("urinario_S_UTI", "S-UTI"),
            ("polmonare_S_PUL", "S-PUL"),
        ]:
            if f.get(site_key, {}).get("sospetto_o_conferma"):
                active_foci.append(site_label)

    # Admission anamnesis clues
    adm_low = admission_text.lower()
    if "ostruzione urinaria" in adm_low or "catetere vescicale" in adm_low or "cistite" in adm_low or "pielonefrite" in adm_low:
        active_foci.append("S-UTI")
    if "k colecisti" in adm_low or "colangite" in adm_low or "ascessi epatici" in adm_low or "peritonite" in adm_low or "epatectomia" in adm_low:
        active_foci.append("S-DIG")
    if "fascite" in adm_low or "lrinec" in adm_low:
        active_foci.append("S-SST")

    diag_low = (diagnostic_pathogen or "").lower()
    if any(k in diag_low for k in ["pseudomonas", "aureus", "pyogenes"]) and "S-SST" in active_foci:
        return "S-SST"
    if any(k in diag_low for k in ["coli", "klebsiella", "enterobacter", "aeromonas", "candida"]):
        if "S-DIG" in active_foci and any(k in adm_low for k in ["colecist", "epatectom", "ascess", "addom"]):
            return "S-DIG"
        if "S-SSI" in active_foci:
            return "S-SSI"
        if "S-UTI" in active_foci:
            return "S-UTI"
    if "candida" in diag_low and "S-PUL" in active_foci:
        return "S-PUL"
    if active_foci:
        return active_foci[0]

    return "UO"

correct = 0
total = 0
for _, row in orig_df.iterrows():
    raw_id = str(row['clean_id']).strip()
    pid = raw_id.replace('Paziente_', '')
    gold_val = str(row["Origine dell'infezione"]).strip()
    p_code = f"Paziente_{pid}"
    p_path = os.path.join(DATA_DIR, p_code)
    if not os.path.exists(p_path): continue
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
        
    clf = ECDCClassifier(patient_id=pid, daily_extractions=daily_ext, parsed_microbiology=micro)
    res = clf.classify()
    pred = res.get('origine')
    
    # normalize S-PUL vs S-PULM
    match = (pred == gold_val) or (pred == "S-PUL" and gold_val == "S-PULM")
    total += 1
    if match: correct += 1
    print(f"Paziente: {pid:8s} | Gold: {gold_val:7s} | Pred: {str(pred):7s} | {'MATCH' if match else 'MISMATCH'}")

print(f"\nRefined Accuracy: {correct}/{total} = {correct/total*100:.1f}%")

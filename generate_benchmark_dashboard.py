import os
import json
import pandas as pd
from typing import Dict, List, Any

from pipeline.config import BASE_DIR, DATA_DIR, BENCHMARK_DIR, GOLD_STANDARD_PATH
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.ecdc_classifier import ECDCClassifier
from pipeline.benchmark import BenchmarkEvaluator

MODELS = [
    {
        "id": "gemma4_e4b",
        "name": "gemma4:e4b",
        "label": "Gemma 4 e4b (Miglior Modello 🏆)",
        "short_label": "Gemma 4 e4b 🏆",
        "folder": "Gemma4-e4b",
        "clean_ext": "gemma4_e4b",
        "timeline_file": "benchmark_timeline_gemma4_e4b.xlsx",
        "db_file": "benchmark_db_gemma4_e4b.xlsx"
    },
    {
        "id": "qwen_27b",
        "name": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
        "label": "Qwen 3.8 27B (Uncensored IQ4-XS)",
        "short_label": "Qwen 3.8 27B",
        "folder": "Qwen3.8-27B",
        "clean_ext": "Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest",
        "timeline_file": "benchmark_timeline_Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest.xlsx",
        "db_file": "benchmark_db_Bucoid_Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF_latest.xlsx"
    },
    {
        "id": "glm_flash",
        "name": "glm-4.7-flash:latest",
        "label": "GLM-4.7-Flash (Reasoning)",
        "short_label": "GLM-4.7-Flash",
        "folder": "GLM",
        "clean_ext": "glm-4.7-flash_latest",
        "timeline_file": "benchmark_timeline_glm-4.7-flash_latest.xlsx",
        "db_file": "benchmark_db_glm-4.7-flash_latest.xlsx"
    },
    {
        "id": "gemma4_12b",
        "name": "gemma4:12b",
        "label": "Gemma 4 12B (Standard)",
        "short_label": "Gemma 4 12B",
        "folder": "Gemma4-12b",
        "clean_ext": "gemma4_12b",
        "timeline_file": "benchmark_timeline_gemma4_12b.xlsx",
        "db_file": "benchmark_db_gemma4_12b.xlsx"
    }
]

def load_all_reports() -> Dict[str, Any]:
    evaluator = BenchmarkEvaluator()
    gold_df = evaluator.gold_df
    
    # Load 67 validated patients in exact order
    valid_df = gold_df[gold_df["BSI?"].notna() & (gold_df["BSI?"].astype(str).str.strip().isin(["SI", "NO", "si", "no"]))].copy()
    valid_ids = [c if c.startswith("Paziente_") else f"Paziente_{c}" for c in valid_df["clean_id"].tolist()]
    
    # Pre-parse microbiology, admission reports and daily chunks for all 67 patients
    patient_micro = {}
    patient_adm = {}
    patient_chunks = {}
    for pid in valid_ids:
        p_dir = os.path.join(DATA_DIR, pid)
        if os.path.exists(p_dir):
            parser = IngestionParser(p_dir)
            pdata = parser.parse_all()
            clean_pid = pid.replace("Paziente_", "")
            patient_micro[clean_pid] = pdata.get("microbiology_reports", [])
            patient_adm[clean_pid] = pdata.get("admission_reports", [])
            chunker = TemporalChunker(pdata)
            patient_chunks[clean_pid] = chunker.build_daily_chunks()
            
    models_data = {}
    
    for m in MODELS:
        ext_base = os.path.join("output", "extractions", m["clean_ext"])
        predictions = {}
        latencies = {}
        
        for pid_full in valid_ids:
            clean_pid = pid_full.replace("Paziente_", "")
            p_ext_dir = os.path.join(ext_base, pid_full)
            if not os.path.exists(p_ext_dir):
                continue
                
            existing_files = os.listdir(p_ext_dir)
            chunks = patient_chunks.get(clean_pid, [])
            daily = []
            tot_lat = 0.0
            
            for c in chunks:
                d_clean = c["date"].replace("/", "-")
                day_num = c["day_number"]
                exact_name = f"extraction_day_{day_num:02d}_{d_clean}.json"
                loaded = None
                if exact_name in existing_files:
                    try:
                        with open(os.path.join(p_ext_dir, exact_name), "r", encoding="utf-8") as jf:
                            loaded = json.load(jf)
                    except Exception:
                        pass
                else:
                    matches = [f for f in existing_files if f.endswith(f"_{d_clean}.json")]
                    if matches:
                        try:
                            with open(os.path.join(p_ext_dir, matches[0]), "r", encoding="utf-8") as jf:
                                loaded = json.load(jf)
                                loaded["day_number"] = day_num
                        except Exception:
                            pass
                if loaded:
                    daily.append(loaded)
                    tot_lat += loaded.get("latency_seconds", 0.0)
                        
            micro = patient_micro.get(clean_pid, [])
            adm_reps = patient_adm.get(clean_pid, [])
            clf = ECDCClassifier(patient_id=clean_pid, daily_extractions=daily, parsed_microbiology=micro, admission_reports=adm_reps)
            res = clf.classify()
            
            predictions[clean_pid] = res
            latencies[clean_pid] = tot_lat
            
        rep = evaluator.evaluate_model(model_name=m["label"], predictions=predictions, patient_latencies=latencies)
        
        models_data[m["id"]] = {
            "meta": m,
            "metrics": rep["metrics"],
            "time_analysis": rep["time_analysis"],
            "comparisons": rep["comparisons"]
        }
        
    return models_data

def build_interactive_html(models_data: Dict[str, Any]) -> str:
    models_json = json.dumps(models_data, ensure_ascii=False)
    
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ECDC Surveillance AI • Report Benchmark 67 Cartelle</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-dark: #0b1120;
      --card-bg: rgba(15, 23, 42, 0.75);
      --card-border: rgba(56, 189, 248, 0.15);
      --card-hover: rgba(56, 189, 248, 0.25);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --cyan-glow: #38bdf8;
      --emerald: #34d399;
      --rose: #fb7185;
      --amber: #fbbf24;
      --accent-grad: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      background: radial-gradient(circle at top right, #1e1b4b 0%, #0b1120 40%, #030712 100%);
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      min-height: 100vh;
      padding: 32px 24px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1400px;
      margin: 0 auto;
    }}
    /* HEADER */
    .top-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      flex-wrap: wrap;
      gap: 16px;
    }}
    .brand-title {{
      font-family: 'Outfit', sans-serif;
      font-size: 1.85rem;
      font-weight: 700;
      background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: -0.5px;
    }}
    .brand-subtitle {{
      color: var(--text-muted);
      font-size: 0.92rem;
      margin-top: 4px;
    }}
    .cohort-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.85rem;
      color: var(--cyan-glow);
      font-weight: 600;
    }}

    /* MODEL SELECTOR TABS */
    .tabs-bar {{
      display: flex;
      gap: 10px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
      padding: 12px 20px;
      border-radius: 10px;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 8px;
      backdrop-filter: blur(8px);
    }}
    .tab-btn:hover {{
      background: rgba(30, 41, 59, 0.8);
      border-color: rgba(56, 189, 248, 0.3);
      color: #fff;
    }}
    .tab-btn.active {{
      background: linear-gradient(135deg, rgba(14, 165, 233, 0.25) 0%, rgba(37, 99, 235, 0.25) 100%);
      border: 1px solid var(--cyan-glow);
      color: #fff;
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.2);
    }}

    /* BENCHMARK HERO CARD */
    .bench-hero {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px 28px;
      margin-bottom: 28px;
      backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }}
    .bench-hero-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .section-title {{
      font-family: 'Outfit', sans-serif;
      font-size: 1.45rem;
      font-weight: 700;
      color: #fff;
    }}
    .section-desc {{
      color: var(--text-muted);
      font-size: 0.88rem;
      margin-top: 4px;
    }}
    .action-links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .btn-action {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.82rem;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s;
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
    }}
    .btn-action:hover {{
      background: rgba(56, 189, 248, 0.15);
      border-color: var(--cyan-glow);
      color: #fff;
    }}

    /* 8 KPI CARDS GRID */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 12px;
    }}
    @media (max-width: 1024px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 640px) {{
      .kpi-grid {{ grid-template-columns: 1fr; }}
    }}
    .kpi-card {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s ease;
    }}
    .kpi-card:hover {{
      border-color: rgba(56, 189, 248, 0.3);
      transform: translateY(-2px);
    }}
    .kpi-label {{
      font-size: 0.76rem;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #94a3b8;
      margin-bottom: 8px;
    }}
    .kpi-value {{
      font-size: 1.85rem;
      font-weight: 800;
      color: #f8fafc;
      font-family: 'Outfit', sans-serif;
      line-height: 1.1;
      margin-bottom: 6px;
    }}
    .kpi-sub {{
      font-size: 0.82rem;
      color: #64748b;
    }}

    /* PATIENT DETAILS TABLE */
    .table-section {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }}
    .table-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .search-input {{
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 8px;
      padding: 8px 14px;
      color: #fff;
      font-size: 0.88rem;
      width: 280px;
    }}
    .search-input:focus {{
      outline: none;
      border-color: var(--cyan-glow);
    }}
    .filter-btn-group {{
      display: flex;
      gap: 8px;
    }}
    .filter-pill {{
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
    }}
    .filter-pill.active {{
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--cyan-glow);
      color: #fff;
    }}

    .table-wrapper {{
      overflow-x: auto;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.06);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.87rem;
    }}
    thead {{
      background: rgba(15, 23, 42, 0.95);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }}
    th {{
      padding: 12px 16px;
      font-weight: 600;
      color: #94a3b8;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    tbody tr {{
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      transition: background 0.15s;
    }}
    tbody tr:hover {{
      background: rgba(56, 189, 248, 0.04);
    }}
    td {{
      padding: 12px 16px;
      vertical-align: middle;
    }}
    .pid-cell {{
      font-weight: 700;
      color: #f8fafc;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
    }}
    .val-si {{
      color: var(--emerald);
      font-weight: 700;
    }}
    .val-no {{
      color: #94a3b8;
      font-weight: 500;
    }}
    .pathogen-text {{
      color: var(--cyan-glow);
      font-weight: 600;
    }}
    .time-badge {{
      background: rgba(56, 189, 248, 0.12);
      color: var(--cyan-glow);
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 8px;
      border-radius: 6px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      font-weight: 600;
      display: inline-block;
    }}
    .badge-concordant {{
      background: rgba(52, 211, 153, 0.15);
      border: 1px solid rgba(52, 211, 153, 0.35);
      color: var(--emerald);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.74rem;
      display: inline-block;
      letter-spacing: 0.5px;
    }}
    .badge-discordant {{
      background: rgba(251, 113, 133, 0.15);
      border: 1px solid rgba(251, 113, 133, 0.35);
      color: var(--rose);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.74rem;
      display: inline-block;
      letter-spacing: 0.5px;
    }}
    .summary-card-overview {{
      margin-top: 36px;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 24px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- TOP HEADER -->
    <header class="top-header">
      <div>
        <h1 class="brand-title">ECDC HA-BSI Surveillance AI • Benchmark Clinico</h1>
        <p class="brand-subtitle">Report interattivo multicartella validato su coorte clinica completa • Motore Deterministico + LLM Sovrano</p>
      </div>
      <div class="cohort-badge">
        <span>🛡️ Coorte Validata: 67 Pazienti (34 NO / 33 SI)</span>
      </div>
    </header>

    <!-- MODEL SELECTOR TABS -->
    <div class="tabs-bar" id="model-tabs">
      <!-- Injected dynamically -->
    </div>

    <!-- MAIN BENCHMARK CARD -->
    <div class="bench-hero">
      <div class="bench-hero-header">
        <div>
          <h2 class="section-title" id="bench-title">Risultati Benchmark Multicartella (67 Pazienti)</h2>
          <p class="section-desc" id="bench-subtitle">Metriche statistiche di accuratezza clinica, Kappa di Cohen e bilancio tempi su tutte le 67 cartelle</p>
        </div>
        <div class="action-links" id="action-links-container">
          <!-- Injected dynamically -->
        </div>
      </div>

      <!-- 8 KPI CARDS -->
      <div class="kpi-grid" id="kpi-container">
        <!-- Injected dynamically -->
      </div>
    </div>

    <!-- PATIENT DETAILS TABLE -->
    <div class="table-section">
      <div class="table-toolbar">
        <div>
          <h3 class="section-title" style="font-size:1.18rem;">Dettaglio dei 67 Pazienti Analizzati (Confronto vs Gold Standard Umano)</h3>
          <p class="section-desc">Classificazione caso per caso, patogeno isolato, tempi ed esito di concordanza</p>
        </div>
        <div style="display:flex;gap:12px;align-items:center;">
          <input type="text" id="patient-search" class="search-input" placeholder="🔍 Cerca paziente o patogeno..." oninput="filterTable()">
          <div class="filter-btn-group">
            <button class="filter-pill active" data-filter="ALL" onclick="setFilter('ALL', this)">Tutti (67)</button>
            <button class="filter-pill" data-filter="BSI_POS" onclick="setFilter('BSI_POS', this)">BSI Positivi (33)</button>
            <button class="filter-pill" data-filter="DISCORDANT" onclick="setFilter('DISCORDANT', this)">Discordanti</button>
          </div>
        </div>
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Cartella Paziente</th>
              <th>BSI (AI / Gold)</th>
              <th>HA-BSI (AI / Gold)</th>
              <th>Patogeno Diagnostico</th>
              <th>Origine / Luogo</th>
              <th>Tempo AI</th>
              <th>Esito Validazione</th>
            </tr>
          </thead>
          <tbody id="patients-table-body">
            <!-- Injected dynamically -->
          </tbody>
        </table>
      </div>
    </div>

    <!-- GLOBAL SUMMARY COMPARISON -->
    <div class="summary-card-overview">
      <h3 class="section-title" style="font-size:1.15rem;margin-bottom:12px;">📊 Confronto Prestazionale Globale tra Tutti i Modelli LLM Testati</h3>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Modello</th>
              <th>Accuratezza BSI</th>
              <th>Sensibilità BSI</th>
              <th>Specificità BSI</th>
              <th>Cohen Kappa (BSI)</th>
              <th>Accuratezza HA-BSI</th>
              <th>Acc. Origine</th>
              <th>Tempo Totale LLM</th>
              <th>Tempo Risparmiato</th>
            </tr>
          </thead>
          <tbody id="global-comparison-body">
            <!-- Injected dynamically -->
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const benchmarkData = {models_json};
    let currentModelKey = "gemma4_e4b";
    let activeFilter = "ALL";

    function init() {{
      renderTabs();
      loadModel(currentModelKey);
      renderGlobalComparison();
    }}

    function renderTabs() {{
      const tabsBar = document.getElementById("model-tabs");
      tabsBar.innerHTML = "";
      Object.keys(benchmarkData).forEach(key => {{
        const m = benchmarkData[key].meta;
        const btn = document.createElement("button");
        btn.className = `tab-btn ${{key === currentModelKey ? 'active' : ''}}`;
        btn.innerHTML = `<span>${{m.short_label}}</span>`;
        btn.onclick = () => {{
          currentModelKey = key;
          document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          loadModel(key);
        }};
        tabsBar.appendChild(btn);
      }});
    }}

    function loadModel(key) {{
      const d = benchmarkData[key];
      const meta = d.meta;
      const m = d.metrics;
      const t = d.time_analysis;

      document.getElementById("bench-title").textContent = `Risultati Benchmark Multicartella (67 Pazienti) • ${{meta.label}}`;
      
      // Download buttons
      const linksContainer = document.getElementById("action-links-container");
      linksContainer.innerHTML = `
        <a class="btn-action" href="${{meta.folder}}/${{meta.timeline_file}}" download>📥 Master Timeline Excel</a>
        <a class="btn-action" href="${{meta.folder}}/${{meta.db_file}}" download>📊 CRF DB 199 Col Excel</a>
        <a class="btn-action" href="benchmark_comparison_models.xlsx" download>📈 Report Metriche Comparativo</a>
      `;

      // 8 KPI Cards
      const kpiContainer = document.getElementById("kpi-container");
      kpiContainer.innerHTML = `
        <div class="kpi-card">
          <div class="kpi-label">Accuratezza BSI (IC 95%)</div>
          <div class="kpi-value">${{(m.accuracy * 100).toFixed(1)}}%</div>
          <div class="kpi-sub">${{(m.accuracy_ci95[0] * 100).toFixed(1)}}% - ${{(m.accuracy_ci95[1] * 100).toFixed(1)}}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Sensibilità BSI (IC 95%)</div>
          <div class="kpi-value">${{(m.sensitivity * 100).toFixed(1)}}%</div>
          <div class="kpi-sub">${{(m.sensitivity_ci95[0] * 100).toFixed(1)}}% - ${{(m.sensitivity_ci95[1] * 100).toFixed(1)}}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Specificità BSI (IC 95%)</div>
          <div class="kpi-value">${{(m.specificity * 100).toFixed(1)}}%</div>
          <div class="kpi-sub">${{(m.specificity_ci95[0] * 100).toFixed(1)}}% - ${{(m.specificity_ci95[1] * 100).toFixed(1)}}%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Kappa di Cohen (BSI)</div>
          <div class="kpi-value" style="color:var(--cyan-glow);">${{m.cohen_kappa_bsi.toFixed(3)}}</div>
          <div class="kpi-sub">Accordo Inter-Osservatore</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Accuratezza HA-BSI</div>
          <div class="kpi-value">${{(m.ha_bsi_accuracy * 100).toFixed(1)}}%</div>
          <div class="kpi-sub">Kappa HA: ${{m.cohen_kappa_ha_bsi.toFixed(3)}}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Accuratezza Origine</div>
          <div class="kpi-value">${{(m.origin_accuracy * 100).toFixed(1)}}%</div>
          <div class="kpi-sub">S-UTI, S-DIG, S-SST, CRI3, UO</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Tempo Umano vs LLM</div>
          <div class="kpi-value" style="font-size:1.45rem;">${{t.total_human_time_min}}m vs ${{t.total_llm_time_min}}m</div>
          <div class="kpi-sub">Media: ${{t.avg_llm_time_per_patient_sec}}s per cartella</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Tempo Totale Risparmiato</div>
          <div class="kpi-value" style="color:var(--emerald);">${{t.time_saved_percent}}%</div>
          <div class="kpi-sub">${{t.time_saved_min}} minuti risparmiati</div>
        </div>
      `;

      renderTable();
    }}

    function setFilter(f, btn) {{
      activeFilter = f;
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      renderTable();
    }}

    function filterTable() {{
      renderTable();
    }}

    function renderTable() {{
      const d = benchmarkData[currentModelKey];
      const comps = d.comparisons || [];
      const tbody = document.getElementById("patients-table-body");
      const search = (document.getElementById("patient-search").value || "").toLowerCase().trim();

      tbody.innerHTML = "";

      comps.forEach(c => {{
        const isConcordantBsi = (c.BSI_Status === "TP" || c.BSI_Status === "TN");
        const isConcordantHa = (c.HA_Status === "TP" || c.HA_Status === "TN" || c.HA_Status === "-");
        const overallConcordant = isConcordantBsi && (c.Gold_BSI === "NO" || isConcordantHa);

        // Filter checks
        if (activeFilter === "BSI_POS" && c.Gold_BSI !== "SI") return;
        if (activeFilter === "DISCORDANT" && overallConcordant) return;

        // Search check
        if (search) {{
          const pMatch = c.Paziente.toLowerCase().includes(search);
          const pathMatch = (c.Patogeno || "").toLowerCase().includes(search);
          if (!pMatch && !pathMatch) return;
        }}

        const tr = document.createElement("tr");
        const badge = overallConcordant 
          ? `<span class="badge-concordant">CONCORDANTE</span>` 
          : `<span class="badge-discordant">DISCORDANTE</span>`;

        const bsiSpan = `<span class="${{c.Pred_BSI === 'SI' ? 'val-si' : 'val-no'}}">${{c.Pred_BSI}}</span> / <strong>${{c.Gold_BSI}}</strong>`;
        const haSpan = `<span class="${{c.Pred_HA_BSI === 'SI' ? 'val-si' : 'val-no'}}">${{c.Pred_HA_BSI || '-'}}</span> / <strong>${{c.Gold_HA_BSI || '-'}}</strong>`;
        const pathSpan = c.Patogeno && c.Patogeno !== '-' 
          ? `<span class="pathogen-text">${{c.Patogeno}}</span>` 
          : `<span style="color:#64748b;">Nessuno</span>`;
        const origText = `${{c.Pred_Origine || '-'}} / ${{c.Pred_Luogo || '-'}}`;

        tr.innerHTML = `
          <td class="pid-cell">${{c.Paziente}}</td>
          <td>${{bsiSpan}}</td>
          <td>${{haSpan}}</td>
          <td>${{pathSpan}}</td>
          <td style="font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:#cbd5e1;">${{origText}}</td>
          <td><span class="time-badge">${{c.Tempo_LLM_Sec}}s</span></td>
          <td>${{badge}}</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function renderGlobalComparison() {{
      const tbody = document.getElementById("global-comparison-body");
      tbody.innerHTML = "";
      Object.keys(benchmarkData).forEach(k => {{
        const d = benchmarkData[k];
        const m = d.metrics;
        const t = d.time_analysis;
        const meta = d.meta;

        const isWinner = k === "gemma4_e4b";
        const tr = document.createElement("tr");
        if (isWinner) tr.style.background = "rgba(56, 189, 248, 0.08)";

        tr.innerHTML = `
          <td style="font-weight:700;color:${{isWinner ? '#38bdf8' : '#fff'}};">${{meta.label}}</td>
          <td><strong>${{(m.accuracy * 100).toFixed(1)}}%</strong> <span style="font-size:0.75rem;color:#64748b;">(${{(m.accuracy_ci95[0]*100).toFixed(1)}}-${{(m.accuracy_ci95[1]*100).toFixed(1)}}%)</span></td>
          <td>${{(m.sensitivity * 100).toFixed(1)}}%</td>
          <td>${{(m.specificity * 100).toFixed(1)}}%</td>
          <td><strong style="color:#38bdf8;">${{m.cohen_kappa_bsi.toFixed(3)}}</strong></td>
          <td>${{(m.ha_bsi_accuracy * 100).toFixed(1)}}% <span style="font-size:0.75rem;color:#64748b;">(κ: ${{m.cohen_kappa_ha_bsi.toFixed(3)}})</span></td>
          <td>${{(m.origin_accuracy * 100).toFixed(1)}}%</td>
          <td><span class="time-badge">${{t.total_llm_time_min.toFixed(1)}} min</span></td>
          <td><strong style="color:var(--emerald);">${{t.time_saved_percent}}%</strong></td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    window.onload = init;
  </script>
</body>
</html>
"""
    return html

def main():
    print("[*] Generazione dati benchmark completi per tutti i modelli...")
    models_data = load_all_reports()
    
    # Save JSON
    json_path = os.path.join(BENCHMARK_DIR, "benchmark_data_all_models.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(models_data, f, indent=2, ensure_ascii=False)
    print(f"[V] JSON salvato in: {json_path}")
    
    # Save Interactive HTML
    html_content = build_interactive_html(models_data)
    html_path = os.path.join(BENCHMARK_DIR, "report_benchmark_interattivo.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[V] Report HTML interattivo salvato in: {html_path}")

if __name__ == "__main__":
    main()

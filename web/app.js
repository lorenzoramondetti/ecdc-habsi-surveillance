// ECDC HA-BSI Surveillance & Benchmark Platform Frontend Logic
let appState = {
  currentTab: "single",
  patients: [],
  models: [],
  selectedBenchModels: [],
  benchPollingTimer: null,
  discrepancyData: [],
  activeFilter: "all"
};

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

async function initApp() {
  setupTimelineFilter();
  await loadConfig();
  await loadModels();
  await loadPatients();
  await loadHistoricalBenchmarkSummary();
}

// -------------------------------------------------------------
// NAVIGATION TABS
// -------------------------------------------------------------
function switchTab(tabId) {
  appState.currentTab = tabId;
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  const targetBtn = document.getElementById(`tab-${tabId}-btn`);
  const targetContent = document.getElementById(`tab-${tabId}-content`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetContent) targetContent.classList.add("active");
}

// -------------------------------------------------------------
// FOLDER CONFIGURATION & MANAGEMENT
// -------------------------------------------------------------
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    const select = document.getElementById("folder-select");
    select.innerHTML = "";

    if (data.available_dirs && data.available_dirs.length > 0) {
      data.available_dirs.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.path;
        opt.textContent = `${d.name} (${d.path})`;
        if (d.is_active) opt.selected = true;
        select.appendChild(opt);
      });
    } else {
      const opt = document.createElement("option");
      opt.value = data.current_data_dir;
      opt.textContent = data.current_data_dir;
      opt.selected = true;
      select.appendChild(opt);
    }
  } catch (err) {
    console.error("Errore nel caricamento configurazione:", err);
  }
}

async function onFolderSelected() {
  const select = document.getElementById("folder-select");
  const chosenPath = select.value;
  if (!chosenPath) return;

  try {
    const res = await fetch("/api/config/data_dir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_dir: chosenPath })
    });
    if (res.ok) {
      await loadPatients();
    }
  } catch (err) {
    alert(`Errore cambio cartella: ${err.message}`);
  }
}

function toggleCustomFolder() {
  const input = document.getElementById("custom-folder-input");
  const btnApply = document.getElementById("btn-apply-custom");
  const select = document.getElementById("folder-select");
  const isHidden = input.style.display === "none";

  input.style.display = isHidden ? "inline-block" : "none";
  btnApply.style.display = isHidden ? "inline-block" : "none";
  select.style.display = isHidden ? "none" : "inline-block";
}

async function applyCustomFolder() {
  const input = document.getElementById("custom-folder-input");
  const customPath = input.value.trim();
  if (!customPath) {
    alert("Inserisci un percorso cartella valido.");
    return;
  }

  try {
    const res = await fetch("/api/config/data_dir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_dir: customPath })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Cartella non valida");

    await loadConfig();
    await loadPatients();
    toggleCustomFolder();
  } catch (err) {
    alert(`Errore: ${err.message}`);
  }
}

// -------------------------------------------------------------
// PATIENTS & MODELS LOADERS
// -------------------------------------------------------------
async function loadPatients() {
  const select = document.getElementById("patient-select");
  const countBadge = document.getElementById("patient-count-val");
  const benchTotalSpan = document.getElementById("bench-total-patients-num");

  try {
    const res = await fetch("/api/patients");
    const data = await res.json();
    appState.patients = data.patients || [];
    select.innerHTML = "";

    if (countBadge) countBadge.textContent = appState.patients.length;
    if (benchTotalSpan) benchTotalSpan.textContent = appState.patients.length;

    if (appState.patients.length > 0) {
      appState.patients.forEach((p, idx) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        const goldHint = p.gold_bsi !== "-" ? `[Gold: BSI ${p.gold_bsi}${p.gold_ha_bsi !== '-' ? ', HA ' + p.gold_ha_bsi : ''}]` : "[Non etichettato]";
        opt.textContent = `${p.folder_name} ${goldHint}`;
        if (idx === 0) opt.selected = true;
        select.appendChild(opt);
      });
      populateCustomPatientsPicker(appState.patients);
    } else {
      select.innerHTML = "<option value=''>Nessuna cartella trovata</option>";
    }
  } catch (err) {
    console.error("Errore caricamento pazienti:", err);
    select.innerHTML = "<option value=''>Errore caricamento cartelle</option>";
  }
}

function populateCustomPatientsPicker(patients) {
  const container = document.getElementById("custom-patients-picker");
  if (!container) return;
  container.innerHTML = "";

  patients.forEach(p => {
    const lbl = document.createElement("label");
    lbl.className = "checkbox-label";
    lbl.style.marginBottom = "4px";
    lbl.innerHTML = `
      <input type="checkbox" name="custom-pz-chk" value="${p.id}" checked>
      <span>${p.folder_name}</span>
    `;
    container.appendChild(lbl);
  });
}

async function loadModels() {
  const select = document.getElementById("model-select");
  const checkboxList = document.getElementById("models-checkbox-list");
  const statusBadge = document.getElementById("system-status-badge");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");

  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    appState.models = data.models || [];
    select.innerHTML = "";
    if (checkboxList) checkboxList.innerHTML = "";

    if (data.ollama_active) {
      statusDot.className = "status-indicator online";
      statusText.textContent = `Ollama Engine Online (${appState.models.length} modelli rilevati)`;
    } else {
      statusDot.className = "status-indicator offline";
      statusText.textContent = "Ollama Non Connesso (usare modelli predefiniti)";
    }

    if (appState.models.length > 0) {
      appState.models.forEach((m, idx) => {
        // Dropdown option
        const opt = document.createElement("option");
        opt.value = m;
        let displayName = formatModelName(m);
        if (m === data.default) displayName += " (Default Primario)";
        opt.textContent = displayName;
        if (m === data.default) opt.selected = true;
        select.appendChild(opt);

        // Benchmark Checkbox row
        if (checkboxList) {
          const row = document.createElement("label");
          row.className = "model-item-row";
          const isChecked = idx < 4; // Select first 4 by default
          row.innerHTML = `
            <input type="checkbox" name="bench-model" value="${m}" ${isChecked ? 'checked' : ''}>
            <span>${formatModelName(m)}</span>
            <span class="model-chip">${getModelSizeTag(m)}</span>
          `;
          checkboxList.appendChild(row);
        }
      });
    } else {
      select.innerHTML = "<option value=''>Nessun modello trovato</option>";
    }
  } catch (err) {
    console.error("Errore caricamento modelli:", err);
  }
}

function formatModelName(m) {
  return m.replace("hf.co/Bucoid/", "").replace(":latest", "").replace("hf.co/", "");
}

function getModelSizeTag(m) {
  const lower = m.toLowerCase();
  if (lower.includes("27b")) return "16GB+ VRAM";
  if (lower.includes("12b")) return "8GB-12GB VRAM";
  if (lower.includes("e4b") || lower.includes("flash") || lower.includes("7b") || lower.includes("4b")) return "Leggero (<8GB)";
  return "Standard";
}

function selectAllModels(checkAll) {
  document.querySelectorAll("input[name='bench-model']").forEach(chk => {
    chk.checked = checkAll;
  });
}

function updateBenchScope() {
  const val = document.querySelector("input[name='bench-patient-scope']:checked").value;
  const customDiv = document.getElementById("custom-patients-picker");
  if (customDiv) {
    customDiv.style.display = (val === "custom") ? "block" : "none";
  }
}

// -------------------------------------------------------------
// TAB 1: SINGLE PATIENT SURVEILLANCE
// -------------------------------------------------------------
async function runAnalysis() {
  const patientId = document.getElementById("patient-select").value;
  const modelName = document.getElementById("model-select").value;
  const force = document.getElementById("chk-force-single").checked;

  if (!patientId) {
    alert("Seleziona una cartella paziente prima di procedere.");
    return;
  }

  const loadingOverlay = document.getElementById("loading-overlay");
  const resultsContainer = document.getElementById("results-container");
  const btnRun = document.getElementById("btn-run");

  loadingOverlay.classList.remove("hidden");
  resultsContainer.classList.add("hidden");
  btnRun.disabled = true;

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_id: patientId, model_name: modelName, force: force })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Errore durante l'elaborazione");

    renderResults(data);
    resultsContainer.classList.remove("hidden");
  } catch (err) {
    alert(`Errore nell'esecuzione: ${err.message}`);
  } finally {
    loadingOverlay.classList.add("hidden");
    btnRun.disabled = false;
  }
}

function renderResults(data) {
  const cls = data.classification || {};
  const gold = data.gold_standard || {};
  const time = data.time_analysis || {};

  // 1. Metric Cards
  const valBsi = document.getElementById("val-bsi");
  const subBsi = document.getElementById("sub-bsi");
  const cardBsi = document.getElementById("card-bsi");

  valBsi.textContent = cls.bsi || "--";
  subBsi.textContent = `Patogeno: ${cls.diagnostic_pathogen || "Nessuno"}`;
  cardBsi.className = `metric-card ${cls.bsi === "SI" ? "danger" : "safe"}`;

  const valHabsi = document.getElementById("val-habsi");
  const subHabsi = document.getElementById("sub-habsi");
  const cardHabsi = document.getElementById("card-habsi");

  valHabsi.textContent = cls.ha_bsi || "--";
  subHabsi.textContent = `Origine: ${cls.origine || "NONE"} • Luogo: ${cls.luogo_acquisizione || "NONE"}`;
  cardHabsi.className = `metric-card ${cls.ha_bsi === "SI" ? "danger" : (cls.bsi === "SI" ? "warning" : "safe")}`;

  const valOrigin = document.getElementById("val-origin");
  const subOrigin = document.getElementById("sub-origin");
  valOrigin.textContent = cls.origine || "NONE";
  subOrigin.textContent = `Luogo ECDC: ${cls.luogo_acquisizione || "NONE"}`;

  const valTimeSaved = document.getElementById("val-time-saved");
  const subTimeSaved = document.getElementById("sub-time-saved");
  valTimeSaved.textContent = `${time.time_saved_percent || 0}%`;
  subTimeSaved.textContent = `Umano: ${time.human_time_min}m | LLM: ${time.llm_time_sec}s (${time.time_saved_min}m risparmiati)`;

  // 2. Audit Trail
  const auditList = document.getElementById("audit-trail-list");
  auditList.innerHTML = "";
  if (cls.audit_trail && cls.audit_trail.length > 0) {
    cls.audit_trail.forEach(step => {
      const item = document.createElement("div");
      item.className = "audit-item";
      let icon = "🔹";
      if (step.includes("CONFERMATA")) icon = "🚨";
      else if (step.includes("COMMUNITY")) icon = "🏘️";
      else if (step.includes("NEGATIVA")) icon = "✅";
      item.innerHTML = `<strong>${icon}</strong> <span>${step}</span>`;
      auditList.appendChild(item);
    });
  }

  // Gold Agreement Badge
  const goldBadge = document.getElementById("gold-agreement-badge");
  if (gold.bsi) {
    const isBsiMatch = (gold.bsi === cls.bsi);
    const isHaMatch = (gold.ha_bsi === cls.ha_bsi);
    if (isBsiMatch && isHaMatch) {
      goldBadge.className = "agreement-badge match";
      goldBadge.textContent = `Confronto Gold: Accordo Perfetto (BSI: ${gold.bsi}, HA: ${gold.ha_bsi})`;
    } else {
      goldBadge.className = "agreement-badge mismatch";
      goldBadge.textContent = `Confronto Gold: Discrepanza (Gold: BSI ${gold.bsi}, HA ${gold.ha_bsi} vs LLM: BSI ${cls.bsi}, HA ${cls.ha_bsi})`;
    }
  } else {
    goldBadge.className = "agreement-badge";
    goldBadge.textContent = "Confronto Gold: Nessuna etichetta presente";
  }

  // 3. Downloads
  if (data.downloads) {
    const dlTimeline = document.getElementById("btn-dl-timeline");
    const dlDb = document.getElementById("btn-dl-db");
    const dlTessy = document.getElementById("btn-dl-tessy");

    if (dlTimeline) dlTimeline.href = data.downloads.timeline_xlsx;
    if (dlDb) dlDb.href = data.downloads.db_xlsx;
    if (dlTessy) dlTessy.href = data.downloads.tessy_csv;
  }

  // 4. Timeline
  renderTimeline(data.timeline || []);
}

function renderTimeline(rows) {
  const container = document.getElementById("timeline-container");
  container.innerHTML = "";

  if (!rows || rows.length === 0) {
    container.innerHTML = "<p style='color:var(--text-muted);'>Nessun dato temporale estratto per questo paziente.</p>";
    return;
  }

  rows.forEach(r => {
    const item = document.createElement("div");
    item.className = "timeline-day-card";
    item.dataset.hasFever = r.ha_febbre === "SI" ? "true" : "false";
    item.dataset.hasCvc = r.ha_cvc === "SI" ? "true" : "false";
    item.dataset.hasAbx = (r.antibiotici && r.antibiotici !== "-") ? "true" : "false";
    item.dataset.hasMicro = (r.microbiologia && r.microbiologia !== "-") ? "true" : "false";

    item.innerHTML = `
      <div class="day-badge">Day ${String(r.giorno).padStart(2, '0')} • ${r.data}</div>
      <div class="day-content">
        <div class="day-params-grid">
          <div class="param-box">
            <span class="param-name">Febbre:</span>
            <span class="val-badge ${r.ha_febbre === 'SI' ? 'badge-danger' : ''}">${r.ha_febbre}</span>
          </div>
          <div class="param-box">
            <span class="param-name">CVC/Dispositivi:</span>
            <span class="val-badge ${r.ha_cvc === 'SI' ? 'badge-warning' : ''}">${r.ha_cvc}</span>
          </div>
          <div class="param-box">
            <span class="param-name">Antibiotici:</span>
            <span class="val-badge">${r.antibiotici}</span>
          </div>
          <div class="param-box">
            <span class="param-name">Microbiologia:</span>
            <span class="val-badge ${r.microbiologia !== '-' ? 'badge-accent' : ''}">${r.microbiologia}</span>
          </div>
        </div>
        ${r.citazione ? `<div class="verbatim-quote">"${r.citazione}"</div>` : ''}
      </div>
    `;
    container.appendChild(item);
  });
}

function setupTimelineFilter() {
  document.querySelectorAll(".timeline-filter .filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".timeline-filter .filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const f = btn.dataset.filter;

      document.querySelectorAll(".timeline-day-card").forEach(card => {
        if (f === "all") card.style.display = "flex";
        else if (f === "fever") card.style.display = card.dataset.hasFever === "true" ? "flex" : "none";
        else if (f === "cvc") card.style.display = card.dataset.hasCvc === "true" ? "flex" : "none";
        else if (f === "abx") card.style.display = card.dataset.hasAbx === "true" ? "flex" : "none";
        else if (f === "micro") card.style.display = card.dataset.hasMicro === "true" ? "flex" : "none";
      });
    });
  });
}

// -------------------------------------------------------------
// TAB 2: MULTI-MODEL BENCHMARK
// -------------------------------------------------------------
async function startMultiModelBenchmark() {
  const checkedBoxes = Array.from(document.querySelectorAll("input[name='bench-model']:checked"));
  const selectedModels = checkedBoxes.map(c => c.value);

  if (selectedModels.length === 0) {
    alert("Seleziona almeno un modello LLM per eseguire il benchmark.");
    return;
  }

  const scope = document.querySelector("input[name='bench-patient-scope']:checked").value;
  let patientTarget = "all";

  if (scope === "first5") {
    patientTarget = appState.patients.slice(0, 5).map(p => p.id);
  } else if (scope === "custom") {
    const checkedPz = Array.from(document.querySelectorAll("input[name='custom-pz-chk']:checked"));
    patientTarget = checkedPz.map(c => c.value);
    if (patientTarget.length === 0) {
      alert("Seleziona almeno una cartella clinica dall'elenco specifico.");
      return;
    }
  }

  const force = document.getElementById("chk-bench-force").checked;

  try {
    const res = await fetch("/api/benchmark/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        models: selectedModels,
        patients: patientTarget,
        force: force
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Impossibile avviare benchmark");

    // UI setup
    document.getElementById("benchmark-progress-section").classList.remove("hidden");
    document.getElementById("btn-start-bench").classList.add("hidden");
    document.getElementById("btn-stop-bench").classList.remove("hidden");

    // Start polling
    startBenchStatusPolling();
  } catch (err) {
    alert(`Errore avvio benchmark: ${err.message}`);
  }
}

function startBenchStatusPolling() {
  if (appState.benchPollingTimer) clearInterval(appState.benchPollingTimer);

  appState.benchPollingTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/benchmark/status");
      const state = await res.json();

      updateBenchProgressUI(state);

      if (state.status === "completed" || state.status === "error" || state.status === "cancelled") {
        clearInterval(appState.benchPollingTimer);
        document.getElementById("btn-start-bench").classList.remove("hidden");
        document.getElementById("btn-stop-bench").classList.add("hidden");

        if (state.status === "completed") {
          alert("Benchmark completato con successo!");
          await loadHistoricalBenchmarkSummary();
          switchTab("reports");
        } else if (state.status === "error") {
          alert(`Errore durante il benchmark: ${state.error_message}`);
        }
      }
    } catch (err) {
      console.error("Errore polling stato benchmark:", err);
    }
  }, 1000);
}

function updateBenchProgressUI(s) {
  const fill = document.getElementById("bench-bar-fill");
  const pct = document.getElementById("bench-pct-badge");
  const curModel = document.getElementById("bench-cur-model");
  const curPz = document.getElementById("bench-cur-patient");
  const curStep = document.getElementById("bench-cur-step");
  const curElapsed = document.getElementById("bench-cur-elapsed");

  if (fill) fill.style.width = `${s.progress}%`;
  if (pct) pct.textContent = `${s.progress}%`;
  if (curModel) curModel.textContent = formatModelName(s.current_model || "--");
  if (curPz) curPz.textContent = s.current_patient ? `Paziente_${s.current_patient}` : "--";
  if (curStep) curStep.textContent = `${s.patient_index} / ${s.total_patients} (Modello ${s.model_index}/${s.total_models})`;
  if (curElapsed) curElapsed.textContent = `${s.elapsed_seconds}s`;

  // Log box
  const logBox = document.getElementById("live-log-box");
  if (logBox && s.logs && s.logs.length > 0) {
    logBox.innerHTML = s.logs.map(l => `<div class="live-log-line">${l}</div>`).join("");
    logBox.scrollTop = logBox.scrollHeight;
  }
}

async function stopBenchmark() {
  if (!confirm("Sei sicuro di voler interrompere la sessione di benchmark in corso?")) return;
  try {
    await fetch("/api/benchmark/stop", { method: "POST" });
  } catch (err) {
    console.error("Errore arresto benchmark:", err);
  }
}

function clearLiveLog() {
  const box = document.getElementById("live-log-box");
  if (box) box.innerHTML = "";
}

// -------------------------------------------------------------
// TAB 3: BENCHMARK SUMMARY & DISCREPANCY VIEWER
// -------------------------------------------------------------
async function loadHistoricalBenchmarkSummary() {
  try {
    // Fetch precomputed data
    const res = await fetch("/benchmark/benchmark_data_all_models.json");
    if (!res.ok) return;
    const allData = await res.json();

    const tbody = document.getElementById("bench-metrics-tbody");
    if (tbody) tbody.innerHTML = "";

    appState.discrepancyData = [];

    Object.keys(allData).forEach((k, idx) => {
      const m = allData[k];
      const meta = m.meta || {};
      const met = m.metrics || {};
      const time = m.time_analysis || {};

      if (tbody) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${meta.label || k}</strong></td>
          <td>${(met.accuracy_bsi * 100).toFixed(1)}%</td>
          <td>${(met.sensitivity_bsi * 100).toFixed(1)}%</td>
          <td>${(met.specificity_bsi * 100).toFixed(1)}%</td>
          <td>${met.f1_bsi.toFixed(3)}</td>
          <td><span class="badge ${met.cohen_kappa_bsi >= 0.8 ? 'badge-safe' : 'badge-accent'}">${met.cohen_kappa_bsi.toFixed(3)} (${met.kappa_interpretation_bsi})</span></td>
          <td>${(time.total_llm_time_minutes || 0).toFixed(1)}m</td>
          <td><span class="badge badge-safe">+${(time.time_saved_percent || 0).toFixed(1)}%</span></td>
        `;
        tbody.appendChild(tr);
      }

      // Populate discrepancies for the first model (e.g. Qwen)
      if (idx === 0 && m.comparisons) {
        appState.discrepancyData = m.comparisons;
        renderDiscrepancyTable(appState.discrepancyData, "all");
      }
    });
  } catch (err) {
    console.error("Errore caricamento storico benchmark:", err);
  }
}

function renderDiscrepancyTable(items, filter) {
  const tbody = document.getElementById("discrepancy-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const filtered = items.filter(c => {
    if (filter === "all") return true;
    if (filter === "fp") return c.status_bsi === "FP" || c.status_ha === "FP";
    if (filter === "fn") return c.status_bsi === "FN" || c.status_ha === "FN";
    if (filter === "match") return (c.status_bsi === "TP" || c.status_bsi === "TN") && (c.status_ha !== "FP" && c.status_ha !== "FN");
    return true;
  });

  filtered.forEach(c => {
    const tr = document.createElement("tr");
    const stClass = (c.status_bsi || "").toLowerCase();
    tr.innerHTML = `
      <td><strong>${c.patient_id}</strong></td>
      <td>${c.gold_bsi}</td>
      <td>${c.pred_bsi}</td>
      <td><span class="status-badge ${stClass}">${c.status_bsi}</span></td>
      <td>${c.gold_ha || "-"}</td>
      <td>${c.pred_ha || "-"}</td>
      <td>${c.pathogen || "-"}</td>
      <td>${c.gold_origin || "-"}</td>
      <td>${c.pred_origin || "-"}</td>
      <td>${c.llm_time_s ? c.llm_time_s + 's' : '-'}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filterDiscrepancies(type) {
  document.querySelectorAll(".filter-pill-group .pill-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");
  renderDiscrepancyTable(appState.discrepancyData, type);
}

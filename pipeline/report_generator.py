import os
import json
from typing import Dict, Any, List
from pipeline.config import REPORTS_DIR

class ReportGenerator:
    """Generates human-readable, highly explainable clinical surveillance reports."""

    def __init__(self, output_dir: str = REPORTS_DIR):
        self.output_dir = output_dir

    def generate_patient_report(self, patient_id: str, classification_res: Dict[str, Any], daily_extractions: List[Dict[str, Any]], gold_standard_info: Dict[str, Any] = None) -> str:
        report_lines = []
        report_lines.append(f"# Scheda di Sorveglianza e Validazione BSI - Paziente_{patient_id}\n")
        report_lines.append(f"**Data Generazione Report**: {classification_res.get('timestamp', 'N/A')}")
        report_lines.append(f"**Paziente ID**: Paziente_{patient_id}")
        report_lines.append(f"**Protocollo di Riferimento**: ECDC PPS v6.1 (Bloodstream Infections Surveillance)\n")

        report_lines.append("## 1. Sintesi Esito di Classificazione Algoritmica")
        report_lines.append("| Criterio ECDC | Esito Predetto | Gold Standard Umano | Concordanza |")
        report_lines.append("| :--- | :--- | :--- | :--- |")

        pred_bsi = classification_res.get("bsi", "NO")
        pred_ha = classification_res.get("ha_bsi", "NO")
        pred_orig = classification_res.get("origine") or "-"
        pred_luogo = classification_res.get("luogo_acquisizione") or "-"

        gold_bsi = gold_standard_info.get("BSI?", "-") if gold_standard_info else "-"
        gold_ha = gold_standard_info.get("HA BSI?", "-") if gold_standard_info else "-"
        gold_orig = gold_standard_info.get("Origine dell'infezione", "-") if gold_standard_info else "-"
        gold_luogo = gold_standard_info.get("Luogo acquisizione", "-") if gold_standard_info else "-"

        match_bsi = "CORRETTO" if str(pred_bsi).upper() == str(gold_bsi).upper() else ("N/D" if gold_bsi == "-" else "DISCORDANTE")
        match_ha = "CORRETTO" if str(pred_ha).upper() == str(gold_ha).upper() else ("N/D" if gold_ha in ["-", "NAN"] else "DISCORDANTE")
        match_orig = "CORRETTO" if str(pred_orig).upper() == str(gold_orig).upper() else ("N/D" if gold_orig in ["-", "NAN"] else "DISCORDANTE")
        match_luogo = "CORRETTO" if str(pred_luogo).upper() == str(gold_luogo).upper() else ("N/D" if gold_luogo in ["-", "NAN"] else "DISCORDANTE")

        report_lines.append(f"| **BSI (Batteriemia)** | **{pred_bsi}** | {gold_bsi} | {match_bsi} |")
        report_lines.append(f"| **HA-BSI (Correlata all'Assistenza)** | **{pred_ha}** | {gold_ha} | {match_ha} |")
        report_lines.append(f"| **Origine dell'Infezione** | **{pred_orig}** | {gold_orig} | {match_orig} |")
        report_lines.append(f"| **Luogo di Acquisizione** | **{pred_luogo}** | {gold_luogo} | {match_luogo} |\n")

        report_lines.append("## 2. Tracciabilità e Spiegazione Deterministica (Audit Trail)")
        report_lines.append("La decisione finale è stata generata in modo deterministico applicando le regole dell'ECDC sulle evidenze estratte:\n")
        for step in classification_res.get("audit_trail", []):
            report_lines.append(f"- {step}")

        report_lines.append("\n## 3. Cronistoria Clinica e Parametri Rilevati per Data")
        report_lines.append("| Data | Degenza | Febbre / Segni Vitali | Dispositivi | Isolati Microbiologici | Focolai Secondari Sospetti |")
        report_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

        for d in sorted(daily_extractions, key=lambda x: x.get("day_number", 1)):
            d_date = d.get("date", "")
            d_num = f"Day {d.get('day_number', 1)}"
            ent = d.get("entities", {})

            # Vital signs summary
            s = ent.get("segni_vitali_sintomi", {})
            vitals = []
            if s.get("febbre", {}).get("presente"):
                vitals.append(f"Febbre ({s['febbre'].get('valore_max', '>38°C')})")
            if s.get("brividi", {}).get("presente"):
                vitals.append("Brividi")
            if s.get("ipotensione", {}).get("presente"):
                vitals.append("Ipotensione")
            vitals_str = ", ".join(vitals) if vitals else "Stabile/Apiretico"

            # Devices summary
            dev = ent.get("dispositivi_invasivi", {})
            dev_list = []
            if dev.get("cvc_presente"):
                dev_list.append("CVC in sede")
            if dev.get("cvc_inserito_oggi"):
                dev_list.append("CVC inserito")
            if dev.get("cvc_rimosso_oggi"):
                dev_list.append("CVC rimosso")
            dev_str = ", ".join(dev_list) if dev_list else "Nessun CVC"

            # Micro summary
            micro = ent.get("microbiologia_rilevata", {})
            micro_list = []
            for bc in micro.get("emocolture", []):
                if bc.get("esito_positivo"):
                    micro_list.append(f"Emocoltura: {bc.get('microrganismo')}")
            for oc in micro.get("altre_colture", []):
                if oc.get("esito_positivo"):
                    micro_list.append(f"{oc.get('sito')}: {oc.get('microrganismo')}")
            micro_str = ", ".join(micro_list) if micro_list else "-"

            # Foci summary
            foci = ent.get("focolai_secondari_infezione", {})
            foci_list = [k.replace("sospetto_", "").replace("_", " ") for k, v in foci.items() if isinstance(v, dict) and v.get("sospetto_o_conferma")]
            foci_str = ", ".join(foci_list) if foci_list else "-"

            report_lines.append(f"| {d_date} | {d_num} | {vitals_str} | {dev_str} | {micro_str} | {foci_str} |")

        report_lines.append("\n---\n*Report generato automaticamente dal sistema di sorveglianza ECDC BSI*\n")

        full_md = "\n".join(report_lines)
        report_path = os.path.join(self.output_dir, f"report_explainability_Paziente_{patient_id}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_md)

        return report_path

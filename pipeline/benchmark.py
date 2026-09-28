import os
import math
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from pipeline.config import GOLD_STANDARD_PATH, BENCHMARK_DIR, DEFAULT_HUMAN_TIME_MINUTES

def compute_wilson_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculates Wilson score interval for binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    z = 1.96 if confidence == 0.95 else 1.645
    p_hat = k / n
    denominator = 1 + (z**2) / n
    center = (p_hat + (z**2) / (2 * n)) / denominator
    spread = (z / denominator) * math.sqrt((p_hat * (1 - p_hat) / n) + ((z**2) / (4 * (n**2))))
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (round(lower, 4), round(upper, 4))

def compute_cohen_kappa(tp: int, tn: int, fp: int, fn: int) -> float:
    """Calculates Cohen's Kappa for 2x2 contingency table."""
    total = tp + tn + fp + fn
    if total <= 0:
        return 0.0
    po = (tp + tn) / total
    pe = (((tp + fp) * (tp + fn)) + ((tn + fp) * (tn + fn))) / (total ** 2)
    if pe >= 1.0:
        return 1.0
    kappa = (po - pe) / (1.0 - pe)
    return round(kappa, 4)

class BenchmarkEvaluator:
    """Evaluates automated pipeline predictions against the human gold standard,
    including Cohen's Kappa, diagnostic metrics with 95% CI, and human vs LLM time savings.
    """

    def __init__(self, gold_standard_path: str = GOLD_STANDARD_PATH):
        self.gold_standard_path = gold_standard_path
        self.gold_df = self._load_gold_standard()
        self.time_column = self._detect_human_time_column()

    def _load_gold_standard(self) -> pd.DataFrame:
        df = pd.read_excel(self.gold_standard_path, "Suddivisione Cartelle")
        df["clean_id"] = df["Codice cartella cartella "].astype(str).str.strip()
        return df

    def _detect_human_time_column(self) -> Optional[str]:
        """Detects if the user has added a manual human review time column in the Excel file."""
        for col in self.gold_df.columns:
            c_low = str(col).lower()
            if any(k in c_low for k in ["tempo", "minut", "durata", "time"]):
                return col
        return None

    def get_human_time_minutes(self, patient_id: str) -> float:
        """Returns the human review time in minutes for a given patient from the gold standard Excel."""
        clean_id = patient_id if str(patient_id).startswith("Paziente_") else f"Paziente_{patient_id}"
        if self.time_column and self.time_column in self.gold_df.columns:
            row = self.gold_df[self.gold_df["clean_id"] == clean_id]
            if not row.empty:
                val = row.iloc[0].get(self.time_column)
                if pd.notna(val):
                    import datetime
                    # Excel parses mm:ss (e.g. 08:27) as datetime.time(hour=8, minute=27)
                    if isinstance(val, datetime.time):
                        return round(val.hour + val.minute / 60.0 + val.second / 3600.0, 2)
                    if isinstance(val, (int, float)) and float(val) > 0:
                        return round(float(val), 2)
                    s = str(val).strip()
                    if ":" in s:
                        parts = s.split(":")
                        if len(parts) == 2:
                            return round(float(parts[0]) + float(parts[1]) / 60.0, 2)
                        elif len(parts) == 3:
                            return round(float(parts[0]) * 60.0 + float(parts[1]) + float(parts[2]) / 60.0, 2)
                    try:
                        f = float(s)
                        if f > 0:
                            return round(f, 2)
                    except Exception:
                        pass
        return DEFAULT_HUMAN_TIME_MINUTES

    def evaluate_model(
        self,
        model_name: str,
        predictions: Dict[str, Dict[str, Any]],
        patient_latencies: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Compares model predictions with human gold standard and evaluates time savings."""
        comparison_rows = []

        tp, fp, tn, fn = 0, 0, 0, 0
        ha_tp, ha_fp, ha_tn, ha_fn = 0, 0, 0, 0
        orig_matches, orig_total = 0, 0
        setting_matches, setting_total = 0, 0

        total_human_time_min = 0.0
        total_llm_time_sec = 0.0

        for patient_id, pred in predictions.items():
            full_pid = patient_id if str(patient_id).startswith("Paziente_") else f"Paziente_{patient_id}"
            gold_row = self.gold_df[self.gold_df["clean_id"] == full_pid]

            if gold_row.empty:
                continue

            gold_item = gold_row.iloc[0]
            gold_bsi = str(gold_item.get("BSI?", "")).strip().upper()
            gold_ha = str(gold_item.get("HA BSI?", "")).strip().upper()
            gold_orig = str(gold_item.get("Origine dell'infezione", "")).strip().upper()
            gold_setting = str(gold_item.get("Luogo acquisizione", "")).strip().upper()

            pred_bsi = str(pred.get("bsi", "")).strip().upper()
            pred_ha = str(pred.get("ha_bsi", "")).strip().upper()
            pred_orig = str(pred.get("origine", "")).strip().upper()
            pred_setting = str(pred.get("luogo_acquisizione", "")).strip().upper()

            # Time tracking
            h_time = self.get_human_time_minutes(patient_id)
            total_human_time_min += h_time

            llm_time = (patient_latencies or {}).get(patient_id, 0.0)
            total_llm_time_sec += llm_time

            # BSI evaluation
            if gold_bsi == "SI":
                if pred_bsi == "SI":
                    tp += 1
                    bsi_match = "TP"
                else:
                    fn += 1
                    bsi_match = "FN"
            elif gold_bsi == "NO":
                if pred_bsi == "SI":
                    fp += 1
                    bsi_match = "FP"
                else:
                    tn += 1
                    bsi_match = "TN"
            else:
                bsi_match = "-"

            # HA-BSI evaluation
            ha_match = "-"
            if gold_bsi == "SI":
                if gold_ha == "SI":
                    if pred_ha == "SI":
                        ha_tp += 1
                        ha_match = "TP"
                    else:
                        ha_fn += 1
                        ha_match = "FN"
                elif gold_ha == "NO":
                    if pred_ha == "SI":
                        ha_fp += 1
                        ha_match = "FP"
                    else:
                        ha_tn += 1
                        ha_match = "TN"

            # Origin evaluation
            orig_match = "-"
            if gold_orig and gold_orig not in ["NAN", "", "NONE"]:
                orig_total += 1
                is_orig_match = (pred_orig == gold_orig) or (pred_orig in ["S-PUL", "S-PULM"] and gold_orig in ["S-PUL", "S-PULM"])
                if is_orig_match:
                    orig_matches += 1
                    orig_match = "MATCH"
                else:
                    orig_match = "MISMATCH"

            # Setting evaluation
            setting_match = "-"
            if gold_setting and gold_setting not in ["NAN", "", "NONE"]:
                setting_total += 1
                if pred_setting == gold_setting:
                    setting_matches += 1
                    setting_match = "MATCH"
                else:
                    setting_match = "MISMATCH"

            comparison_rows.append({
                "Paziente": full_pid,
                "Gold_BSI": gold_bsi,
                "Pred_BSI": pred_bsi,
                "BSI_Status": bsi_match,
                "Gold_HA_BSI": gold_ha,
                "Pred_HA_BSI": pred_ha,
                "HA_Status": ha_match,
                "Patogeno": pred.get("diagnostic_pathogen") or "-",
                "Data_Diagnostica": pred.get("diagnostic_date") or "-",
                "Gold_Origine": gold_orig,
                "Pred_Origine": pred_orig,
                "Origine_Status": orig_match,
                "Gold_Luogo": gold_setting,
                "Pred_Luogo": pred_setting,
                "Luogo_Status": setting_match,
                "Tempo_Umano_Min": h_time,
                "Tempo_LLM_Sec": round(llm_time, 1)
            })

        # Calculate metrics & 95% CIs
        n_bsi = tp + tn + fp + fn
        acc = (tp + tn) / n_bsi if n_bsi > 0 else 0.0
        acc_ci = compute_wilson_ci(tp + tn, n_bsi)

        sens = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        sens_ci = compute_wilson_ci(tp, tp + fn)

        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        spec_ci = compute_wilson_ci(tn, tn + fp)

        ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        ppv_ci = compute_wilson_ci(tp, tp + fp)

        npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0
        npv_ci = compute_wilson_ci(tn, tn + fn)

        f1 = (2 * ppv * sens) / (ppv + sens) if (ppv + sens) > 0 else 0.0
        kappa_bsi = compute_cohen_kappa(tp, tn, fp, fn)

        n_ha = ha_tp + ha_tn + ha_fp + ha_fn
        ha_acc = (ha_tp + ha_tn) / n_ha if n_ha > 0 else 0.0
        ha_kappa = compute_cohen_kappa(ha_tp, ha_tn, ha_fp, ha_fn)

        orig_acc = orig_matches / orig_total if orig_total > 0 else 0.0
        setting_acc = setting_matches / setting_total if setting_total > 0 else 0.0

        # Time savings
        total_llm_time_min = total_llm_time_sec / 60.0
        time_saved_min = max(0.0, total_human_time_min - total_llm_time_min)
        time_saved_pct = (time_saved_min / total_human_time_min * 100.0) if total_human_time_min > 0 else 0.0

        report = {
            "model_name": model_name,
            "metrics": {
                "n_patients": len(comparison_rows),
                "accuracy": round(acc, 4),
                "accuracy_ci95": acc_ci,
                "sensitivity": round(sens, 4),
                "sensitivity_ci95": sens_ci,
                "specificity": round(spec, 4),
                "specificity_ci95": spec_ci,
                "ppv": round(ppv, 4),
                "ppv_ci95": ppv_ci,
                "npv": round(npv, 4),
                "npv_ci95": npv_ci,
                "f1_score": round(f1, 4),
                "cohen_kappa_bsi": kappa_bsi,
                "ha_bsi_accuracy": round(ha_acc, 4),
                "cohen_kappa_ha_bsi": ha_kappa,
                "origin_accuracy": round(orig_acc, 4),
                "setting_accuracy": round(setting_acc, 4),
                "tp": tp, "tn": tn, "fp": fp, "fn": fn
            },
            "time_analysis": {
                "total_human_time_min": round(total_human_time_min, 1),
                "total_human_time_hours": round(total_human_time_min / 60.0, 2),
                "total_llm_time_min": round(total_llm_time_min, 2),
                "total_llm_time_sec": round(total_llm_time_sec, 1),
                "avg_llm_time_per_patient_sec": round(total_llm_time_sec / len(comparison_rows), 1) if comparison_rows else 0.0,
                "time_saved_min": round(time_saved_min, 1),
                "time_saved_hours": round(time_saved_min / 60.0, 2),
                "time_saved_percent": round(time_saved_pct, 1)
            },
            "comparisons": comparison_rows
        }
        return report

    def save_benchmark_report(self, model_reports: List[Dict[str, Any]]) -> str:
        """Saves a multi-model benchmark report to Excel and Markdown."""
        summary_rows = []
        for rep in model_reports:
            m = rep["metrics"]
            t = rep["time_analysis"]
            summary_rows.append({
                "Modello": rep["model_name"],
                "Accuratezza BSI": f"{m['accuracy'] * 100:.1f}% ({m['accuracy_ci95'][0]*100:.1f}-{m['accuracy_ci95'][1]*100:.1f}%)",
                "Sensibilità BSI": f"{m['sensitivity'] * 100:.1f}% ({m['sensitivity_ci95'][0]*100:.1f}-{m['sensitivity_ci95'][1]*100:.1f}%)",
                "Specificità BSI": f"{m['specificity'] * 100:.1f}% ({m['specificity_ci95'][0]*100:.1f}-{m['specificity_ci95'][1]*100:.1f}%)",
                "PPV": f"{m['ppv'] * 100:.1f}%",
                "NPV": f"{m['npv'] * 100:.1f}%",
                "F1-Score": f"{m['f1_score']:.3f}",
                "Kappa Cohen BSI": f"{m['cohen_kappa_bsi']:.3f}",
                "Accuratezza HA-BSI": f"{m['ha_bsi_accuracy'] * 100:.1f}%",
                "Kappa Cohen HA-BSI": f"{m['cohen_kappa_ha_bsi']:.3f}",
                "Accuratezza Origine": f"{m['origin_accuracy'] * 100:.1f}%",
                "Accuratezza Setting": f"{m['setting_accuracy'] * 100:.1f}%",
                "Tempo Umano Totale (min)": t["total_human_time_min"],
                "Tempo LLM Totale (min)": t["total_llm_time_min"],
                "Tempo Risparmiato (%)": f"{t['time_saved_percent']:.1f}%"
            })

        summary_df = pd.DataFrame(summary_rows)
        xlsx_path = os.path.join(BENCHMARK_DIR, "benchmark_comparison_models.xlsx")
        summary_df.to_excel(xlsx_path, index=False)

        def _df_to_markdown(df: pd.DataFrame) -> str:
            try:
                return df.to_markdown(index=False)
            except Exception:
                headers = list(df.columns)
                lines = [
                    "| " + " | ".join(str(h) for h in headers) + " |",
                    "| " + " | ".join(["---"] * len(headers)) + " |"
                ]
                for _, row in df.iterrows():
                    lines.append("| " + " | ".join(str(val).replace("\n", " ") for val in row) + " |")
                return "\n".join(lines)

        md_path = os.path.join(BENCHMARK_DIR, "benchmark_comparison_models.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Report Sorveglianza ECDC BSI: Performance & Analisi Efficienza\n\n")
            f.write(_df_to_markdown(summary_df))
            f.write("\n\n## Dettaglio Paziente per Paziente\n")
            for rep in model_reports:
                f.write(f"\n### Modello: {rep['model_name']}\n")
                f.write(f"- **Tempo Umano**: {rep['time_analysis']['total_human_time_min']} min | **Tempo LLM**: {rep['time_analysis']['total_llm_time_sec']} sec\n")
                f.write(f"- **Tempo Risparmiato**: {rep['time_analysis']['time_saved_min']} min ({rep['time_analysis']['time_saved_percent']}%)\n\n")
                det_df = pd.DataFrame(rep["comparisons"])
                f.write(_df_to_markdown(det_df))
                f.write("\n")

        return xlsx_path

import os
import csv
from typing import Dict, Any, List
from pipeline.config import TESSY_DIR

class TESSyExporter:
    """Exports clinical surveillance results into standard ECDC PPS (TESSy) format.
    Conforms to European Centre for Disease Prevention and Control (ECDC) HAI surveillance standards.
    """

    def __init__(self, export_dir: str = TESSY_DIR):
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

    def export_to_csv(self, predictions: Dict[str, Dict[str, Any]], filename: str = "ecdc_pps_bsi_surveillance.csv") -> str:
        filepath = os.path.join(self.export_dir, filename)
        
        headers = [
            "SURVTYPE",
            "PATIENT_ID",
            "BSI_DETECTED",
            "HA_BSI",
            "BSI_ORIGIN",
            "ACQUISITION_SITE",
            "DIAGNOSTIC_PATHOGEN",
            "ECDC_CRITERIA_MET",
            "TOTAL_DAILY_CHUNKS",
            "AUDIT_TRAIL_SUMMARY"
        ]

        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(headers)

            for pid, res in predictions.items():
                bsi = "Y" if str(res.get("bsi", "")).strip().upper() == "SI" else "N"
                ha_bsi = "Y" if str(res.get("ha_bsi", "")).strip().upper() == "SI" else ("N" if bsi == "Y" else "NA")
                origin = res.get("origine", "NONE")
                site = res.get("luogo_acquisizione", "NONE")
                pathogen = res.get("diagnostic_pathogen") or "None"
                crit = " | ".join(res.get("ecdc_criteria", [])) if res.get("ecdc_criteria") else "None"
                audit = " // ".join(res.get("audit_trail", []))

                writer.writerow([
                    "ECDC_PPS_BSI",
                    pid,
                    bsi,
                    ha_bsi,
                    origin,
                    site,
                    pathogen,
                    crit,
                    res.get("processed_chunks_count", 0),
                    audit
                ])

        return filepath

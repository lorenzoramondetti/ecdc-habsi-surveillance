import os
import re
import sys
from typing import Dict, List, Any, Optional
import pymupdf
import pandas as pd

class IngestionParser:
    """Parses heterogeneous medical records (PDFs and CSVs) for a given patient."""

    def __init__(self, patient_dir: str):
        self.patient_dir = patient_dir
        self.patient_id = os.path.basename(patient_dir).replace("Paziente_", "")

    def parse_all(self) -> Dict[str, Any]:
        """Parses all available clinical folders for the patient."""
        results = {
            "patient_id": self.patient_id,
            "patient_dir": self.patient_dir,
            "admission_reports": self.parse_admission_reports(),
            "clinical_diaries": self.parse_clinical_diaries(),
            "microbiology_reports": self.parse_microbiology(),
            "laboratory_data": self.parse_laboratory_data(),
            "id_consultations": self.parse_id_consultations(),
        }
        return results

    def _find_folder(self, prefix: str) -> Optional[str]:
        for item in os.listdir(self.patient_dir):
            item_path = os.path.join(self.patient_dir, item)
            if os.path.isdir(item_path) and item.startswith(prefix):
                return item_path
        return None

    def parse_admission_reports(self) -> List[Dict[str, Any]]:
        folder = self._find_folder("ADMISSION_EMERGENCY_REPORTS")
        if not folder:
            return []

        reports = []
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".pdf"):
                fpath = os.path.join(folder, fname)
                doc = pymupdf.open(fpath)
                pages_text = [page.get_text("text", sort=True) for page in doc]
                full_text = "\n".join(pages_text)
                
                # Extract birth dates to explicitly exclude them from admission dates
                birth_dates = set(re.findall(r"Nato(?:/a)?\s+(?:il:?|a)[\s\S]{0,40}?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE))
                
                # Extract historical procedure dates (e.g. vascular access inserted months/years prior)
                hist_dates = set(re.findall(r"(?:Data Inserimento|Inserimento CVC|Inserimento Port|Accessi vascolari)[\s\S]{0,40}?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE))

                # Identify explicit triage and emergency room admission dates
                admission_dates = []
                # Pattern 1: Dates explicitly preceding 'Codice Triage' or following 'Val.Triage' / 'Accesso DEA'
                ct_dates = re.findall(r"(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}(?::\d{2})?\s*-\s*Codice Triage", full_text, re.IGNORECASE)
                for d in ct_dates:
                    if d not in birth_dates and d not in hist_dates:
                        admission_dates.append(d)
                
                triage_matches = re.findall(
                    r"(?:Val\.Triage|Triage|Accesso in DEA|Codice Triage Ingresso|Accede in DEA|Verbale di Pronto Soccorso|Data Accettazione|Data Ricovero|Ricovero del)[\s\S]{0,100}?(\d{1,2}/\d{1,2}/\d{4})",
                    full_text,
                    re.IGNORECASE
                )
                for d in triage_matches:
                    if d not in birth_dates and d not in hist_dates:
                        admission_dates.append(d)

                # All generic dates and times
                dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", full_text)
                times = re.findall(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", full_text)
                
                reports.append({
                    "filename": fname,
                    "pages": len(doc),
                    "text": full_text,
                    "admission_dates": admission_dates,
                    "birth_dates": list(birth_dates),
                    "detected_dates": dates,
                    "detected_times": times
                })
        return reports

    def parse_clinical_diaries(self) -> List[Dict[str, Any]]:
        folder = self._find_folder("CLINICAL_DIARIES")
        if not folder:
            return []

        diaries = []
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".pdf"):
                fpath = os.path.join(folder, fname)
                doc = pymupdf.open(fpath)
                
                for page_num, page in enumerate(doc):
                    text = page.get_text("text", sort=True)
                    dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
                    giornate = re.findall(r"\b(\d+)°?\s*giornata\b", text, re.IGNORECASE)
                    times = re.findall(r"\b(\d{1,2}:\d{2}:\d{2})\b", text)
                    ricovero_match = re.findall(r"Ricovero del\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
                    
                    diaries.append({
                        "filename": fname,
                        "page_number": page_num + 1,
                        "text": text,
                        "dates": dates,
                        "giornate": giornate,
                        "times": times,
                        "ricovero_dates": ricovero_match
                    })
        return diaries

    def parse_microbiology(self) -> List[Dict[str, Any]]:
        folder = self._find_folder("MICROBIOLOGY")
        if not folder:
            return []

        reports = []
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".pdf"):
                fpath = os.path.join(folder, fname)
                doc = pymupdf.open(fpath)
                full_text = "\n".join([p.get_text("text", sort=True) for p in doc])
                
                # Detect birth date in header to protect against fallback collision
                m_birth = re.search(r"Nato(?:/a)?\s+(?:il:?|a)[\s\S]{0,40}?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE)
                birth_date = m_birth.group(1) if m_birth else None

                # Extract Validato da date
                validato_date = None
                m_validato = re.search(r"Validato da[\s\S]{0,100}?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE)
                if m_validato:
                    validato_date = m_validato.group(1)

                # Extract Prelievo del date
                prelievo_date = None
                # First check direct inline match
                m_prelievo = re.search(r"Prelievo del\s*(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE)
                if m_prelievo and m_prelievo.group(1) != birth_date:
                    prelievo_date = m_prelievo.group(1)
                else:
                    # Multi-line match near Prelievo del (handling columnar blocks or overlapping anonymization)
                    m_prelievo_near = re.findall(r"Prelievo del[\s\S]{0,60}?(\d{1,2}/\d{1,2}/\d{4})", full_text, re.IGNORECASE)
                    candidates = [d for d in m_prelievo_near if d != birth_date]
                    if candidates:
                        # If multiple candidates (e.g. anonymized overlapping text '08/01/199908/01/2000'),
                        # pick the one whose year matches validato_date or is closest
                        if validato_date:
                            v_year = validato_date.split("/")[-1]
                            matched_year = [d for d in candidates if d.endswith(v_year)]
                            prelievo_date = matched_year[-1] if matched_year else candidates[-1]
                        else:
                            prelievo_date = candidates[-1]

                if not prelievo_date:
                    # Fallback: find all dates excluding birth date and validato date
                    all_dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", full_text)
                    valid_candidates = [d for d in all_dates if d != birth_date and d != validato_date]
                    if valid_candidates:
                        prelievo_date = valid_candidates[0]
                    elif validato_date:
                        prelievo_date = validato_date

                # Identify specimen type
                specimen = "UNKNOWN"
                t_low = full_text.lower()
                if "emocoltura" in t_low:
                    if "c.v.c" in t_low or "cvc" in t_low:
                        specimen = "EMOCOLTURA_CVC"
                    else:
                        specimen = "EMOCOLTURA_PERIFERICA"
                elif "urocoltura" in t_low:
                    specimen = "UROCOLTURA"
                elif "liquido cerebrospinale" in t_low or "csf" in t_low or "liquor" in t_low:
                    specimen = "LIQUOR"
                elif "aspirato tracheale" in t_low or "broncoaspirato" in t_low or "bal" in t_low:
                    specimen = "RESPIRATORIO"
                elif "ferita" in t_low:
                    specimen = "FERITA"
                elif "catetere" in t_low or "punta" in t_low:
                    specimen = "PUNTA_CATETERE"

                # Check positivity
                is_positive = False
                if "positivo" in t_low or "positiva" in t_low:
                    is_positive = True
                elif "sviluppo" in t_low and "nessuno sviluppo" not in t_low:
                    is_positive = True

                # Extract isolates
                isolates = []
                isol_matches = re.findall(r"Isolato \d+:\s*([^\n\r]+)", full_text, re.IGNORECASE)
                for im in isol_matches:
                    clean_name = im.strip()
                    if clean_name and clean_name.lower() not in ["", "nessuno"]:
                        isolates.append(clean_name)

                # Check CFU / colony counts
                cfu = None
                m_cfu = re.search(r"(?:carica microbica|carica batterica)?:?\s*([\d\.,\s]+(?:U\.F\.C\./ml|CFU/ml))", full_text, re.IGNORECASE)
                if m_cfu:
                    cfu = m_cfu.group(1).strip()

                # Check DTP (differential time to positivity)
                dtp = None
                m_dtp = re.search(r"DELTA TIME TO POSITIVITY:?\s*([^\n\r]+)", full_text, re.IGNORECASE)
                if m_dtp:
                    dtp = m_dtp.group(1).strip()

                reports.append({
                    "filename": fname,
                    "specimen": specimen,
                    "prelievo_date": prelievo_date,
                    "validato_date": validato_date,
                    "is_positive": is_positive,
                    "isolates": isolates,
                    "cfu": cfu,
                    "dtp": dtp,
                    "full_text": full_text
                })
        return reports

    def parse_laboratory_data(self) -> Dict[str, Any]:
        folder = self._find_folder("LABORATORY_DATA")
        if not folder:
            return {}

        parsed_csvs = []
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".csv"):
                fpath = os.path.join(folder, fname)
                try:
                    df = pd.read_csv(fpath, sep=";", encoding="utf-8-sig", header=None)
                    
                    # Find the header row containing datetimes
                    header_row_idx = None
                    for idx, row in df.iterrows():
                        row_str = " ".join([str(v) for v in row.values])
                        if re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", row_str):
                            header_row_idx = idx
                            break

                    if header_row_idx is not None:
                        header_row = df.iloc[header_row_idx]
                        data_df = df.iloc[header_row_idx + 1:].copy()
                        data_df.columns = header_row

                        parsed_csvs.append({
                            "filename": fname,
                            "dates": [str(c) for c in header_row if re.search(r"\d{1,2}/\d{1,2}/\d{4}", str(c))],
                            "raw_shape": df.shape,
                            "filepath": fpath
                        })
                except Exception as e:
                    parsed_csvs.append({
                        "filename": fname,
                        "error": str(e),
                        "filepath": fpath
                    })
        return {"files": parsed_csvs}

    def parse_id_consultations(self) -> List[Dict[str, Any]]:
        folder = self._find_folder("INFECTIOUS_DISEASE_CONSULTATIONS")
        if not folder:
            return []

        consults = []
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(".pdf"):
                fpath = os.path.join(folder, fname)
                doc = pymupdf.open(fpath)
                full_text = "\n".join([p.get_text() for p in doc])
                dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", full_text)
                consults.append({
                    "filename": fname,
                    "dates": dates,
                    "full_text": full_text
                })
        return consults

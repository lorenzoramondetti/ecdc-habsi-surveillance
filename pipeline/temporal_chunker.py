import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class TemporalChunker:
    """Chunks patient clinical information by calendar date and hospitalization day."""

    def __init__(self, parsed_patient_data: Dict[str, Any]):
        self.data = parsed_patient_data
        self.patient_id = parsed_patient_data["patient_id"]

    def _parse_date(self, d_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(d_str.strip(), "%d/%m/%Y")
        except Exception:
            return None

    def determine_admission_date(self) -> Optional[str]:
        """Finds the true hospital admission / triage date, filtering out historical/birth dates."""
        ricovero_dts = []
        diary_dts = []
        for diary in self.data.get("clinical_diaries", []):
            for d in diary.get("ricovero_dates", []):
                dt = self._parse_date(d)
                if dt:
                    ricovero_dts.append(dt)
            for d in diary.get("dates", []):
                dt = self._parse_date(d)
                if dt:
                    diary_dts.append(dt)

        micro_dts = []
        for m in self.data.get("microbiology_reports", []):
            if m.get("prelievo_date"):
                dt = self._parse_date(m["prelievo_date"])
                if dt:
                    micro_dts.append(dt)

        # Primary anchor: explicit 'Ricovero del' from clinical diaries
        reference_dt = None
        if ricovero_dts:
            reference_dt = min(ricovero_dts)
        elif diary_dts:
            reference_dt = min(diary_dts)
        elif micro_dts:
            reference_dt = min(micro_dts)

        # 1. Check explicit admission / triage dates from admission reports
        explicit_adm_dates = []
        for rep in self.data.get("admission_reports", []):
            for d in rep.get("admission_dates", []):
                dt = self._parse_date(d)
                if dt:
                    # If we have a reference date, triage candidate cannot be > 14 days prior
                    if reference_dt is None or (dt <= reference_dt and (reference_dt - dt).days <= 14) or (dt >= reference_dt and (dt - reference_dt).days <= 2):
                        explicit_adm_dates.append(dt)

        if explicit_adm_dates:
            # Pick earliest candidate (e.g. DEA triage date that led to ward admission)
            return min(explicit_adm_dates).strftime("%d/%m/%Y")

        if reference_dt:
            return reference_dt.strftime("%d/%m/%Y")

        # 2. Fallback: earliest detected date across all documents
        all_raw_dates = []
        for rep in self.data.get("admission_reports", []):
            for d in rep.get("detected_dates", []):
                dt = self._parse_date(d)
                if dt:
                    all_raw_dates.append(dt)
        if all_raw_dates:
            return min(all_raw_dates).strftime("%d/%m/%Y")
        return None

    def _prune_text(self, text: str, max_chars: int = 2500) -> str:
        """Prunes administrative boilerplate and form padding from clinical reports."""
        clean = re.sub(r"\n\s*\n+", "\n", text)
        clean = re.sub(r"[_\.]{4,}", "", clean)
        clean = re.sub(r"Sede Legale[\s\S]*?Verbale di Pronto Soccorso", "Verbale di Pronto Soccorso", clean, flags=re.IGNORECASE)
        clean = re.sub(r"Documento firmato digitalmente[\s\S]*?norma di legge", "", clean, flags=re.IGNORECASE)
        if len(clean) > max_chars:
            clean = clean[:max_chars] + "\n[... Estratto sezioni cliniche primarie ...]"
        return clean.strip()

    def build_daily_chunks(self) -> List[Dict[str, Any]]:
        admission_date_str = self.determine_admission_date() or "01/01/2000"
        admission_dt = self._parse_date(admission_date_str) or datetime(2000, 1, 1)

        daily_diary_text: Dict[str, List[str]] = {}
        current_dt = admission_dt

        for diary in self.data.get("clinical_diaries", []):
            text = diary.get("text", "")
            page_num = diary.get("page_number", 1)
            
            # Clean text by removing administrative intercalare headers and signatures
            body_clean = re.sub(r"INTERCALARE C[\s\S]*?cf\.", "", text, flags=re.IGNORECASE)
            body_clean = re.sub(r"Documento firmato digitalmente[\s\S]*?norma di legge.*", "", body_clean, flags=re.IGNORECASE)
            body_clean = re.sub(r"Stampa[\s\S]*?norma di legge.*", "", body_clean, flags=re.IGNORECASE)

            # Check for explicit "X° giornata" in cleaned body
            giornate_match = re.findall(r"(\d+)\s*°\s*giornata", body_clean, flags=re.IGNORECASE)
            page_matched_dt = None

            # Look for explicit dates in the body of the clinical note first
            body_dates = re.findall(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", body_clean)
            valid_body_dates = [self._parse_date(d) for d in body_dates if self._parse_date(d)]
            # Filter out ancient dates (e.g. birth dates > 30 days before admission)
            valid_encounter_dates = [d for d in valid_body_dates if (d - admission_dt).days >= 0]

            if giornate_match:
                try:
                    g_num = int(giornate_match[0])
                    # Clinical standard: 1° giornata = admission_dt (Day 1), 2° giornata = admission_dt + 1 day (Day 2)
                    page_matched_dt = admission_dt + timedelta(days=max(0, g_num - 1))
                except Exception:
                    pass
            elif "Val.Triage" in body_clean or "Triage" in body_clean:
                page_matched_dt = admission_dt
            elif valid_encounter_dates:
                # Pick earliest valid encounter date on page that is >= current_dt, or min valid date
                meaningful_dates = [d for d in valid_encounter_dates if d >= current_dt]
                page_matched_dt = min(meaningful_dates) if meaningful_dates else min(valid_encounter_dates)

            if page_matched_dt:
                current_dt = page_matched_dt

            d_str = current_dt.strftime("%d/%m/%Y")
            if d_str not in daily_diary_text:
                daily_diary_text[d_str] = []

            # Clean and add page text
            clean_page = self._prune_text(text, max_chars=1800)
            daily_diary_text[d_str].append(f"--- NOTE DIARIO CLINICO (Pagina {page_num}) ---\n{clean_page}")

        # Also collect all known dates across admissions and microbiology
        all_dates_set = set(daily_diary_text.keys())
        all_dates_set.add(admission_date_str)

        for m in self.data.get("microbiology_reports", []):
            if m.get("prelievo_date"):
                m_dt = self._parse_date(m["prelievo_date"])
                if m_dt:
                    # Filter out pre-admission anomalies (e.g. birth date mis-extractions > 30 days before)
                    if (m_dt - admission_dt).days >= -1:
                        all_dates_set.add(m["prelievo_date"])

        sorted_dates = sorted(
            [d for d in all_dates_set if self._parse_date(d)],
            key=lambda x: self._parse_date(x)
        )

        chunks = []
        for d_str in sorted_dates:
            d_dt = self._parse_date(d_str)
            if admission_dt and d_dt:
                # Strictly enforce non-negative day numbers (day >= 1)
                day_num = max(1, (d_dt - admission_dt).days + 1)
            else:
                day_num = 1

            chunk_text_parts = []
            chunk_text_parts.append(f"=== PAZIENTE: {self.patient_id} | DATA: {d_str} | GIORNO DI RICOVERO: Giorno {day_num} ===")

            # 1. HEAD-FIRST INJECTION: Microbiology reports (CRITICAL: Protected from truncation)
            day_micro = [
                m for m in self.data.get("microbiology_reports", [])
                if m.get("prelievo_date") == d_str
            ]
            if day_micro:
                chunk_text_parts.append("\n--- ESAMI MICROBIOLOGICI PRELEVATI IN QUESTA DATA ---")
                for m in day_micro:
                    status = "POSITIVO" if m.get("is_positive") else "NEGATIVO"
                    isol = ", ".join(m.get("isolates", [])) if m.get("isolates") else "Nessuno sviluppo"
                    cfu_str = f" (Carica: {m['cfu']})" if m.get("cfu") else ""
                    dtp_str = f" (DTP: {m['dtp']})" if m.get("dtp") else ""
                    chunk_text_parts.append(f"[{m['specimen']}] Esito: {status} | Isolati: {isol}{cfu_str}{dtp_str}")

            # 2. Admission and Emergency Reports (if admission day)
            if day_num == 1:
                for rep in self.data.get("admission_reports", []):
                    clean_adm = self._prune_text(rep["text"], max_chars=1400)
                    chunk_text_parts.append(f"\n--- VERBALE DI PRONTO SOCCORSO / RICOVERO ({rep['filename']}) ---\n{clean_adm}")

            # 3. ID Consultations for this date
            for consult in self.data.get("id_consultations", []):
                if d_str in consult.get("dates", []):
                    clean_id = self._prune_text(consult["full_text"], max_chars=1200)
                    chunk_text_parts.append(f"\n--- CONSULENZA INFETTIVOLOGICA ({consult['filename']}) ---\n{clean_id}")

            # 4. Clinical Diary notes for this date
            if d_str in daily_diary_text:
                for note in daily_diary_text[d_str]:
                    chunk_text_parts.append(f"\n{note}")

            full_chunk_text = "\n".join(chunk_text_parts)
            # Safe bounding: cap text to 3800 chars. Notice microbiology was placed FIRST so it is never truncated!
            if len(full_chunk_text) > 3800:
                full_chunk_text = full_chunk_text[:3800] + "\n[... Estratto note secondarie compresso per limiti di contesto ...]"

            token_est = len(full_chunk_text.split()) * 1.3

            chunks.append({
                "patient_id": self.patient_id,
                "date": d_str,
                "day_number": day_num,
                "is_admission_day": (day_num == 1),
                "text": full_chunk_text,
                "token_estimate": token_est
            })

        return chunks

    def save_chunks(self, output_base_dir: str) -> List[str]:
        patient_chunk_dir = os.path.join(output_base_dir, f"Paziente_{self.patient_id}")
        os.makedirs(patient_chunk_dir, exist_ok=True)

        chunks = self.build_daily_chunks()
        saved_paths = []
        for c in chunks:
            clean_date = c["date"].replace("/", "-")
            fname = f"chunk_day_{c['day_number']:02d}_{clean_date}.json"
            fpath = os.path.join(patient_chunk_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(c, f, indent=2, ensure_ascii=False)
            saved_paths.append(fpath)
        return saved_paths

"""
Suite Completa di Test Diagnostici e Stress Test per la Suddivisione Temporale dei Dati Clinici (TemporalChunker).
Verifica analitica dei bug emersi dal Benchmark ECDC BSI (accuratezza HA-BSI 57.6% - 63.6%).
"""

import unittest
import os
import sys
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Any

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from pipeline.temporal_chunker import TemporalChunker
from pipeline.ingestion_parser import IngestionParser


class TemporalChunkerDiagnosticSuite(unittest.TestCase):
    """
    Test diagnostici mirati a individuare i bug di suddivisione giornaliera (chunking)
    responsabili delle anomalie di classificazione HA-BSI nell'ultimo benchmark.
    """

    def test_01_flusso_nominale_giornate_consecutive(self):
        """
        TEST 1 (Nominale): Tre giornate di degenza consecutive (Day 1, Day 2, Day 3).
        Ogni pagina rappresenta una giornata distinta.
        """
        patient_data = {
            "patient_id": "TEST_NOMINAL_01",
            "admission_reports": [
                {
                    "filename": "ADM_Doc1.pdf",
                    "text": "Verbale di Pronto Soccorso del 10/05/2023.",
                    "detected_dates": ["10/05/2023"]
                }
            ],
            "clinical_diaries": [
                {
                    "filename": "DIARY_Doc1.pdf",
                    "page_number": 1,
                    "text": "10/05/2023: Val.Triage. Ingresso in reparto.",
                    "dates": ["10/05/2023"],
                    "giornate": []
                },
                {
                    "filename": "DIARY_Doc1.pdf",
                    "page_number": 2,
                    "text": "11/05/2023: 2° giornata. Paziente afebbrile.",
                    "dates": ["11/05/2023"],
                    "giornate": ["2"]
                },
                {
                    "filename": "DIARY_Doc1.pdf",
                    "page_number": 3,
                    "text": "12/05/2023: 3° giornata. Condizioni stabili.",
                    "dates": ["12/05/2023"],
                    "giornate": ["3"]
                }
            ],
            "microbiology_reports": []
        }
        chunker = TemporalChunker(patient_data)
        chunks = chunker.build_daily_chunks()
        
        # Diagnosi del bug di page_num in (1, 2)
        dates = [c["date"] for c in chunks]
        days = [c["day_number"] for c in chunks]
        print(f"\n[Test 1 Nominale] Chunks generati: {list(zip(days, dates))}")
        
        self.assertEqual(len(chunks), 3, 
            f"BUG RILEVATO: attesi 3 chunk giornalieri ma generati {len(chunks)}. "
            f"La pagina 2 e' stata erroneamente schiacciata sul Day 1 dal controllo page_num in (1, 2).")

    def test_02_stress_date_nascita_e_anamnesi_remota(self):
        """
        TEST 2 (Stress - Date storiche): Presenza di data di nascita (1950) e accessi vascolari storici.
        Verifica se determine_admission_date() prende min(dates) retrodatando l'ammissione.
        """
        patient_data = {
            "patient_id": "TEST_BIRTH_ANAMNESIS",
            "admission_reports": [
                {
                    "filename": "ADM.pdf",
                    "text": (
                        "Verbale Pronto Soccorso.\n"
                        "Paziente Nato il 15/08/1950 a Bologna.\n"
                        "CVC inserito il 10/01/2015.\n"
                        "Data di Accesso e Triage: 01/02/2020."
                    ),
                    "detected_dates": ["15/08/1950", "10/01/2015", "01/02/2020"]
                }
            ],
            "clinical_diaries": [
                {
                    "filename": "DIARY.pdf",
                    "page_number": 1,
                    "text": "01/02/2020: Ingresso.",
                    "dates": ["01/02/2020"],
                    "giornate": []
                }
            ],
            "microbiology_reports": [
                {
                    "filename": "MICRO.pdf",
                    "prelievo_date": "01/02/2020",
                    "specimen": "EMOCOLTURA",
                    "is_positive": True,
                    "isolates": ["Escherichia coli"]
                }
            ]
        }
        chunker = TemporalChunker(patient_data)
        adm_date = chunker.determine_admission_date()
        chunks = chunker.build_daily_chunks()
        days = [c["day_number"] for c in chunks]
        
        print(f"\n[Test 2 Stress Date Storiche] Ammissione stimata: {adm_date} | Giorni: {days}")
        self.assertEqual(adm_date, "01/02/2020",
            f"BUG CRITICO RILEVATO: Ammissione calcolata al {adm_date} anziche' 01/02/2020. "
            f"min(dates) cattura la data di nascita/anamnesi, proiettando il ricovero a Day {days[-1]}!")

    def test_03_stress_giorni_negativi(self):
        """
        TEST 3 (Stress - Giorni negativi): Prelievo o referto con data antecedente all'ammissione.
        Verifica che non vengano prodotti file come chunk_day_-214_...json.
        """
        patient_data = {
            "patient_id": "TEST_NEGATIVE_DAYS",
            "admission_reports": [
                {
                    "filename": "ADM.pdf",
                    "text": "Ammissione del 10/10/2021",
                    "detected_dates": ["10/10/2021"]
                }
            ],
            "clinical_diaries": [],
            "microbiology_reports": [
                {
                    "filename": "MICRO.pdf",
                    "prelievo_date": "10/03/2021",  # Errore tipico da estrazione data di nascita
                    "specimen": "EMOCOLTURA",
                    "is_positive": True,
                    "isolates": ["Escherichia coli"]
                }
            ]
        }
        chunker = TemporalChunker(patient_data)
        chunks = chunker.build_daily_chunks()
        days = [c["day_number"] for c in chunks]
        
        print(f"\n[Test 3 Stress Giorni Negativi] Giorni prodotti: {days}")
        has_negative = any(d < 1 for d in days)
        self.assertFalse(has_negative,
            f"BUG CRITICO RILEVATO: Generati giorni negativi {days}. "
            f"Questo crea prompt non validi ('Giorno -214') che allucinano i modelli LLM.")

    def test_04_stress_troncamento_microbiologia(self):
        """
        TEST 4 (Stress - Sovraccarico di testo): Nota clinica lunga per verificare se il tetto di 3800
        caratteri tronca i referti microbiologici accodati in fondo al chunk.
        """
        clinical_text = "Nota clinica del medico di reparto. " + ("Condizioni generali invariate, prosegue monitoraggio. " * 40)
        patient_data = {
            "patient_id": "TEST_TRUNCATION",
            "admission_reports": [],
            "clinical_diaries": [
                {
                    "filename": "DIARY_1.pdf",
                    "page_number": 3,
                    "text": f"05/03/2022: {clinical_text}",
                    "dates": ["05/03/2022"],
                    "giornate": []
                },
                {
                    "filename": "DIARY_2.pdf",
                    "page_number": 4,
                    "text": f"05/03/2022: {clinical_text}",
                    "dates": ["05/03/2022"],
                    "giornate": []
                }
            ],
            "microbiology_reports": [
                {
                    "filename": "MICRO_CRIT.pdf",
                    "prelievo_date": "05/03/2022",
                    "specimen": "EMOCOLTURA_PERIFERICA",
                    "is_positive": True,
                    "isolates": ["Staphylococcus epidermidis"],
                    "cfu": None,
                    "dtp": None
                }
            ]
        }
        chunker = TemporalChunker(patient_data)
        chunks = chunker.build_daily_chunks()
        chunk_text = chunks[0]["text"]
        
        print(f"\n[Test 4 Stress Troncamento] Lunghezza chunk finale: {len(chunk_text)} caratteri")
        has_micro = "Staphylococcus epidermidis" in chunk_text
        self.assertTrue(has_micro,
            "BUG CRITICO RILEVATO: I referti microbiologici essenziali sono stati TRONCATI via dal chunk "
            "perche' la nota del diario ha superato il limite di 3800 caratteri.")

    def test_05_stress_formula_xgiornata_off_by_one(self):
        """
        TEST 5 (Stress - Formula X° giornata):
        Verifica che '2° giornata' corrisponda a Day 2 (ammissione + 1 giorno) e non Day 4 (ammissione + 3 giorni).
        """
        patient_data = {
            "patient_id": "TEST_OFF_BY_ONE",
            "admission_reports": [
                {
                    "filename": "ADM.pdf",
                    "text": "Ricovero del 01/01/2020",
                    "detected_dates": ["01/01/2020"]
                }
            ],
            "clinical_diaries": [
                {
                    "filename": "DIARY.pdf",
                    "page_number": 1,
                    "text": "01/01/2020: Val.Triage.",
                    "dates": ["01/01/2020"],
                    "giornate": []
                },
                {
                    "filename": "DIARY.pdf",
                    "page_number": 3,
                    "text": "2° giornata: parametri stabili.",
                    "dates": [],
                    "giornate": ["2"]
                }
            ],
            "microbiology_reports": []
        }
        chunker = TemporalChunker(patient_data)
        chunks = chunker.build_daily_chunks()
        day_map = {c["date"]: c["day_number"] for c in chunks}
        
        print(f"\n[Test 5 Stress Formula X Giornata] Mappa (Data -> Day Number): {day_map}")
        # 2° giornata con ammissione 01/01/2020 deve essere 02/01/2020 (Day 2)
        self.assertIn("02/01/2020", day_map,
            f"BUG CRITICO RILEVATO: La '2° giornata' e' stata mappata a {list(day_map.keys())}. "
            f"La formula 'g_num + 1' ha aggiunto +2 giorni spostando erroneamente la giornata a Day 4!")

    def test_06_stress_multidoc_page_number_reset(self):
        """
        TEST 6 (Stress - Reset numero di pagina su molteplici PDF):
        Se il paziente ha 2 PDF di diario clinico, il secondo PDF inizia da pagina 1.
        Il controllo page_num in (1, 2) non deve resettare la data alla data di ammissione.
        """
        patient_data = {
            "patient_id": "TEST_MULTIDOC_RESET",
            "admission_reports": [
                {
                    "filename": "ADM.pdf",
                    "text": "Ammissione 01/03/2021",
                    "detected_dates": ["01/03/2021"]
                }
            ],
            "clinical_diaries": [
                {
                    "filename": "DIARY_Doc1.pdf",
                    "page_number": 1,
                    "text": "01/03/2021: Triage.",
                    "dates": ["01/03/2021"],
                    "giornate": []
                },
                {
                    "filename": "DIARY_Doc2.pdf",  # Secondo documento due settimane dopo!
                    "page_number": 1,
                    "text": "15/03/2021: Nota di trasferimento.",
                    "dates": ["15/03/2021"],
                    "giornate": []
                }
            ],
            "microbiology_reports": []
        }
        chunker = TemporalChunker(patient_data)
        chunks = chunker.build_daily_chunks()
        chunk_dates = [c["date"] for c in chunks]
        
        print(f"\n[Test 6 Stress MultiDoc Page Reset] Date generate: {chunk_dates}")
        self.assertIn("15/03/2021", chunk_dates,
            f"BUG RILEVATO: La data 15/03/2021 e' stata persa o schiacciata su 01/03/2021 "
            f"a causa del reset del numero di pagina su file PDF multipli.")


if __name__ == "__main__":
    unittest.main()

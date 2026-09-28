"""
Suite di Quality Control (3 Loops) per il Motore di Classificazione Deterministica ECDC (ECDCClassifier).
Verifica analitica delle definizioni di caso ECDC PPS 6.1:
  - Loop 1: BSI Case Definition & Criteri Microbiologici (Criterio 1 vs 2, Contaminanti, Finestra 48h, Stesso patogeno)
  - Loop 2: Healthcare Association (HA-BSI vs CA-BSI, Day 3+, Dispositivi 'prior to onset', Dimissioni 48h)
  - Loop 3: Source Attribution (CRI3-CVC, C-CVC, Focolai Secondari, Risoluzione conflitti) & Setting (CURR vs OHOSP)
"""

import unittest
import os
import sys
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from pipeline.ecdc_classifier import ECDCClassifier


class TestECDCClassifierQCLoops(unittest.TestCase):

    # =========================================================================
    # LOOP 1: BSI Case Definition & Criteri Microbiologici
    # =========================================================================

    def test_loop1_01_abbreviated_skin_contaminants(self):
        """
        LOOP 1 - TEST 1:
        Verifica se le denominazioni abbreviate o sinonimi dei contaminanti cutanei
        (es. 's. hominis', 'S. epidermidis', 'CNS', 'Stafilococco coagulasi-negativo')
        vengono correttamente riconosciuti come contaminanti cutanei e NON come patogeni virulenti.
        """
        clf = ECDCClassifier("TEST_CONTAM_ABBR", [])
        self.assertTrue(clf._is_skin_contaminant("s. hominis"), "BUG: 's. hominis' non riconosciuto come contaminante cutaneo!")
        self.assertTrue(clf._is_skin_contaminant("S. epidermidis"), "BUG: 'S. epidermidis' non riconosciuto come contaminante cutaneo!")
        self.assertTrue(clf._is_skin_contaminant("CNS"), "BUG: 'CNS' non riconosciuto come contaminante cutaneo!")
        self.assertTrue(clf._is_skin_contaminant("Stafilococco coagulasi-negativo"), "BUG: 'Stafilococco coagulasi-negativo' con trattino non riconosciuto!")

    def test_loop1_02_skin_contaminant_same_organism_requirement(self):
        """
        LOOP 1 - TEST 2:
        Secondo ECDC Criterio 2, le due emocolture per contaminante cutaneo DEVONO
        isolare lo STESSO microrganismo.
        Due microrganismi diversi (es. S. epidermidis e Corynebacterium) NON costituiscono BSI da contaminante.
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "01/01/2020", "is_positive": True, "isolates": ["Staphylococcus epidermidis"]},
            {"specimen": "EMOCOLTURA", "prelievo_date": "02/01/2020", "is_positive": True, "isolates": ["Corynebacterium sp."]}
        ]
        exts = [
            {"day_number": 1, "date": "01/01/2020", "entities": {"segni_vitali": {"febbre": {"presente": True}}}},
            {"day_number": 2, "date": "02/01/2020", "entities": {}}
        ]
        clf = ECDCClassifier("TEST_DIFF_CONTAM", exts, micro)
        res = clf.classify()
        self.assertEqual(res["bsi"], "NO",
            "BUG: BSI classificata SI con 2 contaminanti DIVERSI (S. epidermidis + Corynebacterium). ECDC richiede lo STESSO contaminante!")

    def test_loop1_03_skin_contaminant_48h_window(self):
        """
        LOOP 1 - TEST 3:
        Secondo ECDC Criterio 2, le due emocolture per contaminante cutaneo devono essere
        prelevate entro una finestra temporale ravvicinata (solitamente 48 ore).
        Due emocolture a distanza di 30 giorni sono due eventi isolati, non una BSI confermata.
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "01/01/2020", "is_positive": True, "isolates": ["Staphylococcus epidermidis"]},
            {"specimen": "EMOCOLTURA", "prelievo_date": "01/02/2020", "is_positive": True, "isolates": ["Staphylococcus epidermidis"]}
        ]
        exts = [
            {"day_number": 1, "date": "01/01/2020", "entities": {"segni_vitali": {"febbre": {"presente": True}}}},
            {"day_number": 32, "date": "01/02/2020", "entities": {}}
        ]
        clf = ECDCClassifier("TEST_48H_WINDOW", exts, micro)
        res = clf.classify()
        self.assertEqual(res["bsi"], "NO",
            "BUG: BSI Criterio 2 confermata con due emocolture a distanza di 30 giorni l'una dall'altra!")

    # =========================================================================
    # LOOP 2: Healthcare Association (HA-BSI vs CA-BSI) & Temporal Logic
    # =========================================================================

    def test_loop2_01_same_day_device_insertion_not_ha_bsi(self):
        """
        LOOP 2 - TEST 1:
        Un paziente arriva al Day 1 con febbre e shock settico. Gli viene inserito un CVC al Day 1
        durante la rianimazione in DEA e vengono prelevate emocolture al Day 1.
        L'infezione NON e' ospedaliera (HA-BSI): il CVC e' stato inserito contestualmente, NON 'prior to onset'.
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "01/01/2020", "is_positive": True, "isolates": ["Escherichia coli"]}
        ]
        exts = [
            {
                "day_number": 1,
                "date": "01/01/2020",
                "entities": {
                    "catetere_venoso": {"cvc_inserito_oggi": True},
                    "segni_vitali": {"febbre": {"presente": True}}
                }
            }
        ]
        clf = ECDCClassifier("TEST_SAME_DAY_CVC", exts, micro)
        res = clf.classify()
        self.assertEqual(res["ha_bsi"], "NO",
            "BUG CRITICO: Un'emocoltura di Day 1 con CVC inserito lo stesso giorno (Day 1) e' stata classificata HA-BSI! "
            "Un catetere inserito in DEA al momento dell'ammissione non puo' causare la batteriemia di ingresso.")

    def test_loop2_02_ha_bsi_device_inserted_prior_to_onset(self):
        """
        LOOP 2 - TEST 2:
        Paziente ricoverato al Day 1. CVC inserito al Day 1.
        Al Day 2 compare nuova febbre ed emocolture positive.
        In questo caso, il dispositivo e' stato inserito in questa degenza PRIMA dell'insorgenza (Day 1 < Day 2).
        Questo E' un HA-BSI valido secondo criterio ECDC Day 1/2.
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "02/01/2020", "is_positive": True, "isolates": ["Staphylococcus aureus"]}
        ]
        exts = [
            {
                "day_number": 1,
                "date": "01/01/2020",
                "entities": {"catetere_venoso": {"cvc_inserito_oggi": True}}
            },
            {
                "day_number": 2,
                "date": "02/01/2020",
                "entities": {"segni_vitali": {"febbre": {"presente": True}}}
            }
        ]
        clf = ECDCClassifier("TEST_DEVICE_PRIOR", exts, micro)
        res = clf.classify()
        self.assertEqual(res["ha_bsi"], "SI",
            "CVC inserito al Day 1 prima dell'insorgenza al Day 2 deve essere riconosciuto come HA-BSI.")

    # =========================================================================
    # LOOP 3: Source Attribution & Place of Acquisition (Setting)
    # =========================================================================

    def test_loop3_01_setting_curr_hospital_after_day_2(self):
        """
        LOOP 3 - TEST 1:
        Un paziente trasferito da altro ospedale (provenienza: ALTRO_OSPEDALE)
        sviluppa una batteriemia al Day 10 di ricovero nell'ospedale corrente.
        L'infezione e' insorta nell'ospedale attuale (Day >= 3), quindi il setting DEVE essere CURR, non OHOSP!
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "10/01/2020", "is_positive": True, "isolates": ["Pseudomonas aeruginosa"]}
        ]
        exts = [
            {
                "day_number": 1,
                "date": "01/01/2020",
                "entities": {"ammissione": {"provenienza": "ALTRO_OSPEDALE"}}
            },
            {
                "day_number": 10,
                "date": "10/01/2020",
                "entities": {"segni_vitali": {"febbre": {"presente": True}}}
            }
        ]
        clf = ECDCClassifier("TEST_SETTING_CURR", exts, micro)
        res = clf.classify()
        self.assertEqual(res["luogo_acquisizione"], "CURR",
            f"BUG CRITICO: Batteriemia insorta al Day 10 classificata come {res['luogo_acquisizione']} anziche' CURR. "
            "Infezioni insorte dopo il Day 2 appartengono all'ospedale corrente.")

    def test_loop3_02_clinical_foci_priority_and_pathogen_coherence(self):
        """
        LOOP 3 - TEST 2:
        Paziente con urosepsi da E. coli: urocoltura positiva per E. coli al Day 1,
        ed emocoltura positiva per E. coli al Day 3. La nota menziona anche lieve diarrea/nausea (S-DIG).
        La presenza dell'urocoltura con lo STESSO patogeno DEVE avere precedenza su note cliniche generiche.
        """
        micro = [
            {"specimen": "EMOCOLTURA", "prelievo_date": "03/01/2020", "is_positive": True, "isolates": ["Escherichia coli"]},
            {"specimen": "UROCOLTURA", "prelievo_date": "03/01/2020", "is_positive": True, "isolates": ["Escherichia coli"]}
        ]
        exts = [
            {
                "day_number": 1,
                "date": "01/01/2020",
                "entities": {
                    "focolai_infezione": [
                        {"sito": "DIG", "sospetto_o_conferma": True, "evidenza": "lieve diarrea"},
                        {"sito": "UTI", "sospetto_o_conferma": True, "evidenza": "cistite/disuria"}
                    ]
                }
            },
            {
                "day_number": 3,
                "date": "03/01/2020",
                "entities": {"segni_vitali": {"febbre": {"presente": True}}}
            }
        ]
        clf = ECDCClassifier("TEST_FOCI_PRECEDENCE", exts, micro)
        res = clf.classify()
        self.assertEqual(res["origine"], "S-UTI",
            f"BUG: Origine classificata {res['origine']} anziche' S-UTI nonostante urocoltura positiva per lo stesso patogeno (E. coli).")


if __name__ == "__main__":
    unittest.main()

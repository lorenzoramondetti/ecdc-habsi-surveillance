import json
from typing import Dict, Any

SYSTEM_PROMPT = """Sei un medico epidemiologo ed estrattore deterministico di entità cliniche per la sorveglianza delle batteriemie (ECDC HA-BSI).
Il tuo compito è individuare ed estrarre menzioni testuali verbatim dal testo fornito, senza deduzioni arbitrarie o sintesi.

REGOLE FONDAMENTALI:
1. ESTRAZIONE VERBATIM: Nel campo "testo_estratto" inserisci SEMPRE la citazione testuale esatta, copiata parola per parola dal testo clinico originale tra virgolette, a supporto del reperto.
2. MODIFICATORI CLINICI:
   - "presente": true se il riscontro è accertato/confermato clinicamente; altrimenti false.
   - "negato": true se il reperto è esplicitamente negato o assente (es. "apiretica", "nega brividi", "non segni flogosi al CVC"); altrimenti false.
   - "soggetto": considera ESCLUSIVAMENTE il paziente in esame. Ignora l'anamnesi familiare.
   - "stato_temporale": "in_corso" (condizione attiva oggi), "remoto" (pregresso/risolto), "inserito_oggi" (dispositivo posizionato oggi), "rimosso_oggi" (dispositivo rimosso oggi).
3. ASSENZA DI INFORMAZIONI: Se un'informazione non è esplicitamente presente nel testo, lascia boolean false o null. Non inventare mai dati.

RISPONDI ESCLUSIVAMENTE CON UN OGGETTO JSON VALIDO. Nessun testo di pensiero o commento prima o dopo il JSON.
"""

EXTRACTION_SCHEMA = {
    "segni_vitali": {
        "febbre": {"presente": False, "negato": False, "tc_valore": None, "testo_estratto": None},
        "ipotensione": {"presente": False, "negato": False, "pas_valore": None, "testo_estratto": None},
        "brividi": {"presente": False, "negato": False, "testo_estratto": None},
        "ipotermia": {"presente": False, "negato": False, "tc_valore": None, "testo_estratto": None}
    },
    "catetere_venoso": {
        "cvc_in_sede": False,
        "cvc_inserito_oggi": False,
        "cvc_rimosso_oggi": False,
        "pvc_inserito_oggi": False,
        "segni_infezione_sito_pus_eritema": False,
        "miglioramento_48h_post_rimozione": False,
        "testo_estratto": None
    },
    "microbiologia": [
        {
            "tipo_campione": "EMOCOLTURA_PERIFERICA | EMOCOLTURA_CVC | UROCOLTURA | PUNTA_CATETERE | LIQUOR | RESPIRATORIO | FERITA | ALTRO",
            "esito_positivo": True,
            "microrganismo": "Nome esatto patogeno",
            "carica_cfu": None,
            "dtp": None,
            "testo_estratto": "Citazione verbatim referto"
        }
    ],
    "focolai_infezione": [
        {
            "sito": "S-UTI | S-PUL | S-DIG | S-SST | S-SSI | S-OTH",
            "sospetto_o_conferma": True,
            "testo_estratto": "Citazione verbatim del focolaio"
        }
    ],
    "ammissione": {
        "provenienza": "DOMICILIO | RSA | ALTRO_OSPEDALE | SCONOSCIUTA",
        "dimesso_recente_48h": False,
        "testo_estratto": None
    }
}

FEW_SHOT_EXAMPLE = """ESEMPIO GUIDA:
Testo clinico:
\"Pz giunto da RSA per decadimento e iperpiressia. In DEA riscontrata TC 39.1°C con brividi scuotenti, PAO 85/50. Posizionato CVC bilume giugulare dx. Eseguite emocolture da vena periferica e da CVC. All'ecografia addominale quadro compatibile con colecistite acuta litiasica. Refertata emocoltura periferica positiva per Klebsiella pneumoniae.\"

Output JSON atteso:
{
  "segni_vitali": {
    "febbre": {"presente": true, "negato": false, "tc_valore": "39.1", "testo_estratto": "TC 39.1°C"},
    "ipotensione": {"presente": true, "negato": false, "pas_valore": "85", "testo_estratto": "PAO 85/50"},
    "brividi": {"presente": true, "negato": false, "testo_estratto": "brividi scuotenti"},
    "ipotermia": {"presente": false, "negato": false, "tc_valore": null, "testo_estratto": null}
  },
  "catetere_venoso": {
    "cvc_in_sede": true,
    "cvc_inserito_oggi": true,
    "cvc_rimosso_oggi": false,
    "pvc_inserito_oggi": false,
    "segni_infezione_sito_pus_eritema": false,
    "miglioramento_48h_post_rimozione": false,
    "testo_estratto": "Posizionato CVC bilume giugulare dx"
  },
  "microbiologia": [
    {
      "tipo_campione": "EMOCOLTURA_PERIFERICA",
      "esito_positivo": true,
      "microrganismo": "Klebsiella pneumoniae",
      "carica_cfu": null,
      "dtp": null,
      "testo_estratto": "emocoltura periferica positiva per Klebsiella pneumoniae"
    }
  ],
  "focolai_infezione": [
    {
      "sito": "S-DIG",
      "sospetto_o_conferma": true,
      "testo_estratto": "quadro compatibile con colecistite acuta litiasica"
    }
  ],
  "ammissione": {
    "provenienza": "RSA",
    "dimesso_recente_48h": false,
    "testo_estratto": "giunto da RSA"
  }
}
"""

def create_extraction_prompt(chunk_text: str, patient_id: str, date_str: str, day_number: int) -> str:
    """Generates the structured Italian clinical extraction prompt for a single daily chunk."""
    prompt = f"""Analizza il seguente estratto clinico giornaliero del Paziente {patient_id} relativo alla data {date_str} (Giorno di degenza: Day {day_number}).

{FEW_SHOT_EXAMPLE}

TESTO CLINICO GIORNALIERO DA ANALIZZARE:
\"\"\"
{chunk_text}
\"\"\"

Compila ed estrai in JSON rigoroso e valido secondo questa struttura esatta:
{json.dumps(EXTRACTION_SCHEMA, indent=2, ensure_ascii=False)}
"""
    return prompt

def create_extraction_prompt_en(chunk_text: str, patient_id: str, date_str: str, day_number: int) -> str:
    """English variant prompt for future performance comparison."""
    prompt = f"""Analyze the following daily clinical text for Patient {patient_id} on date {date_str} (Hospitalization Day: {day_number}).
Extract all clinical entities verbatim using exact quotes from the text.

CLINICAL TEXT TO ANALYZE:
\"\"\"
{chunk_text}
\"\"\"

Respond with valid JSON matching this schema:
{json.dumps(EXTRACTION_SCHEMA, indent=2, ensure_ascii=False)}
"""
    return prompt

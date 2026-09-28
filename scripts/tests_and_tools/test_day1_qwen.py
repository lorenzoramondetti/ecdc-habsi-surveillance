import requests, json
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker

parser = IngestionParser(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1")
data = parser.parse_all()
chunker = TemporalChunker(data)
chunks = chunker.build_daily_chunks()
day1 = chunks[0]

compact_schema = {
  "segni_vitali": {
    "febbre": {"presente": False, "negato": False, "tc_valore": None, "testo_estratto": None},
    "ipotensione": {"presente": False, "negato": False, "pas_valore": None, "testo_estratto": None},
    "brividi": {"presente": False, "negato": False, "testo_estratto": None}
  },
  "catetere_venoso": {
    "cvc_in_sede": False,
    "cvc_inserito_oggi": False,
    "cvc_rimosso_oggi": False,
    "segni_infezione_sito_pus_eritema": False,
    "miglioramento_48h_post_rimozione": False,
    "testo_estratto": None
  },
  "microbiologia": [
    {
      "tipo_campione": "EMOCOLTURA_PERIFERICA",
      "esito_positivo": True,
      "microrganismo": "Enterobacter aerogenes",
      "carica_cfu": None,
      "dtp": None,
      "testo_estratto": "emocolture in corso..."
    }
  ],
  "focolai_infezione": [
    {
      "sito": "S-UTI",
      "sospetto_o_conferma": True,
      "testo_estratto": "PNA multifocale destra"
    }
  ],
  "ammissione": {
    "provenienza": "DOMICILIO",
    "dimesso_recente_48h": False,
    "testo_estratto": "al domicilio"
  }
}

user_prompt = f"""Analizza il seguente testo clinico del Paziente {day1['patient_id']} per la data {day1['date']} (Giorno di degenza: Day {day1['day_number']}).
Estrai i parametri clinici secondo lo schema JSON indicato. Nel campo 'testo_estratto' riporta sempre la citazione testuale verbatim esatta.

TESTO CLINICO:
\"\"\"
{day1['text']}
\"\"\"

Restituisci ESCLUSIVAMENTE l'oggetto JSON compilato conforme a questa struttura:
{json.dumps(compact_schema, indent=2)}
"""

payload = {
    "model": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "messages": [
        {"role": "system", "content": "Sei un medico estrattore di dati clinici. Restituisci ESCLUSIVAMENTE un oggetto JSON valido. Nessun commento."},
        {"role": "user", "content": user_prompt}
    ],
    "format": "json",
    "stream": False,
    "options": {
        "temperature": 0.0,
        "num_ctx": 8192,
        "num_predict": 3500
    }
}

print(f"Sending request for Day 1 (~{int(day1['token_estimate'])} tokens)...")
r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=180)
print("Status code:", r.status_code)
res = r.json()
content = res.get("message", {}).get("content", "")
thinking = res.get("message", {}).get("thinking", "")
print(f"Content len: {len(content)}")
print(f"Thinking len: {len(thinking)}")
print(f"Done reason: {res.get('done_reason')}")
print("Extracted content:\n", content[:1000])

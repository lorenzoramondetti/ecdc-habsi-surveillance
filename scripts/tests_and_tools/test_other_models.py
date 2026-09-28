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
    "febbre": {"presente": False, "tc_valore": None, "testo_estratto": None},
    "ipotensione": {"presente": False, "pas_valore": None, "testo_estratto": None},
    "brividi": {"presente": False, "testo_estratto": None}
  },
  "catetere_venoso": {
    "cvc_in_sede": False,
    "cvc_inserito_oggi": False,
    "cvc_rimosso_oggi": False,
    "testo_estratto": None
  },
  "microbiologia": [
    {
      "tipo_campione": "EMOCOLTURA_PERIFERICA",
      "esito_positivo": True,
      "microrganismo": "Enterobacter aerogenes",
      "testo_estratto": "citazione"
    }
  ],
  "focolai_infezione": [
    {"sito": "S-UTI", "sospetto_o_conferma": True, "testo_estratto": "citazione"}
  ],
  "ammissione": {
    "provenienza": "DOMICILIO",
    "dimesso_recente_48h": False,
    "testo_estratto": "citazione"
  }
}

user_prompt = f"""Estrai i parametri clinici secondo lo schema JSON indicato.
NON RAGIONARE. Genera direttamente l'oggetto JSON finale.

TESTO CLINICO:
\"\"\"
{day1['text']}
\"\"\"

SCHEMA JSON:
{json.dumps(compact_schema, indent=2)}
"""

for model in ["glm-4.7-flash:latest", "gemma4:26b"]:
    print(f"\n==========================================")
    print(f"Testing model: {model} on Day 1")
    print(f"==========================================")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Sei un medico estrattore di dati clinici. Restituisci ESCLUSIVAMENTE un oggetto JSON valido. Nessun preambolo."},
            {"role": "user", "content": user_prompt}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 2048
        }
    }
    try:
        r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=90)
        res = r.json()
        content = res.get("message", {}).get("content", "")
        thinking = res.get("message", {}).get("thinking", "")
        print(f"Status: {r.status_code} | Content len: {len(content)} | Thinking len: {len(thinking)}")
        print(f"Done reason: {res.get('done_reason')}")
        print("Content sample:\n", content[:600])
    except Exception as e:
        print("Error:", e)

import requests, json, time
from pipeline.prompt_templates import SYSTEM_PROMPT, EXTRACTION_SCHEMA_COMPACT

text_sample = """
02/01/2000 09:57:00 0° giornata
T: 36,9, Pa D: 70, Pa Sist.: 130, F.C.: 90, SaO2 AA: 96
Paziente vigile, orientata ST, collaborante. Eupnoica in AA.
Asintomatica per disturbi di rilievo. Apiretica nella notte.
Cute perfusa. Mucose idratate.
In attesa di posto letto in nefrologia.
emocolture e urocoltura in corso.
riposizionare accesso venoso
piperacillina + tazobactam 2200 mg
"""

prompt = f"""Estrai i parametri clinici secondo lo schema JSON indicato.
NON SCRIVERE ALCUN RAGIONAMENTO. INIZIA DIRETTAMENTE CON {{ E CHIUDI CON }}.

TESTO:
{text_sample}

SCHEMA JSON:
{json.dumps(EXTRACTION_SCHEMA_COMPACT, indent=2)}
"""

for model in ["gemma4:12b", "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest"]:
    print(f"\n==========================================")
    print(f"Testing model: {model}")
    print(f"==========================================")
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Sei un estrattore di dati clinici. Restituisci ESCLUSIVAMENTE un oggetto JSON valido. Nessun ragionamento, nessun preambolo, nessun testo prima o dopo il JSON."},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 512
        }
    }
    
    t0 = time.time()
    try:
        r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=120)
        dt = time.time() - t0
        res = r.json()
        content = res.get("message", {}).get("content", "")
        thinking = res.get("message", {}).get("thinking", "")
        print(f"Status: {r.status_code} in {dt:.2f}s")
        print(f"Prompt tokens: {res.get('prompt_eval_count')}, Eval tokens: {res.get('eval_count')}")
        print(f"Thinking present? {bool(thinking)} (len: {len(thinking)})")
        print(f"Content (first 250 chars):\n{content[:250]}")
    except Exception as e:
        print("Error:", e)

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

prompt = f"""Analizza il testo seguente ed estrai i parametri in JSON.

TESTO:
{text_sample}

SCHEMA JSON:
{json.dumps(EXTRACTION_SCHEMA_COMPACT, indent=2)}
"""

payload = {
    'model': 'hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest',
    'messages': [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt}
    ],
    'format': 'json',
    'stream': False,
    'think': False,
    'options': {
        'temperature': 0.0,
        'num_predict': 512
    }
}

t0 = time.time()
r = requests.post('http://127.0.0.1:11434/api/chat', json=payload, timeout=180)
dt = time.time() - t0
data = r.json()
msg = data.get('message', {})
print(f"Elapsed: {dt:.2f}s")
print("HAS THINKING:", bool(msg.get('thinking')))
print(f"Prompt tokens: {data.get('prompt_eval_count')}, Eval tokens: {data.get('eval_count')}")
print("CONTENT:")
print(msg.get('content'))

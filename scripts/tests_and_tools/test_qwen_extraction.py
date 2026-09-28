import requests, json

test_chunk = """=== PAZIENTE: 0E691DF1 | DATA: 02/01/2000 | GIORNO DI DEGENZA: Day 2 ===
09:57:00 0° giornata
Dolore: 0, T: 36,9, Pa D: 70, Pa Sist.: 130, F.C.: 90, SaO2 AA: 96
Paziente vigile, orientata ST, collaborante. Eupnoica in AA.
Asintomatica per disturbi di rilievo. Apiretica nella notte.
Cute perfusa. Mucose idratate.
In attesa di posto letto in nefrologia.
emocolture e urocoltura in corso.
riposizionare accesso venoso.
piperacillina + tazobactam 2200 mg.
"""

from pipeline.prompt_templates import SYSTEM_PROMPT, EXTRACTION_SCHEMA, create_extraction_prompt

prompt = create_extraction_prompt(test_chunk, "0E691DF1", "02/01/2000", 2)

payload = {
    "model": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ],
    "format": "json",
    "stream": False,
    "options": {
        "temperature": 0.0,
        "num_ctx": 8192,
        "num_predict": 2048
    }
}

r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=120)
print("Status:", r.status_code)
res = r.json()
msg = res.get("message", {})
content = msg.get("content", "")
thinking = msg.get("thinking", "")
print(f"Content length: {len(content)}")
print(f"Thinking length: {len(thinking)}")
print(f"Done reason: {res.get('done_reason')}")
print(f"Eval count: {res.get('eval_count')}")
print("Content sample:\n", content[:500])

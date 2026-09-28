import requests, json

test_chunk = '09:57:00 T: 36,9, Pa Sist: 130, Pa D: 70. Apiretica. emocolture in corso per sospetta sepsi.'

from pipeline.prompt_templates import EXTRACTION_SCHEMA

prompt = f"""RISPONDI ESCLUSIVAMENTE CON L'OGGETTO JSON. NON RAGIONARE. INIZIA DIRETTAMENTE CON {{.

TESTO:
{test_chunk}

SCHEMA JSON:
{json.dumps(EXTRACTION_SCHEMA, indent=2)}
"""

# Test 1: with num_predict 3000
payload = {
    'model': 'gemma4:12b',
    'messages': [
        {'role': 'system', 'content': 'You are a JSON extractor. Output valid JSON only. Do not think or explain.'},
        {'role': 'user', 'content': prompt}
    ],
    'format': 'json',
    'stream': False,
    'options': {'temperature': 0.0, 'num_predict': 3000}
}
r = requests.post('http://127.0.0.1:11434/api/chat', json=payload, timeout=90)
res = r.json()
print("--- TEST 1 (num_predict 3000) ---")
print("Content len:", len(res.get('message', {}).get('content', '')))
print("Thinking len:", len(res.get('message', {}).get('thinking', '')))
print("Done reason:", res.get('done_reason'))
print("Content:\n", res.get('message', {}).get('content', '')[:400])

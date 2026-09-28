import requests, json

payload = {
    'model': 'hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest',
    'messages': [
        {'role': 'system', 'content': 'Sei un assistente. Rispondi ESCLUSIVAMENTE in JSON valido.'},
        {'role': 'user', 'content': 'Estrai: "Febbre a 38.5". Schema: {"febbre": true, "tc": 38.5}'}
    ],
    'format': 'json',
    'stream': False,
    'options': {
        'temperature': 0.0,
        'num_ctx': 4096,
        'num_predict': 256
    }
}
try:
    r = requests.post('http://127.0.0.1:11434/api/chat', json=payload, timeout=60)
    print('Status:', r.status_code)
    print('Response:', r.json())
except Exception as e:
    print('Error:', e)

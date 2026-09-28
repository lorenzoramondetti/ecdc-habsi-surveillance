import requests, json

payload = {
    "model": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "messages": [
        {"role": "system", "content": "You are a direct JSON extractor. Do not think. Output valid JSON only."},
        {"role": "user", "content": "Estrai TC: 'Paziente febbrile con TC 39.2'. Rispondi: {\"tc\": 39.2}"},
        {"role": "assistant", "content": "{"}
    ],
    "format": "json",
    "stream": False,
    "options": {"temperature": 0.0, "num_predict": 100}
}
try:
    r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=30)
    print("Pre-fill status:", r.status_code)
    print("Response:", r.json().get("message"))
except Exception as e:
    print("Error:", e)

import requests, json

payload = {
    "model": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "messages": [
        {"role": "user", "content": "Rispondi ESCLUSIVAMENTE con {\"status\": \"ok\"}. Non pensare."}
    ],
    "format": "json",
    "stream": False,
    "options": {"temperature": 0.0, "num_predict": 300}
}
r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=30)
res = r.json()
print("Message:", res.get("message"))

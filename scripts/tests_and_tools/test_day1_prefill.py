import requests, json, time
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.prompt_templates import SYSTEM_PROMPT, create_extraction_prompt

parser = IngestionParser(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1")
data = parser.parse_all()
chunker = TemporalChunker(data)
chunks = chunker.build_daily_chunks()
day1 = chunks[0]

prompt = create_extraction_prompt(day1['text'], day1['patient_id'], day1['date'], day1['day_number'])

payload = {
    "model": "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": "{"}
    ],
    "format": "json",
    "stream": False,
    "options": {
        "temperature": 0.0,
        "num_ctx": 8192,
        "num_predict": 2048
    }
}

print(f"Sending request for Day 1 with pre-filled '{{'...")
t0 = time.time()
r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=90)
dt = time.time() - t0
print(f"Status: {r.status_code} in {dt:.2f}s")
res = r.json()
msg = res.get("message", {})
content = msg.get("content", "")
thinking = msg.get("thinking", "")
print(f"Content len: {len(content)} | Thinking len: {len(thinking)}")
print(f"Done reason: {res.get('done_reason')}")
print("Extracted content:\n", content[:1200])

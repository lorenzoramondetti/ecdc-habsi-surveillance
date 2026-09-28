import os
from pipeline.config import DATA_DIR
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.prompt_templates import SYSTEM_PROMPT, create_extraction_prompt
import requests, json

candidates = [os.path.join(DATA_DIR, d) for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
parser = IngestionParser(candidates[0] if candidates else DATA_DIR)
data = parser.parse_all()
chunker = TemporalChunker(data)
chunks = chunker.build_daily_chunks()

for idx in [0, 2]: # Day 1 and Day 3
    c = chunks[idx]
    print(f"\n--- Testing Day {c['day_number']} (Date: {c['date']}, Len: {len(c['text'])}) ---")
    prompt = create_extraction_prompt(c['text'], c['patient_id'], c['date'], c['day_number'])
    
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
            "num_ctx": 4096,
            "num_predict": 1024
        }
    }
    try:
        r = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=60)
        print("Status code:", r.status_code)
        if r.status_code != 200:
            print("Response text:", r.text)
        else:
            res = r.json()
            content = res.get("message", {}).get("content", "")
            thinking = res.get("message", {}).get("thinking", "")
            print("Content len:", len(content))
            print("Thinking len:", len(thinking))
            print("Done reason:", res.get("done_reason"))
    except Exception as e:
        print("Exception:", e)

import os
from pipeline.config import DATA_DIR
from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker
from pipeline.llm_client import OllamaClient
import json

candidates = [os.path.join(DATA_DIR, d) for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
patient_folder = candidates[0] if candidates else DATA_DIR
parser = IngestionParser(patient_folder)
data = parser.parse_all()
chunker = TemporalChunker(data)
chunks = chunker.build_daily_chunks()

print(f"Total chunks for 0E691DF1: {len(chunks)}")
for c in chunks:
    print(f"Day {c['day_number']:02d}: {c['date']} - Chars: {len(c['text'])} - Tokens: {int(c['token_estimate'])}")

client = OllamaClient(model_name="gemma4:12b")
print(f"\n--- Testing Extraction on Day 1 ({chunks[0]['date']}) ---")
res = client.extract_from_chunk(chunks[0], force_recompute=True)
print(f"Latency: {res['latency_seconds']} s")
print("Extracted:")
print(json.dumps(res['entities'], indent=2, ensure_ascii=False))

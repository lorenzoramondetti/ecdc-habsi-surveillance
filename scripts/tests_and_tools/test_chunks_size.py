from pipeline.ingestion_parser import IngestionParser
from pipeline.temporal_chunker import TemporalChunker

parser = IngestionParser(r"Prime cartelle cliniche anonimizzate\Paziente_0E691DF1")
data = parser.parse_all()
chunker = TemporalChunker(data)
chunks = chunker.build_daily_chunks()
print(f"Total chunks generated: {len(chunks)}")
for c in chunks:
    print(f"Day {c['day_number']:02d}: Date {c['date']} | Chars: {len(c['text'])} | Tokens: {int(c['token_estimate'])}")

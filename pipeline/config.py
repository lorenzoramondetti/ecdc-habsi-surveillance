import os
from pathlib import Path

# Dynamic root directory (portable across any OS and machine)
BASE_DIR = os.environ.get("ECDC_BASE_DIR", str(Path(__file__).resolve().parent.parent))

# Default medical records folder, with automatic fallback to sample_data if primary is absent
PRIMARY_DATA_DIR = os.path.join(BASE_DIR, "Prime cartelle cliniche anonimizzate")
SAMPLE_DATA_DIR = os.path.join(BASE_DIR, "sample_data")

DATA_DIR = os.environ.get(
    "ECDC_DATA_DIR",
    PRIMARY_DATA_DIR if os.path.exists(PRIMARY_DATA_DIR) else SAMPLE_DATA_DIR
)

GOLD_STANDARD_PATH = os.environ.get(
    "ECDC_GOLD_STANDARD",
    os.path.join(BASE_DIR, "Etichette cartelle_validazione umana.xlsx")
)
if not os.path.exists(GOLD_STANDARD_PATH):
    sample_gold = os.path.join(SAMPLE_DATA_DIR, "sample_gold_standard.xlsx")
    if os.path.exists(sample_gold):
        GOLD_STANDARD_PATH = sample_gold

ECDC_RULES_PATH = os.path.join(BASE_DIR, "Classificazione_BSI_ECDC.txt")
DATA_EXTRACTION_SPECS_PATH = os.path.join(BASE_DIR, "llm-data-extraction v1.3.xlsx")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CHUNKS_DIR = os.path.join(OUTPUT_DIR, "chunks")
EXTRACTIONS_DIR = os.path.join(OUTPUT_DIR, "extractions")
TABLES_DIR = os.path.join(OUTPUT_DIR, "tables")
REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")
BENCHMARK_DIR = os.path.join(OUTPUT_DIR, "benchmark")
TESSY_DIR = os.path.join(OUTPUT_DIR, "tessy_export")

for d in [OUTPUT_DIR, CHUNKS_DIR, EXTRACTIONS_DIR, TABLES_DIR, REPORTS_DIR, BENCHMARK_DIR, TESSY_DIR]:
    os.makedirs(d, exist_ok=True)

OLLAMA_URL = "http://127.0.0.1:11434"

# Default primary model
DEFAULT_MODEL = "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest"

# Models available locally in Ollama
AVAILABLE_MODELS = [
    "hf.co/Bucoid/Qwen3.8-27B-Uncensored-IQ4-XS-MTP-16GB-VRAM-GGUF:latest",
    "glm-4.7-flash:latest",
    "gemma4:12b",
    "gemma4:e4b"
]

BENCHMARK_MODELS = AVAILABLE_MODELS

# Context window: 8192 prevents any exceed_context_size_error
OLLAMA_NUM_CTX = 8192
# Generation limit: 3500 ensures thinking models have enough budget to emit the full JSON
OLLAMA_NUM_PREDICT = 3500
OLLAMA_KEEP_ALIVE = "5m"

# Human manual surveillance baseline (minutes per medical record)
DEFAULT_HUMAN_TIME_MINUTES = 20.0

# ECDC skin contaminants list
SKIN_CONTAMINANTS = [
    "coagulase-negative staphylococci",
    "coagulase negative staphylococci",
    "coagulase-negative staphylococcus",
    "staphylococcus coagulasi negativo",
    "stafilococco coagulasi negativo",
    "stafilococco coagulasi-negativo",
    "stafilococchi coagulasi negativi",
    "staphylococcus epidermidis",
    "s. epidermidis",
    "s.epidermidis",
    "staphylococcus hominis",
    "s. hominis",
    "s.hominis",
    "staphylococcus haemolyticus",
    "s. haemolyticus",
    "staphylococcus capitis",
    "s. capitis",
    "staphylococcus warneri",
    "s. warneri",
    "staphylococcus lugdunensis",
    "s. lugdunensis",
    "staphylococcus saprophyticus",
    "s. saprophyticus",
    "cns",
    "scns",
    "micrococcus",
    "micrococcus sp.",
    "micrococcus spp.",
    "propionibacterium acnes",
    "cutibacterium acnes",
    "propionibacterium",
    "cutibacterium",
    "bacillus",
    "bacillus sp.",
    "bacillus spp.",
    "corynebacterium",
    "corynebacterium sp.",
    "corynebacterium spp."
]


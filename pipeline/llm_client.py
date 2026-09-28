import os
import json
import time
import re
from typing import Dict, Any, Optional
import requests
from pipeline.config import (
    OLLAMA_URL, DEFAULT_MODEL, EXTRACTIONS_DIR,
    OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_KEEP_ALIVE
)
from pipeline.prompt_templates import SYSTEM_PROMPT, create_extraction_prompt

class OllamaClient:
    """Client for querying local LLMs through Ollama with structured JSON outputs and caching.
    Uses assistant prefill to bypass reasoning loops and guarantee fast, valid JSON output.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, base_url: str = OLLAMA_URL):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.clean_model_name = self._sanitize_model_name(model_name)

    def _sanitize_model_name(self, name: str) -> str:
        s = name.replace("hf.co/", "").replace(":", "_").replace("/", "_")
        return re.sub(r"[^a-zA-Z0-9_\.-]", "_", s)

    def unload_model(self):
        """Forces Ollama to release VRAM by setting keep_alive to 0."""
        try:
            requests.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model_name, "messages": [], "keep_alive": 0},
                timeout=10
            )
        except Exception:
            pass

    def extract_from_chunk(self, chunk: Dict[str, Any], force_recompute: bool = False) -> Dict[str, Any]:
        patient_id = chunk["patient_id"]
        day_num = chunk["day_number"]
        date_clean = chunk["date"].replace("/", "-")

        cache_dir = os.path.join(EXTRACTIONS_DIR, self.clean_model_name, f"Paziente_{patient_id}")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"extraction_day_{day_num:02d}_{date_clean}.json")

        # Only use cache if it exists and contains NO errors
        if not force_recompute and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    ent = cached_data.get("entities", {})
                    if "error" not in ent and isinstance(ent, dict) and len(ent) > 0:
                        return cached_data
            except Exception:
                pass

        # Fallback: check if extraction exists for the exact calendar date under a previous day number
        if not force_recompute and os.path.exists(cache_dir):
            try:
                matching_files = [f for f in os.listdir(cache_dir) if f.endswith(f"_{date_clean}.json")]
                if matching_files:
                    alt_file = os.path.join(cache_dir, matching_files[0])
                    with open(alt_file, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                        ent = cached_data.get("entities", {})
                        if "error" not in ent and isinstance(ent, dict) and len(ent) > 0:
                            cached_data["day_number"] = day_num
                            # Save with the corrected day_num name as well
                            with open(cache_file, "w", encoding="utf-8") as out_f:
                                json.dump(cached_data, out_f, indent=2, ensure_ascii=False)
                            return cached_data
            except Exception:
                pass

        user_prompt = create_extraction_prompt(
            chunk_text=chunk["text"],
            patient_id=patient_id,
            date_str=chunk["date"],
            day_number=day_num
        )

        # Pre-filling the assistant response with "{" bypasses infinite thinking loops in Qwen and Gemma
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "{"}
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "format": "json",
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 42,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": OLLAMA_NUM_PREDICT
            }
        }

        t_start = time.time()
        raw_content = ""
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=600)
            resp.raise_for_status()
            res_json = resp.json()
            raw_content = res_json.get("message", {}).get("content", "")
            
            # Since we prefilled "{", ensure the content starts with "{" if omitted
            if raw_content and not raw_content.strip().startswith("{"):
                raw_content = "{\n" + raw_content.strip()

            if not raw_content or not raw_content.strip():
                # Fallback: check if model emitted thinking containing JSON
                th = res_json.get("message", {}).get("thinking", "")
                m = re.search(r"(\{[\s\S]*\})", th)
                if m:
                    raw_content = m.group(1)
                else:
                    raw_content = json.dumps({"error": "Empty model output", "res_json": str(res_json)[:200]})
        except Exception as e:
            raw_content = json.dumps({"error": str(e)})

        latency = time.time() - t_start

        # Clean markdown wrappers if present
        clean_content = raw_content.strip()
        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
            clean_content = re.sub(r"\s*```$", "", clean_content)

        try:
            parsed_entities = json.loads(clean_content)
        except Exception:
            match = re.search(r"(\{[\s\S]*\})", clean_content)
            if match:
                try:
                    parsed_entities = json.loads(match.group(1))
                except Exception as e:
                    parsed_entities = {"error": f"JSON parse error: {str(e)}", "raw_content": clean_content[:300]}
            else:
                parsed_entities = {"error": "No JSON found in response", "raw_content": clean_content[:300]}

        extraction_result = {
            "patient_id": patient_id,
            "date": chunk["date"],
            "day_number": day_num,
            "model": self.model_name,
            "latency_seconds": round(latency, 2),
            "entities": parsed_entities
        }

        # Cache on disk only if extraction succeeded without error
        if "error" not in parsed_entities:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(extraction_result, f, indent=2, ensure_ascii=False)

        return extraction_result

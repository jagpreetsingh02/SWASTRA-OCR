"""Model-selection probe: a small local generative LLM extracting JSON from GROUND-TRUTH text.

    .venv/bin/python eval/llm_extraction_probe.py Qwen/Qwen3-VL-2B-Instruct

Every extracted string is checked against the source text; anything not found verbatim
(case/whitespace-insensitive) is reported as UNGROUNDED -- that is a fabrication.
"""

import json
import re
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForImageTextToText, AutoModelForCausalLM, AutoProcessor, AutoTokenizer

DOCS = Path(__file__).resolve().parents[1] / "dev"
CONTROL = "The quarterly shipping manifest lists 40 crates of ceramic tiles delivered to Pune on Tuesday."
EXTRA = ("Patient: Anita Rao. c/o fever and dry cough for 3 days, body ache. Known allergy to penicillin. "
         "Adv: CBC, CRP. Syp. Ascoril 5ml TDS x 5 days.")

INSTRUCTION = """Extract medical information from the document text below. Copy values EXACTLY as they appear in the text (same spelling, abbreviations and units). Never expand abbreviations, never correct spelling, never guess. If something is not in the text, use null or [].

Return only JSON with this shape:
{"patient_name": str|null, "doctor_name": str|null, "date": str|null,
 "medications": [{"name": str, "dosage": str|null, "frequency": str|null, "duration": str|null}],
 "diagnoses": [str], "symptoms": [str], "allergies": [str],
 "tests": [{"name": str, "value": str|null, "unit": str|null, "reference_range": str|null}]}

Document text:
"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


model_id = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3-VL-2B-Instruct"
device = "mps" if torch.backends.mps.is_available() else "cpu"
t = time.time()
if "VL" in model_id:
    tok = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16).to(device).eval()
else:
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.bfloat16).to(device).eval()
print(f"loaded {model_id} in {time.time() - t:.1f}s on {device}")

texts = {p.stem: p.read_text() for p in sorted(DOCS.glob("*.txt"))}
texts["control_non_medical"] = CONTROL
texts["extra_symptoms_allergy"] = EXTRA
for name, text in texts.items():
    messages = [{"role": "user", "content": [{"type": "text", "text": INSTRUCTION + text}]}]
    if "VL" not in model_id:
        messages = [{"role": "user", "content": INSTRUCTION + text}]
    kwargs = {} if "VL" in model_id else {"enable_thinking": False}
    inputs = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                                     return_tensors="pt", **kwargs).to(device)
    t = time.time()
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=700, do_sample=False)
    raw = tok.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
    secs = time.time() - t
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        data = None
    print(f"\n== {name} ({secs:.1f}s)")
    if data is None:
        print("  INVALID JSON:", raw[:400])
        continue
    print("  " + json.dumps(data, ensure_ascii=False))
    ungrounded = [s for s in strings(data) if s and norm(s) not in norm(text)]
    print("  UNGROUNDED:", ungrounded)

"""Model-selection probe for the extraction stage, run on GROUND-TRUTH text (OCR errors excluded).

    .venv/bin/python eval/extraction_candidates.py Ihor/gliner-biomed-base-v1.0

Prints every span the model finds per label so a person can judge it, plus a no-medical-content
control that should come back (nearly) empty.
"""

import sys
import time
from pathlib import Path

from gliner import GLiNER

DOCS = Path(__file__).resolve().parents[1] / "dev"
LABELS = ["Drug", "Drug dosage", "Drug frequency", "Drug duration", "Disease", "Symptom", "Lab test",
          "Lab test value", "Allergy", "Patient name", "Doctor name", "Date"]
CONTROL = "The quarterly shipping manifest lists 40 crates of ceramic tiles delivered to Pune on Tuesday."
EXTRA = ("Patient: Anita Rao. c/o fever and dry cough for 3 days, body ache. Known allergy to penicillin. "
         "Adv: CBC, CRP. Syp. Ascoril 5ml TDS x 5 days.")

model_id = sys.argv[1] if len(sys.argv) > 1 else "Ihor/gliner-biomed-base-v1.0"
threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
t = time.time()
model = GLiNER.from_pretrained(model_id)
print(f"loaded {model_id} in {time.time() - t:.1f}s, threshold={threshold}")

texts = {p.stem: p.read_text() for p in sorted(DOCS.glob("*.txt"))}
texts["control_non_medical"] = CONTROL
texts["extra_symptoms_allergy"] = EXTRA
for name, text in texts.items():
    t = time.time()
    ents = model.predict_entities(text, LABELS, threshold=threshold, flat_ner=True)
    print(f"\n== {name}  ({time.time() - t:.2f}s)")
    for e in ents:
        print(f"  {e['label']:16s} {e['score']:.2f}  {e['text']!r}")

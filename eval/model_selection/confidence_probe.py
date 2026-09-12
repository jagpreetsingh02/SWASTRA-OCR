"""What exactly is the per-character confidence, and why does it miss HbA1c -> HbAlc? DEV pages only.

    .venv/bin/python eval/model_selection/confidence_probe.py

Checks three things and writes eval/model_selection/reports/confidence_probe.json:

1. the recorded probability really is the emitted token's probability (emitted token == argmax of the
   scores the recorder sees, at every step);
2. what the model's alternatives were where it misread (HbA1c -> HbAlc, Augmtin -> Augmentin);
3. whether resolution is the cause (full resolution and a single-line crop are compared).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch
from transformers import LogitsProcessor, LogitsProcessorList

EVAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL))
from medikiosk_ocr import ocr  # noqa: E402
from medikiosk_ocr.preprocess import load_document  # noqa: E402

DEV = EVAL / "dev"


def generate_with_alternatives(image, fit: bool = True, top: int = 4):
    model, processor = ocr.load()
    image = ocr._fit(image) if fit else image
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": ocr.PROMPT}]}]
    inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                                           return_tensors="pt").to(model.device)
    steps = []

    class Record(LogitsProcessor):
        def __call__(self, input_ids, scores):
            probabilities = torch.softmax(scores[0].float(), -1)
            best = torch.topk(probabilities, top)
            steps.append([(int(i), float(v)) for v, i in zip(best.values, best.indices)])
            return scores

    started = time.perf_counter()
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=ocr.MAX_NEW_TOKENS, do_sample=False, temperature=None,
                             top_p=None, top_k=None, logits_processor=LogitsProcessorList([Record()]))
    ids = out[0, inputs["input_ids"].shape[-1]:].tolist()
    return {
        "ids": ids, "steps": steps, "seconds": round(time.perf_counter() - started, 1), "size": image.size,
        "text": processor.tokenizer.decode(ids, skip_special_tokens=True),
        "greedy_token_is_argmax_at_every_step": all(steps[i][0][0] == ids[i] for i in range(len(ids))),
    }


def around(run: dict, needle: str, width: int = 8) -> list[dict]:
    _, processor = ocr.load()
    pieces = [processor.tokenizer.decode([i]) for i in run["ids"]]
    at = "".join(pieces).find(needle)
    out, position = [], 0
    for index, piece in enumerate(pieces):
        if at >= 0 and position + len(piece) > at - 2 and position < at + width:
            out.append({"token": piece, "p": round(run["steps"][index][0][1], 4),
                        "alternatives": [(processor.tokenizer.decode([i]), round(v, 4)) for i, v in run["steps"][index][1:]]})
        position += len(piece)
    return out


def main() -> None:
    report = {}
    lab = load_document((DEV / "lab_report_scan.png").read_bytes())[0].image
    production = generate_with_alternatives(lab)
    report["lab_production_resolution"] = {
        "size": production["size"], "seconds": production["seconds"],
        "greedy_token_is_argmax_at_every_step": production["greedy_token_is_argmax_at_every_step"],
        "line": next((l for l in production["text"].splitlines() if "Hb" in l), None),
        "tokens": around(production, "HbA"),
    }
    full = generate_with_alternatives(lab, fit=False)
    report["lab_full_resolution"] = {"size": full["size"], "seconds": full["seconds"],
                                     "line": next((l for l in full["text"].splitlines() if "Hb" in l), None),
                                     "tokens": around(full, "HbA")}
    crop = generate_with_alternatives(lab.crop((60, 230, 1240, 300)))
    report["lab_single_line_crop"] = {"size": crop["size"], "text": crop["text"], "tokens": around(crop, "HbA")}

    handwritten = generate_with_alternatives(load_document((DEV / "prescription_handwritten.png").read_bytes())[0].image)
    report["handwritten"] = {"greedy_token_is_argmax_at_every_step": handwritten["greedy_token_is_argmax_at_every_step"],
                             "line": next((l for l in handwritten["text"].splitlines() if "625" in l), None),
                             "tokens": around(handwritten, "Aug")}

    page = ocr.read_page(lab)  # the production path, for the record
    index = page.text.find("HbA")
    report["production_read_page"] = {
        "characters": [(c, round(p, 4)) for c, p in zip(page.text[index:index + 6], page.char_confidence[index:index + 6])],
        "document_mean": round(sum(page.char_confidence) / len(page.char_confidence), 4),
    }
    out = EVAL / "model_selection" / "reports" / "confidence_probe.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1)[:4000])
    print("wrote", out)


if __name__ == "__main__":
    main()

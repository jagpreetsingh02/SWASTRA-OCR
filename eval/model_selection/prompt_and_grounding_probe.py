"""Two OCR questions, answered on DEV pages only (never held-out):

1. Grounding: can Qwen3-VL-2B return a bounding box per line reliably enough to check each OCR
   line against the ink on the page (an invented line would sit on blank paper)?
2. Language prior: does a stricter prompt stop "corrections" like Augmtin -> Augmentin without
   hurting everything else?

    .venv/bin/python eval/model_selection/prompt_and_grounding_probe.py

Writes eval/model_selection/reports/prompt_and_grounding_probe.json.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import torch

EVAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL))
import metrics  # noqa: E402
from medikiosk_ocr import ocr  # noqa: E402
from medikiosk_ocr.preprocess import load_document  # noqa: E402

DEV = EVAL / "dev"
PAGES = {
    "prescription_scan.png": "prescription", "prescription_degraded.png": "prescription",
    "prescription_photo_handheld.jpg": "prescription", "lab_report_scan.png": "lab_report",
    "lab_report_degraded.png": "lab_report", "discharge_scan.png": "discharge", "discharge_degraded.png": "discharge",
    "prescription_handwritten.png": "prescription_handwritten", "hw_rx_bradley.png": "hw_rx_bradley",
    "hw_rx_brush_hard.png": "hw_rx_brush_hard", "hw_rx_chalkboard.png": "hw_rx_chalkboard",
    "hw_rx_cursive.png": "hw_rx_cursive", "mixed_printed_handwritten.png": "mixed_printed_handwritten",
}
PROMPTS = {
    "production": ocr.PROMPT,
    "literal": ("Transcribe all text in this image exactly as written, line by line. Copy every character as it "
                "appears, even when a word looks misspelled or unusual: do not replace it with a real word you know. "
                "Keep abbreviations, numbers and units exactly. Do not correct, expand, translate or add anything. "
                "If there is no readable text, output nothing."),
    "ocr_engine": ("You are an OCR engine, not an editor. Output the exact characters visible in the image, one line of "
                   "the page per line of output. Misspellings and unfamiliar words must be copied letter by letter. "
                   "Output nothing else."),
}
GROUNDING_PROMPT = ('Read every line of text in the image. Return only a JSON list, one item per line, in reading order: '
                    '[{"bbox_2d": [x1, y1, x2, y2], "text": "the line copied exactly"}]. Do not correct or add anything.')


def generate(image, prompt, max_new_tokens=1536):
    model, processor = ocr.load()
    image = ocr._fit(image)
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                                           return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None, top_k=None)
    return processor.decode(out[0, inputs["input_ids"].shape[-1]:], skip_special_tokens=True), image.size


def main() -> None:
    report = {"prompts": {}, "grounding": {}}
    for label, prompt in PROMPTS.items():
        rows, found, expected, subs, seconds = {}, 0, 0, 0, 0.0
        for name, stem in PAGES.items():
            image = load_document((DEV / name).read_bytes())[0].image
            start = time.perf_counter()
            text, _ = generate(image, prompt)
            elapsed = time.perf_counter() - start
            score = metrics.score_ocr(text, metrics.load_truth(DEV / f"{stem}.truth.json"), (DEV / f"{stem}.txt").read_text())
            replaced = [s for s in score["substitutions"] if s["op"] == "replace"]
            rows[name] = {"seconds": round(elapsed, 1), "critical": score["critical_total"], "cer": score["cer"],
                          "missing": score["missing"], "substitutions": replaced}
            found += score["critical_total"]["found"]
            expected += score["critical_total"]["expected"]
            subs += len(replaced)
            seconds += elapsed
            print(f"{label:11s} {name:34s} critical={score['critical_total']['found']}/{score['critical_total']['expected']} "
                  f"cer={score['cer']} subs={[(s['written'], s['read']) for s in replaced]} {elapsed:.1f}s", flush=True)
        report["prompts"][label] = {"critical_accuracy": round(found / expected, 3), "substitutions": subs,
                                    "seconds": round(seconds, 1), "pages": rows}
        print(f"== {label}: critical {found}/{expected} substitutions {subs} total {seconds:.0f}s", flush=True)

    for name in ("prescription_scan.png", "prescription_handwritten.png", "hw_rx_bradley.png", "lab_report_scan.png"):
        image = load_document((DEV / name).read_bytes())[0].image
        start = time.perf_counter()
        raw, size = generate(image, GROUNDING_PROMPT, max_new_tokens=2048)
        elapsed = time.perf_counter() - start
        match = re.search(r"\[.*\]", raw, re.S)
        try:
            items = json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            items = None
        report["grounding"][name] = {"seconds": round(elapsed, 1), "parsed": items is not None,
                                     "lines": len(items) if items else 0, "raw": raw[:3000], "image_size": size}
        print(f"grounding {name:34s} parsed={items is not None} lines={len(items) if items else 0} {elapsed:.1f}s", flush=True)
        if items:
            for item in items[:14]:
                print("    ", item, flush=True)
    out = EVAL / "model_selection" / "reports" / "prompt_and_grounding_probe.json"
    out.write_text(json.dumps(report, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()

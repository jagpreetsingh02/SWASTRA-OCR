"""Where do time and memory go? Profiles the real pipeline on dev documents.

    .venv/bin/python eval/tools/profile_pipeline.py --label after [--repeat 10]

Reports model cold-load time, per-stage time for each document, and process/MPS memory after
every request (including N repeats of the same page, to expose growth). Writes
eval/reports/profile_<label>.json.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import torch

from medikiosk_ocr import extract, ocr, pipeline

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "eval" / "dev"
FILES = ["prescription_scan.png", "prescription_photo_handheld.jpg", "lab_report_scan.png",
         "prescription_handwritten.png", "hw_rx_bradley.png", "prescription.pdf"]
STAGES: dict[str, float] = {}


def timed(label, fn):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            STAGES[label] = STAGES.get(label, 0.0) + time.perf_counter() - start
    return wrapper


def patch(module, attr, label):
    if hasattr(module, attr):
        setattr(module, attr, timed(label, getattr(module, attr)))


def memory() -> dict:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    out = {"max_rss_mb": round(rss / 2**20 if sys.platform == "darwin" else rss / 2**10, 1)}
    if torch.backends.mps.is_available():
        out["mps_allocated_mb"] = round(torch.mps.current_allocated_memory() / 2**20, 1)
        out["mps_driver_mb"] = round(torch.mps.driver_allocated_memory() / 2**20, 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--repeat", type=int, default=10)
    args = parser.parse_args()

    report = {"label": args.label, "memory_start": memory()}
    start = time.perf_counter()
    model, processor = ocr.load()
    report["cold_load_ocr_s"] = round(time.perf_counter() - start, 1)
    start = time.perf_counter()
    extract._ner()
    report["cold_load_extractor_s"] = round(time.perf_counter() - start, 1)
    report["memory_after_load"] = memory()

    model.generate = timed("ocr.generate", model.generate)
    processor.apply_chat_template = timed("ocr.image_processing+template", processor.apply_chat_template)
    patch(ocr, "_characters_with_confidence", "ocr.char_confidence_mapping")
    for module in (pipeline,):
        patch(module, "load_document", "preprocess.load_document")
        patch(module, "is_blank", "preprocess.is_blank")
        patch(module, "estimate_text_lines", "validate.estimate_text_lines")
    try:
        from medikiosk_ocr import validate
        for name in ("check_page_text", "flag_entities"):
            patch(validate, name, f"validate.{name}")
    except ImportError:
        pass
    patch(extract, "_ner_spans", "extract.gliner")

    rows = []
    for name in FILES + [FILES[0]] * args.repeat:
        STAGES.clear()
        start = time.perf_counter()
        result = pipeline.extract_document((DEV / name).read_bytes())
        total = time.perf_counter() - start
        rows.append({"file": name, "status": result.status.value, "total_s": round(total, 2),
                     "stages_s": {k: round(v, 3) for k, v in sorted(STAGES.items())}, "memory": memory()})
        print(f"{name:34s} {total:6.2f}s {json.dumps(rows[-1]['stages_s'])} {rows[-1]['memory']}", flush=True)
    report["requests"] = rows
    out = ROOT / "eval" / "reports" / f"profile_{args.label}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()

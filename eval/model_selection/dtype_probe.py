"""Is float16 faster than bfloat16 for Qwen3-VL-2B on this GPU, with identical output? DEV pages only.

    .venv/bin/python eval/model_selection/dtype_probe.py

Each dtype runs in its own process (one model in memory at a time). Writes
eval/model_selection/reports/dtype_probe.json. The production dtype changes only if the text is
identical on every page and the speed-up is material.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1]
DEV = EVAL / "dev"
PAGES = ["prescription_scan.png", "lab_report_scan.png", "prescription_handwritten.png", "hw_rx_bradley.png"]


def child(dtype_name: str) -> None:
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    from medikiosk_ocr import ocr
    from medikiosk_ocr.preprocess import load_document

    ocr._processor = AutoProcessor.from_pretrained(ocr.MODEL_ID)
    ocr._model = AutoModelForImageTextToText.from_pretrained(ocr.MODEL_ID, dtype=getattr(torch, dtype_name)).to(ocr._device()).eval()
    images = {p: load_document((DEV / p).read_bytes())[0].image for p in PAGES}
    ocr.read_page(images[PAGES[0]])  # warm-up (kernel compilation)
    out = {}
    for name, image in images.items():
        start = time.perf_counter()
        read = ocr.read_page(image)
        out[name] = {"seconds": round(time.perf_counter() - start, 2), "text": read.text}
    print("RESULT " + json.dumps(out))


def main() -> None:
    if len(sys.argv) > 1:
        child(sys.argv[1])
        return
    results = {}
    for dtype_name in ("bfloat16", "float16"):
        proc = subprocess.run([sys.executable, __file__, dtype_name], capture_output=True, text=True)
        line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT ")), None)
        results[dtype_name] = json.loads(line[7:]) if line else {"error": proc.stderr[-1500:]}
        print(dtype_name, {k: v.get("seconds") for k, v in results[dtype_name].items()} if line else "FAILED", flush=True)
    if all("error" not in r for r in results.values()):
        same = {p: results["bfloat16"][p]["text"] == results["float16"][p]["text"] for p in PAGES}
        speed = sum(results["bfloat16"][p]["seconds"] for p in PAGES) / sum(results["float16"][p]["seconds"] for p in PAGES)
        results["comparison"] = {"identical_text": same, "bf16_seconds_over_fp16_seconds": round(speed, 3)}
        print(json.dumps(results["comparison"]))
    (EVAL / "model_selection" / "reports" / "dtype_probe.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()

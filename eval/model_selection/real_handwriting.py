"""Which OCR model actually reads REAL doctors' handwriting?

    .venv/bin/python eval/model_selection/real_handwriting.py qwen3-vl-2b
    .venv/bin/python eval/model_selection/real_handwriting.py --list
    .venv/bin/python eval/model_selection/real_handwriting.py --compare        # table from saved runs

Model selection only. It imports nothing from `medikiosk_ocr.ocr`, so the production OCR backend is
untouched and unaffected by anything here.

What it measures, and why this file exists separately from eval/run.py:

* The subject is the OCR MODEL, not the pipeline. Each engine returns a literal transcription and is
  scored on clinical tokens straight out of that text -- GLiNER, document classification and the
  medication rules are not in the loop, so they cannot flatter or mask a model's reading.
* Scoring reuses eval/metrics.py unchanged, so matching is the same strict, count-aware, whole-token
  rule the acceptance evaluation uses: "5" never matches "500", "OD" never matches "BD".
* No autocorrection of any kind. No spellcheck, no drug dictionary, no fuzzy matching, no LLM cleanup.
  The question is what the model itself can read.
* Every engine sees the SAME 21 real_world_dev pages, the same ground truth and the same base
  preprocessing (medikiosk_ocr.preprocess.load_document), so the comparison is fair.

The 9 real_world_holdout pages are NEVER touched here; this script cannot even see them, because it
reads only files named rw_*.jpeg inside eval/real_world/.
"""

from __future__ import annotations

import argparse
import json
import re
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent
REPO = EVAL.parent
DOCS = EVAL / "real_world"
REPORTS = EVAL / "reports" / "model_selection_real_world"
sys.path.insert(0, str(EVAL))
sys.path.insert(0, str(REPO))
import metrics  # noqa: E402

# One transcription instruction, the same intent for every generative model, no drug hints of any kind.
PROMPT = ("Transcribe all text in this image exactly as written, line by line. Keep the original "
          "spelling, abbreviations, numbers and units. Do not correct, expand, translate or add anything.")


def documents() -> list[tuple[str, Path]]:
    """The 21 real_world_dev pages. Holdout pages are not in this directory and cannot be reached."""
    return [(p.stem, p) for p in sorted(DOCS.glob("rw_*.jpeg"))
            if (DOCS / f"{p.stem}.truth.json").exists()]


# ------------------------------------------------------------------------------ engines
# Each returns read(PIL.Image) -> str. One model is resident at a time; the process exits between
# engines so nothing leaks into the next measurement.

def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


def chat_vlm(model_id: str, prompt: str, *, max_pixels: int | None = None):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    device = _device()
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id, dtype=torch.float32 if device == "cpu" else torch.bfloat16).to(device).eval()

    def read(image):
        if max_pixels and image.width * image.height > max_pixels:
            scale = (max_pixels / (image.width * image.height)) ** 0.5
            image = image.resize((round(image.width * scale), round(image.height * scale)))
        messages = [{"role": "user", "content": [{"type": "image", "image": image},
                                                 {"type": "text", "text": prompt}]}]
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                               return_dict=True, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=1536, do_sample=False,
                                 temperature=None, top_p=None, top_k=None)
        text = processor.tokenizer.decode(out[0, inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        return text.strip()

    return read


def got_ocr2():
    """GOT-OCR2 uses its own OCR entry point rather than a chat template."""
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    device = _device()
    model_id = "stepfun-ai/GOT-OCR-2.0-hf"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id, dtype=torch.float32 if device == "cpu" else torch.bfloat16).to(device).eval()

    def read(image):
        inputs = processor(image, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=1536, do_sample=False,
                                 tokenizer=processor.tokenizer, stop_strings="<|im_end|>")
        return processor.decode(out[0, inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()

    return read


def production_prompt() -> str:
    """The prompt the shipped engine actually uses. Read from the production module, never modified.

    The incumbent is benchmarked twice -- once with this, once with the neutral benchmark prompt above --
    because a trivial change to the prompt tail moved which pages collapse into generation loops. Judging
    the incumbent only on a prompt it does not ship with would bias the comparison against it.
    """
    from medikiosk_ocr.ocr import PROMPT as SHIPPED

    return SHIPPED


ENGINES = {
    # id -> (factory, exact model id, licence, note, prompt)
    "qwen3-vl-2b": (lambda: chat_vlm("Qwen/Qwen3-VL-2B-Instruct", PROMPT, max_pixels=1_400_000),
                    "Qwen/Qwen3-VL-2B-Instruct", "apache-2.0", "current production model", PROMPT),
    "qwen3-vl-2b-prod": (lambda: chat_vlm("Qwen/Qwen3-VL-2B-Instruct", production_prompt(), max_pixels=1_400_000),
                         "Qwen/Qwen3-VL-2B-Instruct", "apache-2.0",
                         "current production model, with its shipped prompt", "<production prompt>"),
    "got-ocr2": (got_ocr2, "stepfun-ai/GOT-OCR-2.0-hf", "apache-2.0", "580M document OCR model",
                 "(none: GOT-OCR2 has a dedicated OCR entry point, no text prompt)"),
    "paddleocr-vl": (lambda: chat_vlm("PaddlePaddle/PaddleOCR-VL-1.6", "OCR:", max_pixels=1280 * 28 * 28),
                     "PaddlePaddle/PaddleOCR-VL-1.6", "apache-2.0", "0.9B, OCR-specialised, multilingual", "OCR:"),
    "glm-ocr": (lambda: chat_vlm("zai-org/GLM-OCR", "Text Recognition:"),
                "zai-org/GLM-OCR", "mit", "OCR-specialised GLM", "Text Recognition:"),
}


# ------------------------------------------------------------------------------ hallucination signals

REPEAT_RUN = 3               # the same LINE this many times in a row is a generation loop
LOOP_DISTINCT_RATIO = 0.35   # few distinct lines over many lines is a loop
LOOP_PERIOD_MAX = 8          # longest repeating unit looked for, e.g. "0" or "00-"
LOOP_PERIOD_CHARS = 40       # a back-to-back repeat must be at least this long to count
LOOP_PERIOD_SHARE = 0.25     # ...and must cover at least this much of the page's text


def longest_periodic_run(text: str, max_period: int = LOOP_PERIOD_MAX) -> tuple[int, str]:
    """The longest stretch built from one short unit repeated back to back.

    A line-based check cannot see a loop that carries no newlines, and GOT-OCR2 emits exactly that:
    "00000000000..." and "00- 00- 00- ..." on one unbroken line. Counting only repeated lines scored
    those pages as clean, which under-reported that model's real failure rate by four pages.

    Repetition must be CONSECUTIVE, and that is what keeps legitimate medical notation out of it: a
    prescription may carry "1+0+1" against a dozen drugs, but those occurrences are separated by drug
    names, so they never form one unbroken run.
    """
    squeezed = re.sub(r"\s+", " ", text)
    n = len(squeezed)
    best_len, best_unit = 0, ""
    for period in range(1, max_period + 1):
        i = 0
        while i + 2 * period <= n:
            unit = squeezed[i:i + period]
            if not unit.strip():
                i += 1
                continue
            j = i + period
            while j + period <= n and squeezed[j:j + period] == unit:
                j += period
            run = j - i
            if run >= 2 * period and run > best_len:
                best_len, best_unit = run, unit
            i = j if run >= 2 * period else i + 1
    return best_len, best_unit


def output_problems(text: str, hit_limit: bool) -> dict:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    distinct = len(set(lines))
    longest_run, run, previous = 0, 0, None
    for line in lines:
        run = run + 1 if line == previous else 1
        longest_run = max(longest_run, run)
        previous = line
    line_loop = bool(lines) and (longest_run >= REPEAT_RUN or
                                 (len(lines) >= 20 and distinct / len(lines) < LOOP_DISTINCT_RATIO))
    periodic_chars, periodic_unit = longest_periodic_run(text)
    squeezed = len(re.sub(r"\s+", " ", text))
    periodic_loop = (periodic_chars >= LOOP_PERIOD_CHARS
                     and periodic_chars >= LOOP_PERIOD_SHARE * max(squeezed, 1))
    return {"lines": len(lines), "distinct_lines": distinct, "longest_repeat_run": longest_run,
            "line_loop": line_loop, "periodic_loop": periodic_loop,
            "periodic_run_chars": periodic_chars, "periodic_unit": periodic_unit[:12],
            "generation_loop": line_loop or periodic_loop,
            "empty_output": not lines, "hit_token_limit": hit_limit,
            "cjk_characters": sum(1 for ch in text if "一" <= ch <= "鿿"),
            "bangla_characters": sum(1 for ch in text if "ঀ" <= ch <= "৿")}


def memory_mb() -> dict:
    import torch

    out = {"max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 1)}
    if torch.backends.mps.is_available():
        out["mps_allocated_mb"] = round(torch.mps.current_allocated_memory() / 2**20, 1)
        out["mps_driver_mb"] = round(torch.mps.driver_allocated_memory() / 2**20, 1)
    return out


# ------------------------------------------------------------------------------ run

def run(name: str) -> dict:
    from medikiosk_ocr.preprocess import load_document

    factory, model_id, licence, note, prompt = ENGINES[name]
    print(f"== {name}  ({model_id}, {licence})", flush=True)
    started = time.perf_counter()
    read = factory()
    load_s = round(time.perf_counter() - started, 1)
    after_load = memory_mb()
    print(f"   cold load {load_s}s  {after_load}", flush=True)

    rows = []
    for stem, path in documents():
        truth = metrics.load_truth(DOCS / f"{stem}.truth.json")
        image = load_document(path.read_bytes())[0].image      # identical preprocessing for every engine
        t = time.perf_counter()
        try:
            text = read(image)
            error = None
        except Exception as exc:                                # a model that cannot read a page is a result
            text, error = "", f"{type(exc).__name__}: {exc}"[:300]
        seconds = round(time.perf_counter() - t, 2)
        scored = metrics.score_ocr(text, truth, None)           # no transcription: critical tokens only
        problems = output_problems(text, hit_limit=len(text) > 4000)
        rows.append({"document": stem, "seconds": seconds, "error": error, "text": text,
                     "critical": scored["critical_total"], "by_category": scored["critical_by_category"],
                     "missing": scored["missing"], **problems})
        found, expected = scored["critical_total"]["found"], scored["critical_total"]["expected"]
        print("   %-8s %6.2fs  critical %2d/%-2d  lines=%-4d distinct=%-4d %s%s"
              % (stem, seconds, found, expected, problems["lines"], problems["distinct_lines"],
                 "LOOP " if problems["generation_loop"] else "", error or ""), flush=True)

    by_cat: dict[str, dict] = {}
    for r in rows:
        for cat, c in r["by_category"].items():
            agg = by_cat.setdefault(cat, {"expected": 0, "found": 0})
            agg["expected"] += c["expected"]
            agg["found"] += c["found"]
    for c in by_cat.values():
        c["accuracy"] = round(c["found"] / c["expected"], 3) if c["expected"] else None
    expected = sum(c["expected"] for c in by_cat.values())
    found = sum(c["found"] for c in by_cat.values())

    report = {
        "engine": name, "model_id": model_id, "licence": licence, "note": note,
        "prompt": production_prompt() if name == "qwen3-vl-2b-prod" else prompt,
        "device": _device(), "documents": len(rows),
        "cold_load_s": load_s, "memory_after_load": after_load, "memory_end": memory_mb(),
        "mean_seconds_per_page": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 2),
        "critical_total": {"expected": expected, "found": found,
                           "accuracy": round(found / expected, 3) if expected else None},
        "critical_by_category": by_cat,
        "generation_loops": sum(r["generation_loop"] for r in rows),
        "empty_outputs": sum(r["empty_output"] for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "pages_with_cjk": sum(r["cjk_characters"] > 0 for r in rows),
        "pages_with_bangla": sum(r["bangla_characters"] > 0 for r in rows),
        "documents_detail": rows,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(report, indent=1) + "\n")
    print("   critical-token accuracy %s | loops %d | mean %.2fs/page -> %s"
          % (report["critical_total"]["accuracy"], report["generation_loops"],
             report["mean_seconds_per_page"], REPORTS / f"{name}.json"), flush=True)
    return report


def compare() -> None:
    files = sorted(REPORTS.glob("*.json"))
    if not files:
        print("no runs yet")
        return
    loaded = [json.loads(f.read_text()) for f in files
              if f.name not in ("summary.json", "dangerous_errors.json", "pipeline.json")]
    # A model that died mid-benchmark has no critical_total. It is listed, never silently skipped:
    # leaving it out of the table would read as "never tried" instead of "tried and unusable here".
    reports = [r for r in loaded if not str(r.get("status", "")).startswith("INCOMPLETE")]
    for r in loaded:
        if str(r.get("status", "")).startswith("INCOMPLETE"):
            print("  !! %-14s %s -- completed %s/%s pages, %s s/page"
                  % (r["engine"], r["status"], r.get("documents_completed"),
                     r.get("documents_attempted"), r.get("mean_seconds_per_page_partial")))
    if not reports:
        print("no completed runs yet")
        return
    cats = ["medicine_name", "dosage", "frequency", "duration", "date"]
    print("%-14s %-9s %s  %7s %6s %6s %7s" % ("engine", "critical", "".join("%12s" % c for c in cats),
                                              "loops", "empty", "s/page", "coldload"))
    for r in sorted(reports, key=lambda r: -(r["critical_total"]["accuracy"] or 0)):
        cells = ""
        for c in cats:
            got = r["critical_by_category"].get(c)
            cells += "%12s" % (f"{got['found']}/{got['expected']}" if got else "-")
        print("%-14s %-9s %s  %7d %6d %6.2f %7.1f"
              % (r["engine"], r["critical_total"]["accuracy"], cells, r["generation_loops"],
                 r["empty_outputs"], r["mean_seconds_per_page"], r["cold_load_s"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", nargs="?", choices=sorted(ENGINES))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    if args.list:
        for name, (_, mid, lic, note, _prompt) in ENGINES.items():
            print("  %-18s %-34s %-11s %s" % (name, mid, lic, note))
        print("\n  documents: %d real_world_dev pages" % len(documents()))
        return
    if args.compare:
        compare()
        return
    if not args.engine:
        parser.error("give an engine name, --list or --compare")
    run(args.engine)


if __name__ == "__main__":
    main()

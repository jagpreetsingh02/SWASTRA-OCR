"""Model-selection benchmark: which OCR engine actually reads OUR documents?

Not part of the pipeline and not the acceptance evaluation (that is eval/run.py). Kept so the
model choice is reproducible and can be re-run when a new candidate appears.

    .venv/bin/python eval/model_selection/ocr_candidates.py tesseract
    .venv/bin/python eval/model_selection/ocr_candidates.py --all
    .venv/bin/python eval/model_selection/ocr_candidates.py --rescore   # recompute metrics from saved outputs

Each engine runs in its own process (one model in memory at a time). Per image it stores the raw
output, CER against the transcription, and critical-token accuracy computed with the same strict,
count-aware matching as eval/run.py (eval/metrics.py). Non-documents (white page, noise, and the
photos in eval/controls) record how much text an engine invents where there is none.
Note: the Qwen prompt here is the benchmark prompt, not the production prompt in medikiosk_ocr/ocr.py.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent
DOCS = EVAL / "dev"
CONTROLS = EVAL / "controls"
REPORTS = ROOT / "reports"
sys.path.insert(0, str(EVAL))
import metrics  # noqa: E402

# image -> truth stem (transcription is <stem>.txt, truth is <stem>.truth.json)
CASES = {
    "prescription_scan.png": "prescription",
    "prescription_degraded.png": "prescription",
    "prescription_photo_handheld.jpg": "prescription",
    "lab_report_scan.png": "lab_report",
    "lab_report_degraded.png": "lab_report",
    "discharge_scan.png": "discharge",
    "discharge_degraded.png": "discharge",
    "prescription_handwritten.png": "prescription_handwritten",
    "hw_rx_bradley.png": "hw_rx_bradley",
    "hw_rx_brush_hard.png": "hw_rx_brush_hard",
    "hw_rx_chalkboard.png": "hw_rx_chalkboard",
    "hw_rx_cursive.png": "hw_rx_cursive",
    "mixed_printed_handwritten.png": "mixed_printed_handwritten",
}

PROMPT = "Transcribe all text in this image exactly as written, line by line. Output only the text."


# ------------------------------------------------------------------------------ engines

def tesseract_engine():
    def read(img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "4"], input=buf.getvalue(), capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.decode(errors="replace")[:300])
        return out.stdout.decode(errors="replace")
    return read


def _device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def chat_vlm_engine(model_id: str, prompt: str, *, max_pixels: int | None = None):
    """Any image-text-to-text model that speaks the chat template (Qwen-VL, PaddleOCR-VL, GLM-OCR)."""
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16).to(_device()).eval()

    def read(img: Image.Image) -> str:
        if max_pixels and img.width * img.height > max_pixels:
            s = (max_pixels / (img.width * img.height)) ** 0.5
            img = img.resize((int(img.width * s), int(img.height * s)))
        messages = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                               return_dict=True, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        return processor.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
    return read


def got_engine():
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    mid = "stepfun-ai/GOT-OCR-2.0-hf"
    processor = AutoProcessor.from_pretrained(mid)
    model = AutoModelForImageTextToText.from_pretrained(mid, dtype=torch.bfloat16).to(_device()).eval()

    def read(img: Image.Image) -> str:
        inputs = processor(img, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, do_sample=False, tokenizer=processor.tokenizer,
                                 stop_strings="<|im_end|>", max_new_tokens=1024)
        return processor.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return read


def khedim_engine():
    """The handwritten-prescription TrOCR that MediKiosk used before. Line-level model (gated repo)."""
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    mid = "khedim/Medical-Prescription-OCR"
    processor = TrOCRProcessor.from_pretrained(mid)
    model = VisionEncoderDecoderModel.from_pretrained(mid).to(_device()).eval()

    def read(img: Image.Image) -> str:
        pv = processor(images=img.convert("RGB"), return_tensors="pt").pixel_values.to(model.device)
        with torch.inference_mode():
            out = model.generate(pv, max_new_tokens=64)
        return processor.batch_decode(out, skip_special_tokens=True)[0]
    return read


ENGINES = {
    "tesseract": tesseract_engine,
    "got-ocr2": got_engine,
    "khedim-trocr": khedim_engine,
    "paddleocr-vl": lambda: chat_vlm_engine("PaddlePaddle/PaddleOCR-VL-1.6", "OCR:", max_pixels=1280 * 28 * 28),
    "glm-ocr": lambda: chat_vlm_engine("zai-org/GLM-OCR", "Text Recognition:"),
    "qwen3-vl-2b": lambda: chat_vlm_engine("Qwen/Qwen3-VL-2B-Instruct", PROMPT, max_pixels=1_400_000),
}


# ------------------------------------------------------------------------------ run

def handwritten_line_crops() -> list[tuple[str, Image.Image]]:
    """Single-line crops, so line-level models (TrOCR) get a fair chance."""
    img = Image.open(DOCS / "prescription_handwritten.png").convert("RGB")
    rows = {"Tab Augmtin 625 BD x 5d": (425, 485), "PCM 500 sos": (490, 545),
            "Pantop 40 OD bf": (550, 610), "Tab Zerodol SP BD x 3d": (610, 670)}
    return [(truth, img.crop((100, y0, 600, y1))) for truth, (y0, y1) in rows.items()]


def score_text(image_name: str, text: str) -> dict:
    stem = CASES[image_name]
    transcription = (DOCS / f"{stem}.txt").read_text()
    ocr = metrics.score_ocr(text, metrics.load_truth(DOCS / f"{stem}.truth.json"), transcription)
    return {"cer": ocr["cer"], "critical_tokens": ocr["critical_total"], "missing": ocr["missing"]}


def run(name: str) -> dict:
    t0 = time.time()
    read = ENGINES[name]()
    result = {"engine": name, "load_s": round(time.time() - t0, 1), "documents": [], "controls": {}, "line_crops": []}

    for image_name in CASES:
        img = Image.open(DOCS / image_name).convert("RGB")
        t = time.time()
        try:
            hyp, err = read(img), None
        except Exception as exc:  # record, keep going
            hyp, err = "", f"{type(exc).__name__}: {exc}"[:300]
        doc = {"image": image_name, "seconds": round(time.time() - t, 1), "error": err, "text": hyp, **score_text(image_name, hyp)}
        result["documents"].append(doc)
        print(f"{name:14s} {image_name:34s} cer={doc['cer']:<6} critical={doc['critical_tokens']} {doc['seconds']}s", flush=True)

    blank = Image.new("RGB", (1240, 1754), "white")
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (1754, 1240, 3), dtype=np.uint8))
    controls = [("blank", blank), ("noise", noise)] + [(p.stem, Image.open(p).convert("RGB")) for p in sorted(CONTROLS.glob("*.jpg"))]
    for label, img in controls:
        text = read(img)
        result["controls"][label] = {"chars": len(text.strip()), "text": text[:300]}
        print(f"{name:14s} control {label:26s} -> {len(text.strip())} chars: {text.strip()[:80]!r}", flush=True)

    for truth, crop in handwritten_line_crops():
        text = read(crop)
        result["line_crops"].append({"truth": truth, "text": text, "cer": metrics.cer(text, truth)})
        print(f"{name:14s} line {truth!r:28s} -> {text.strip()[:60]!r}", flush=True)
    return result


def rescore() -> None:
    """Recompute metrics from saved outputs and print the comparison table."""
    for path in sorted(REPORTS.glob("*.json")):
        report = json.loads(path.read_text())
        if "engine" not in report:  # other probes share this folder
            continue
        if "failed" in report:
            print(f"{report['engine']:14s} FAILED {report['failed'][:80]}")
            continue
        docs = [d for d in report["documents"] if d["image"] in CASES]
        for doc in docs:
            doc.update(score_text(doc["image"], doc["text"]))
            doc.pop("token_recall", None)  # the old presence-only metric
        report["documents"] = docs
        path.write_text(json.dumps(report, indent=1))

        def group(pred):
            rows = [d for d in docs if pred(d["image"])]
            found = sum(d["critical_tokens"]["found"] for d in rows)
            expected = sum(d["critical_tokens"]["expected"] for d in rows)
            return f"{found / expected:.2f} ({len(rows)} pages)" if rows else "      n/a"

        handwritten = lambda n: n.startswith("hw_") or n == "prescription_handwritten.png"
        printed = lambda n: not handwritten(n) and not n.startswith("mixed_")
        controls = " ".join(f"{k}={v['chars']}" for k, v in report["controls"].items())
        print(f"{report['engine']:14s} | printed {group(printed)} | handwritten {group(handwritten)} "
              f"| mixed {group(lambda n: n.startswith('mixed_'))} "
              f"| s/page {sum(d['seconds'] for d in docs) / len(docs):4.1f} | chars on non-documents: {controls}")


def main() -> None:
    if "--rescore" in sys.argv:
        rescore()
        return
    names = list(ENGINES) if "--all" in sys.argv else [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv:  # one subprocess per engine so memory is released between models
        for n in names:
            subprocess.run([sys.executable, __file__, n], check=False)
        return
    REPORTS.mkdir(parents=True, exist_ok=True)
    for n in names:
        try:
            report = run(n)
        except Exception as exc:
            report = {"engine": n, "failed": f"{type(exc).__name__}: {exc}"[:500]}
            print(f"{n}: FAILED {report['failed']}", flush=True)
        (REPORTS / f"{n}.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

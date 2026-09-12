"""The evaluation, in one command.

    .venv/bin/python eval/run.py                          # dev + heldout + real_world, text + ocr, reliability
    .venv/bin/python eval/run.py --split heldout --mode ocr
    .venv/bin/python eval/run.py --mode text               # extraction only (no OCR model needed)

Splits (see eval/README.md):
    dev         used while building and tuning -- numbers here are optimistic by construction
    heldout     frozen before the current rules were written; NEVER tune on it (MANIFEST.sha256 checked)
    real_world  real, de-identified documents; empty until someone adds consented samples

Modes:
    text        transcription (.txt) -> extraction, i.e. extraction quality with perfect OCR
    ocr         document file -> full pipeline (preprocess, OCR, validation, extraction)

Reliability (with --mode ocr/all): non-documents must come back unreadable with no entities, and the
hallucination detector is exercised by feeding each page's true text plus one invented line.

Writes eval/reports/<split>_<mode>.json, eval/reports/reliability.json and eval/reports/SUMMARY.md.
Every document is listed individually; errors that were NOT flagged needs_review are listed by name.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
REPORTS = EVAL / "reports"
sys.path.insert(0, str(EVAL))
import metrics  # noqa: E402

DOCUMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".heic", ".heif", ".pdf"}
SPLITS = ("dev", "heldout", "real_world")
INVENTED_LINES = ("Tab Warfarin 5 mg OD x 10 days", "Serum Potassium 7.9 mEq/L (3.5 - 5.1)")


# ------------------------------------------------------------------------------ discovery

def discover(split: str) -> tuple[dict[str, Path], list[tuple[Path, str]], list[str]]:
    """Truth files, (document file, truth stem) pairs, and warnings for unannotated files."""
    folder = EVAL / split
    truths = {p.name.removesuffix(".truth.json"): p for p in sorted(folder.glob("*.truth.json"))}
    documents, warnings = [], []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in DOCUMENT_EXTENSIONS:
            continue
        # <stem>.<ext> or <stem>_<variant>.<ext>; the longest matching truth stem wins
        stems = [s for s in truths if p.stem == s or p.stem.startswith(s + "_")]
        if stems:
            documents.append((p, max(stems, key=len)))
        else:
            warnings.append(f"{split}/{p.name}: no truth file, not evaluated")
    return truths, documents, warnings


def verify_heldout_manifest() -> list[str]:
    manifest = EVAL / "heldout" / "MANIFEST.sha256"
    if not manifest.exists():
        return ["heldout/MANIFEST.sha256 is missing: cannot show the held-out set is unchanged"]
    problems, listed = [], set()
    for line in manifest.read_text().splitlines():
        digest, name = line.split("  ", 1)
        listed.add(name)
        path = EVAL / "heldout" / name
        if not path.exists():
            problems.append(f"heldout/{name} is listed in the manifest but missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"heldout/{name} CHANGED since the held-out set was frozen")
    for path in (EVAL / "heldout").iterdir():
        if path.is_file() and path.name not in listed and path.name != "MANIFEST.sha256":
            problems.append(f"heldout/{path.name} was ADDED after the held-out set was frozen")
    return problems


# ------------------------------------------------------------------------------ runs

def run_split(split: str, mode: str) -> dict | None:
    from medikiosk_ocr import pipeline

    truths, documents, warnings = discover(split)
    if mode == "text":
        cases = [(EVAL / split / f"{stem}.txt", stem) for stem in truths if (EVAL / split / f"{stem}.txt").exists()]
    else:
        cases = documents
    if not cases:
        return {"split": split, "mode": mode, "documents": {}, "warnings": warnings + [f"no {mode} cases in {split}"]}

    rows = []
    for path, stem in cases:
        truth = metrics.load_truth(truths[stem])
        transcription_path = EVAL / split / f"{stem}.txt"
        transcription = transcription_path.read_text() if transcription_path.exists() else None
        started = time.perf_counter()
        row = {"file": path.name, "truth": stem}
        try:
            if mode == "text":
                result = pipeline.analyse_text(path.read_text())
            else:
                result = pipeline.extract_document(path.read_bytes())
        except Exception:  # the pipeline promises never to raise; if it does, that is a crash to report
            row.update(crashed=True, traceback=traceback.format_exc()[-1500:])
            rows.append(row)
            print(f"  {split:10s} {mode:4s} {path.name:36s} CRASH", flush=True)
            continue
        row.update(
            crashed=False,
            seconds=round(time.perf_counter() - started, 2),
            status=result.status.value,
            error=result.error.model_dump() if result.error else None,
            warnings=result.warnings,
            raw_text=result.raw_text,
            extraction=metrics.score_extraction(result, truth),
        )
        if mode == "ocr":
            row["ocr"] = metrics.score_ocr(result.raw_text, truth, transcription)
        rows.append(row)
        print("  " + one_line(split, mode, row), flush=True)

    scored = [r for r in rows if not r["crashed"]]
    summary = metrics.aggregate(scored)
    summary["documents"] = len(rows)
    summary["crashes"] = sum(r["crashed"] for r in rows)
    if mode == "ocr" and scored:
        _check_outputs_are_distinct(split, scored, summary)
        by_cat: dict[str, dict[str, int]] = {}
        for r in scored:
            for cat, c in r["ocr"]["critical_by_category"].items():
                agg = by_cat.setdefault(cat, {"expected": 0, "found": 0})
                agg["expected"] += c["expected"]
                agg["found"] += c["found"]
        for c in by_cat.values():
            c["accuracy"] = round(c["found"] / c["expected"], 3) if c["expected"] else None
        exp = sum(c["expected"] for c in by_cat.values())
        summary["ocr_critical_tokens"] = {"by_category": by_cat, "accuracy": round(sum(c["found"] for c in by_cat.values()) / exp, 3) if exp else None}
        summary["ocr_unsupported_lines"] = sum(len(r["ocr"]["unsupported_lines"]) for r in scored)
        cers = [r["ocr"]["cer"] for r in scored if r["ocr"]["cer"] is not None]
        summary["ocr_mean_cer"] = round(sum(cers) / len(cers), 4) if cers else None
        summary["mean_seconds_per_file"] = round(sum(r["seconds"] for r in scored) / len(scored), 2)
    return {"split": split, "mode": mode, "summary": summary, "documents": {r["file"]: r for r in rows}, "warnings": warnings}


def _check_outputs_are_distinct(split: str, rows: list[dict], summary: dict) -> None:
    """Every document's OCR text must be closest to ITS OWN source. A model that collapses different
    inputs into one memorised output, or repeats a previous page, fails here."""
    sources = {}
    for path in sorted((EVAL / split).glob("*.txt")):
        sources[path.stem] = path.read_text()
    mismatches = []
    for row in rows:
        if row["truth"] not in sources:
            continue
        distances = {stem: metrics.cer(row["raw_text"], text) for stem, text in sources.items()}
        own = distances.pop(row["truth"])
        closest, nearest = min(distances.items(), key=lambda kv: kv[1]) if distances else (None, None)
        row["closest_other_source"] = {"document": closest, "cer": nearest, "own_cer": own,
                                       "own_is_closest": closest is None or own < nearest}
        if not row["closest_other_source"]["own_is_closest"]:
            mismatches.append(f"{row['file']} reads closer to {closest} ({nearest}) than to its own source ({own})")
    checked = [r for r in rows if "closest_other_source" in r]
    summary["outputs_closest_to_own_source"] = f"{sum(r['closest_other_source']['own_is_closest'] for r in checked)}/{len(checked)}"
    summary["output_distinctness_problems"] = mismatches


def one_line(split: str, mode: str, row: dict) -> str:
    ex = row["extraction"]
    tp = sum(c["tp"] for c in ex["fields"].values())
    fp = sum(c["fp"] for c in ex["fields"].values())
    fn = sum(c["fn"] for c in ex["fields"].values())
    parts = [f"{split:10s} {mode:4s} {row['file']:36s} {row['status']:14s} tp={tp:3d} fp={fp:2d} fn={fn:2d}",
             f"unflagged={len(ex['unflagged_errors'])}"]
    if "ocr" in row:
        c = row["ocr"]["critical_total"]
        parts.append(f"critical={c['found']}/{c['expected']} cer={row['ocr']['cer']}")
    parts.append(f"{row['seconds']}s")
    return " ".join(parts)


def run_reliability(splits: tuple[str, ...]) -> dict:
    """Non-documents must yield nothing; the hallucination detector must catch an invented line."""
    from medikiosk_ocr import ocr, pipeline

    def png(img: Image.Image) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    controls = {p.name: p.read_bytes() for p in sorted((EVAL / "controls").glob("*")) if p.suffix.lower() in DOCUMENT_EXTENSIONS}
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (1754, 1240, 3), dtype=np.uint8))
    dust = np.full((1754, 1240, 3), 205, dtype=np.uint8)
    dust[60::100, 50::100] = 40
    dark_object = Image.new("RGB", (1240, 1754), "white")
    dark_object.paste((20, 20, 20), (300, 500, 900, 1100))
    controls.update({"white_page.png": png(Image.new("RGB", (1240, 1754), "white")), "noise.png": png(noise),
                     "dust.png": png(Image.fromarray(dust)), "dark_object.png": png(dark_object)})
    control_rows = {}
    for name, data in controls.items():
        try:
            r = pipeline.extract_document(data)
            e = r.entities
            has_entities = any([e.medications, e.diagnoses, e.symptoms, e.tests, e.test_results, e.allergies,
                                e.patient_name, e.doctor_name, e.date])
            control_rows[name] = {"status": r.status.value, "entities": has_entities, "raw_text": r.raw_text[:200],
                                  "passed": r.status.value == "unreadable" and not has_entities}
        except Exception:
            control_rows[name] = {"passed": False, "crashed": True, "traceback": traceback.format_exc()[-800:]}
        print(f"  reliability control {name:28s} {'PASS' if control_rows[name]['passed'] else 'FAIL'} {control_rows[name].get('status')}", flush=True)

    # Detector check: OCR is replaced by the page's true text (+/- one invented line). This measures the
    # validation layer, not the OCR model.
    detector_rows = {}
    real_read = ocr.read_page
    try:
        for split in (s for s in ("dev", "heldout") if s in splits):
            _, documents, _ = discover(split)
            for path, stem in documents:
                if path.suffix.lower() == ".pdf":
                    continue  # multi-page / text-layer files: the stub cannot address pages individually
                transcription_path = EVAL / split / f"{stem}.txt"
                if not transcription_path.exists():
                    continue
                truth_lines = [l for l in transcription_path.read_text().splitlines() if l.strip()]
                invented = INVENTED_LINES[len(detector_rows) % len(INVENTED_LINES)]
                injected = truth_lines[: len(truth_lines) // 2] + [invented] + truth_lines[len(truth_lines) // 2:]
                outcome = {}
                for label, lines in (("clean", truth_lines), ("injected", injected)):
                    text = "\n".join(lines)
                    ocr.read_page = lambda image, text=text: ocr.PageText(text, [0.99] * len(text), False)
                    r = pipeline.extract_document(path.read_bytes())
                    start = r.raw_text.find(invented) if label == "injected" else -1
                    invented_entities = []
                    for ent in _all_entities(r.entities):
                        if start >= 0 and start <= ent.start < start + len(invented):
                            invented_entities.append({"text": ent.text, "needs_review": ent.needs_review})
                    suspicious = [w for w in r.warnings if "invented" in w or "not supported" in w or "missing" in w]
                    outcome[label] = {"status": r.status.value, "suspicion_warnings": suspicious,
                                      "invented_line_entities": invented_entities}
                inj = outcome["injected"]
                detected = inj["status"] != "ok" and (bool(inj["suspicion_warnings"]) or all(x["needs_review"] for x in inj["invented_line_entities"]))
                unflagged_invented = [x for x in inj["invented_line_entities"] if not x["needs_review"]]
                false_alarm = outcome["clean"]["status"] != "ok" or bool(outcome["clean"]["suspicion_warnings"])
                detector_rows[f"{split}/{path.name}"] = {**outcome, "detected": detected, "false_alarm": false_alarm,
                                                         "unflagged_invented_entities": unflagged_invented}
                print(f"  reliability detector {split}/{path.name:36s} detected={detected} unflagged_invented={len(unflagged_invented)} false_alarm={false_alarm}", flush=True)
    finally:
        ocr.read_page = real_read

    return {
        "controls": control_rows,
        "controls_passed": sum(r["passed"] for r in control_rows.values()),
        "controls_total": len(control_rows),
        "detector": detector_rows,
        "detector_detected": sum(r["detected"] for r in detector_rows.values()),
        "detector_unflagged_invented_entities": sum(len(r["unflagged_invented_entities"]) for r in detector_rows.values()),
        "detector_false_alarms": sum(r["false_alarm"] for r in detector_rows.values()),
        "detector_total": len(detector_rows),
    }


def _all_entities(e) -> list:
    return metrics._entities(e)


# ------------------------------------------------------------------------------ report

def write_summary(results: list[dict], reliability: dict | None, manifest_problems: list[str]) -> str:
    out = ["# Evaluation summary", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `eval/run.py`.", ""]
    if manifest_problems:
        out += ["## ⚠ Held-out integrity", ""] + [f"- {p}" for p in manifest_problems] + [""]
    for res in results:
        split, mode = res["split"], res["mode"]
        out += [f"## {split} / {mode}", ""]
        out += [f"- {w}" for w in res.get("warnings", [])]
        if not res["documents"]:
            out += ["", "_No documents._", ""]
            continue
        s = res["summary"]
        o = s["overall"]
        out += ["", f"Documents: {s['documents']} · crashes: {s['crashes']} · document-type accuracy: {s['document_type_accuracy']}",
                f"Extraction overall: precision {o['precision']} · recall {o['recall']} (tp {o['tp']}, fp {o['fp']}, fn {o['fn']})",
                f"False positives {s['false_positives']} · false negatives {s['false_negatives']} · wrong values {s['wrong_values']} · "
                f"**unflagged errors {s['unflagged_errors']}** · placement errors {s['placement_errors']} · grounding failures {s['grounding_failures']}", ""]
        if "ocr_critical_tokens" in s:
            cats = " · ".join(f"{k} {v['found']}/{v['expected']}" for k, v in sorted(s["ocr_critical_tokens"]["by_category"].items()))
            out += [f"OCR critical tokens: accuracy {s['ocr_critical_tokens']['accuracy']} ({cats})",
                    f"OCR mean CER {s['ocr_mean_cer']} · unsupported (invented/garbled) lines {s['ocr_unsupported_lines']} · "
                    f"mean {s['mean_seconds_per_file']} s/file",
                    f"Output distinctness (closest to its own source): {s.get('outputs_closest_to_own_source', 'n/a')}"
                    + ("".join(f"<br>⚠ {p}" for p in s.get("output_distinctness_problems", []))), ""]
        out += ["| field | tp | fp | fn | precision | recall |", "|---|---|---|---|---|---|"]
        out += [f"| {f} | {c['tp']} | {c['fp']} | {c['fn']} | {c['precision']} | {c['recall']} |" for f, c in s["fields"].items()]
        out += ["", "| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |", "|---|---|---|---|---|---|---|"]
        for name, r in res["documents"].items():
            if r["crashed"]:
                out.append(f"| {name} | **CRASH** | | | | | |")
                continue
            ex = r["extraction"]
            tp, fp, fn = (sum(c[k] for c in ex["fields"].values()) for k in ("tp", "fp", "fn"))
            problems = [f"{x['kind']} {x['field']}: expected {x['expected']!r} got {x['got']!r}"
                        + ("" if x["needs_review"] is None else (" (flagged)" if x["needs_review"] else " (**NOT flagged**)"))
                        for x in ex["errors"]]
            if "ocr" in r:
                problems += [f"OCR missed {m['category']} {m['token']!r}" for m in r["ocr"]["missing"]]
                problems += [f"OCR read {s_['written']!r} as {s_['read']!r}" for s_ in r["ocr"]["substitutions"] if s_["op"] == "replace"]
                problems += [f"OCR line not on page: {l!r}" for l in r["ocr"]["unsupported_lines"]]
            crit = f"{r['ocr']['critical_total']['found']}/{r['ocr']['critical_total']['expected']}" if "ocr" in r else ""
            cer_ = r["ocr"]["cer"] if "ocr" in r else ""
            out.append(f"| {name} | {r['status']} | {tp}/{fp}/{fn} | {len(ex['unflagged_errors'])} | {crit} | {cer_} | {'<br>'.join(problems) or '—'} |")
        out.append("")
    if reliability:
        out += ["## Reliability", "",
                f"Non-documents returning `unreadable` with no entities: **{reliability['controls_passed']}/{reliability['controls_total']}**", ""]
        out += [f"- {n}: {'pass' if r['passed'] else 'FAIL'} ({r.get('status')})" for n, r in reliability["controls"].items()]
        out += ["", f"Hallucination detector (OCR stubbed with the true text plus one invented line): detected "
                f"**{reliability['detector_detected']}/{reliability['detector_total']}**, invented-line entities not flagged "
                f"**{reliability['detector_unflagged_invented_entities']}**, false alarms on clean text {reliability['detector_false_alarms']}/{reliability['detector_total']}", ""]
        out += [f"- {n}: detected={r['detected']} unflagged_invented={len(r['unflagged_invented_entities'])} false_alarm={r['false_alarm']}"
                for n, r in reliability["detector"].items()]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=(*SPLITS, "all"), default="all")
    parser.add_argument("--mode", choices=("text", "ocr", "all"), default="all")
    parser.add_argument("--no-reliability", action="store_true")
    args = parser.parse_args()

    splits = SPLITS if args.split == "all" else (args.split,)
    modes = ("text", "ocr") if args.mode == "all" else (args.mode,)
    manifest_problems = verify_heldout_manifest() if "heldout" in splits else []
    for p in manifest_problems:
        print("WARNING:", p)
    REPORTS.mkdir(exist_ok=True)

    results = []
    for split in splits:
        for mode in modes:
            print(f"== {split} / {mode}", flush=True)
            res = run_split(split, mode)
            res["heldout_integrity_problems"] = manifest_problems if split == "heldout" else []
            (REPORTS / f"{split}_{mode}.json").write_text(json.dumps(res, indent=1))
            results.append(res)
    reliability = None
    if "ocr" in modes and not args.no_reliability:
        print("== reliability", flush=True)
        reliability = run_reliability(splits)
        (REPORTS / "reliability.json").write_text(json.dumps(reliability, indent=1))
    (REPORTS / "SUMMARY.md").write_text(write_summary(results, reliability, manifest_problems))
    print(f"\nwrote {REPORTS / 'SUMMARY.md'}")
    for res in results:
        if res["documents"]:
            s = res["summary"]
            print(f"{res['split']:10s} {res['mode']:4s} precision={s['overall']['precision']} recall={s['overall']['recall']} "
                  f"fp={s['false_positives']} fn={s['false_negatives']} unflagged={s['unflagged_errors']} "
                  f"placement={s['placement_errors']} ungrounded={s['grounding_failures']} crashes={s['crashes']}"
                  + (f" critical_ocr={s['ocr_critical_tokens']['accuracy']} cer={s['ocr_mean_cer']}"
                     f" distinct={s.get('outputs_closest_to_own_source')}" if "ocr_critical_tokens" in s else ""))
    if reliability:
        print(f"reliability controls {reliability['controls_passed']}/{reliability['controls_total']} · detector "
              f"{reliability['detector_detected']}/{reliability['detector_total']} · false alarms {reliability['detector_false_alarms']}")


if __name__ == "__main__":
    main()

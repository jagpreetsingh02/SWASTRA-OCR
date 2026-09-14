"""Compare OCR models on real handwriting: scorecard, dangerous errors, script breakdown.

    .venv/bin/python eval/model_selection/analyse_models.py                 # scorecard + dangerous errors
    .venv/bin/python eval/model_selection/analyse_models.py --pipeline      # + unchanged extraction pipeline

Reads the per-model JSON written by real_handwriting.py. Measurement only: it never edits a model, a
prompt or the production engine, and it applies no spellcheck, dictionary or fuzzy correction to any
model's output -- the primary numbers are what each model literally read.

`--pipeline` is the SECONDARY test required by the brief: it feeds each model's transcription through
the UNCHANGED extraction pipeline (`pipeline.analyse_text`) and scores it with the same strict metrics
used by eval/run.py, showing practical impact. It loads GLiNER but no OCR model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent
REPO = EVAL.parent
DOCS = EVAL / "real_world"
REPORTS = EVAL / "reports" / "model_selection_real_world"
sys.path.insert(0, str(EVAL))
sys.path.insert(0, str(REPO))
import metrics  # noqa: E402

CATEGORIES = ["medicine_name", "dosage", "frequency", "duration", "date"]


def cell(value, spec: str = "%s") -> str:
    """A missing measurement prints as '--'. Never as 'None', and never silently as zero."""
    return "--" if value is None else spec % value


def load_runs() -> tuple[list[dict], list[dict]]:
    """(complete runs, failed runs). A model that died mid-benchmark is reported, never silently dropped:
    its absence from a scorecard would read as "not tried" rather than "tried and unusable here"."""
    complete, failed = [], []
    for f in sorted(REPORTS.glob("*.json")):
        if f.name in ("summary.json", "dangerous_errors.json", "pipeline.json"):
            continue
        run = json.loads(f.read_text())
        (failed if run.get("status", "").startswith("INCOMPLETE") else complete).append(run)
    return complete, failed


def report_failures(failed: list[dict]) -> None:
    if not failed:
        return
    print("=" * 132)
    print("MODELS THAT COULD NOT COMPLETE THE BENCHMARK IN THIS ENVIRONMENT")
    for r in failed:
        c = r.get("partial_critical_total", {})
        print("  %-14s %-34s %s" % (r["engine"], r["model_id"], r["status"]))
        print("     completed %s/%s pages, last %s | partial critical %s/%s (%s) | %s s/page"
              % (r.get("documents_completed"), r.get("documents_attempted"), r.get("last_completed"),
                 c.get("found"), c.get("expected"), c.get("accuracy"), r.get("mean_seconds_per_page_partial")))
        print("     %s" % r.get("verdict", "")[:120])


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def dangerous_errors(run: dict) -> list[dict]:
    """A truth token the model missed, next to the closest thing it actually wrote.

    A near-miss on a medicine name or a number is the dangerous case: the reader sees a plausible drug
    or dose that nobody prescribed. A token that simply vanished is a miss, not a substitution, and is
    reported separately by the scorecard.
    """
    out = []
    for doc in run["documents_detail"]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9.\-/]*|\d+(?:[./]\d+)*", doc["text"])
        for miss in doc["missing"]:
            token = str(miss["token"])
            best, best_d = None, 99
            for w in words:
                if w.lower() == token.lower():
                    continue
                d = edit_distance(token.lower(), w.lower())
                if d < best_d and d <= max(1, min(3, len(token) // 3)):
                    best, best_d = w, d
            if best is not None:
                out.append({"engine": run["engine"], "document": doc["document"],
                            "category": miss["category"], "truth": token, "model_wrote": best,
                            "edit_distance": best_d,
                            "kind": "numeric substitution" if token[:1].isdigit() else "name substitution"})
    return out


def scorecard(runs: list[dict]) -> None:
    print("=" * 132)
    print("SCORECARD -- 21 real_world_dev handwritten prescriptions, identical images, identical strict truth")
    print("=" * 132)
    head = "%-13s %9s " % ("engine", "critical") + "".join("%13s" % c for c in CATEGORIES)
    print(head + "%7s %6s %6s %7s %8s" % ("loops", "empty", "errs", "s/page", "coldload"))
    for r in sorted(runs, key=lambda r: -(r["critical_total"]["accuracy"] or 0)):
        cells = ""
        for c in CATEGORIES:
            g = r["critical_by_category"].get(c)
            cells += "%13s" % (f"{g['found']}/{g['expected']}" if g else "-")
        # a derived row carries no timing of its own; print "--" rather than crash or invent a number
        print("%-13s %9s %s%7d %6d %6d %7s %8s"
              % (r["engine"], r["critical_total"]["accuracy"], cells, r["generation_loops"],
                 r["empty_outputs"], r["errors"], cell(r.get("mean_seconds_per_page"), "%.2f"),
                 cell(r.get("cold_load_s"), "%.1f")))
    print()
    print("%-13s %-34s %-11s %-7s %s" % ("engine", "model id", "licence", "device", "memory after load"))
    for r in runs:
        mem = r.get("memory_after_load") or {}
        print("%-13s %-34s %-11s %-7s rss %s MB, mps %s MB"
              % (r["engine"], r["model_id"], r["licence"], r["device"],
                 cell(mem.get("max_rss_mb")), cell(mem.get("mps_allocated_mb"))))
    for r in runs:
        if r.get("provenance"):
            print("\n  note on %s: %s" % (r["engine"], r["provenance"]))
        if r.get("latency_note"):
            print("  latency for %s: %s" % (r["engine"], r["latency_note"]))


def script_breakdown(runs: list[dict]) -> None:
    """Section 7: Bangla failures must not hide Roman-script medicine-name failures."""
    print("=" * 132)
    print("SCRIPT / LANGUAGE BREAKDOWN")
    print("  Every truth medicine name in this corpus is written in Roman script, so medicine_name")
    print("  accuracy IS the Roman-script medicine accuracy. Bangla appears in dosing and advice text.")
    print()
    print("%-13s %18s %14s %16s %16s" % ("engine", "roman medicine", "pages w/Bangla", "pages w/CJK", "mean lines/page"))
    for r in runs:
        med = r["critical_by_category"].get("medicine_name", {})
        acc = med.get("accuracy")
        lines = sum(d["lines"] for d in r["documents_detail"]) / max(len(r["documents_detail"]), 1)
        print("%-13s %8s (%5s) %14d %16d %16.1f"
              % (r["engine"], f"{med.get('found')}/{med.get('expected')}", acc,
                 r["pages_with_bangla"], r["pages_with_cjk"], lines))


def hallucination_table(runs: list[dict]) -> None:
    print("=" * 132)
    print("HALLUCINATION / FAILURE BEHAVIOUR")
    print("%-13s %7s %7s %8s %9s %11s %s" % ("engine", "loops", "empty", "errors", "maxrepeat", "cjk pages", "worst page"))
    for r in runs:
        worst = max(r["documents_detail"], key=lambda d: d["longest_repeat_run"])
        print("%-13s %7d %7d %8d %9d %11d %s (run=%d, %d lines/%d distinct)"
              % (r["engine"], r["generation_loops"], r["empty_outputs"], r["errors"],
                 worst["longest_repeat_run"], r["pages_with_cjk"], worst["document"],
                 worst["longest_repeat_run"], worst["lines"], worst["distinct_lines"]))


def pipeline_test(runs: list[dict]) -> dict:
    """Secondary: the UNCHANGED extraction pipeline over each model's transcription."""
    from medikiosk_ocr import pipeline

    print("=" * 132)
    print("SECONDARY -- unchanged extraction pipeline over each model's text")
    print("%-13s %10s %8s %8s %8s %10s %10s" % ("engine", "precision", "recall", "med tp", "med fp", "placement", "ungrounded"))
    out = {}
    for r in runs:
        tp = fp = fn = placement = ungrounded = 0
        med = Counter()
        for doc in r["documents_detail"]:
            truth = metrics.load_truth(DOCS / f"{doc['document']}.truth.json")
            result = pipeline.analyse_text(doc["text"])
            score = metrics.score_extraction(result, truth)
            for name, f in score["fields"].items():
                tp += f["tp"]; fp += f["fp"]; fn += f["fn"]
                if name == "medication":
                    med["tp"] += f["tp"]; med["fp"] += f["fp"]; med["fn"] += f["fn"]
            placement += len(score.get("placement_errors") or [])
            ungrounded += len(score.get("ungrounded") or [])
        precision = round(tp / (tp + fp), 3) if tp + fp else 0.0
        recall = round(tp / (tp + fn), 3) if tp + fn else 0.0
        out[r["engine"]] = {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn,
                            "medication": dict(med), "placement_errors": placement,
                            "grounding_failures": ungrounded}
        print("%-13s %10s %8s %8d %8d %10d %10d"
              % (r["engine"], precision, recall, med["tp"], med["fp"], placement, ungrounded))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", action="store_true", help="also run the unchanged extraction pipeline")
    args = parser.parse_args()

    runs, failed = load_runs()
    if not runs:
        print("no completed model runs found in", REPORTS)
        return
    scorecard(runs)
    report_failures(failed)
    script_breakdown(runs)
    hallucination_table(runs)

    danger = [e for r in runs for e in dangerous_errors(r)]
    print("=" * 132)
    print("CLINICALLY DANGEROUS SUBSTITUTIONS (a truth token missed, with the nearest thing the model wrote)")
    print("%-13s %-9s %-14s %-26s %-26s %s" % ("engine", "document", "category", "truth", "model wrote", "dist"))
    for e in sorted(danger, key=lambda e: (e["engine"], e["document"]))[:60]:
        print("%-13s %-9s %-14s %-26s %-26s %d"
              % (e["engine"], e["document"], e["category"], e["truth"][:26], e["model_wrote"][:26], e["edit_distance"]))
    counts = Counter(e["engine"] for e in danger)
    print("\n  dangerous substitutions per engine:", dict(counts) or "none")
    (REPORTS / "dangerous_errors.json").write_text(json.dumps(danger, indent=1) + "\n")

    summary = {"documents": runs[0]["documents"], "split": "real_world_dev",
               "holdout_runs": 0,
               "failed_engines": {r["engine"]: {"model_id": r["model_id"], "status": r["status"],
                                                "completed": r.get("documents_completed"),
                                                "verdict": r.get("verdict")} for r in failed},
               "engines": {r["engine"]: {"model_id": r["model_id"], "licence": r["licence"],
                                         "critical": r["critical_total"],
                                         "by_category": r["critical_by_category"],
                                         "loops": r["generation_loops"], "empty": r["empty_outputs"],
                                         "errors": r["errors"],
                                         "seconds_per_page": r["mean_seconds_per_page"],
                                         "cold_load_s": r["cold_load_s"],
                                         "memory_after_load": r.get("memory_after_load")} for r in runs},
               "dangerous_substitutions": dict(counts)}
    if args.pipeline:
        summary["pipeline"] = pipeline_test(runs)
    (REPORTS / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("\nwrote", REPORTS / "summary.json", "and dangerous_errors.json")


if __name__ == "__main__":
    main()

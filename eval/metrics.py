"""Strict matching and scoring for evaluation. No model code; scores ExtractionResult objects.

Matching rules (never loosened to raise a score):

* names -- medicines, tests, diagnoses, symptoms, allergies, patient, doctor: equal after lowercasing,
  collapsing whitespace and trimming surrounding punctuation. No substring matching.
* values -- doses, frequencies, durations, dates, lab values, units, ranges: equal after lowercasing
  and removing whitespace only. "5" != "500", "D" != "OD", "1.1" != "1.15".
* A truth value may be a list of acceptable alternatives, e.g. ["Vikram Rathod", "Mr. Vikram Rathod"].

Truth file format: see eval/README.md ("Truth format"). `load_truth` rejects unknown or missing keys.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

DOC_TYPES = {"prescription", "lab_report", "discharge_summary", "medical_invoice", "pharmaceutical_information",
             "other_medical", "unknown"}
TRUTH_KEYS = {"document_type", "patient_name", "doctor_name", "date", "medications", "test_results",
              "tests", "diagnoses", "symptoms", "allergies"}
# medication_mentions: medicines the document only names (invoice lines, product literature). Optional so
# that truth files for documents without any mention stay short; absent means "none expected".
# vitals: observations measured on the patient (BP, pulse, SpO2) -- same shape as a lab result but never one.
# panels: test-group headings a lab report groups its analytes under (Complete Blood Count).
OPTIONAL_KEYS = {"notes", "medication_mentions", "vitals", "panels"}
MED_KEYS = {"name", "dosage", "frequency", "duration"}
RESULT_KEYS = {"name", "value", "unit", "reference_range"}
LIST_FIELDS = ("diagnoses", "symptoms", "tests", "allergies")


# ------------------------------------------------------------------------------ truth

def load_truth(path: Path | str) -> dict:
    path = Path(path)
    t = json.loads(path.read_text())
    problems = []
    if unknown := set(t) - TRUTH_KEYS - OPTIONAL_KEYS:
        problems.append(f"unknown keys {sorted(unknown)}")
    if missing := TRUTH_KEYS - set(t):
        problems.append(f"missing keys {sorted(missing)}")
    if t.get("document_type") not in DOC_TYPES:
        problems.append(f"document_type must be one of {sorted(DOC_TYPES)}")
    for field in ("medications", "medication_mentions"):
        for m in t.get(field, []):
            if set(m) != MED_KEYS:
                problems.append(f"{field} keys must be {sorted(MED_KEYS)}: {m}")
    for r in t.get("test_results", []):
        if set(r) != RESULT_KEYS:
            problems.append(f"test_result keys must be {sorted(RESULT_KEYS)}: {r}")
    for v in t.get("vitals", []):
        if not set(v) <= RESULT_KEYS:
            problems.append(f"vitals keys must be a subset of {sorted(RESULT_KEYS)}: {v}")
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return t


def alts(value) -> list[str]:
    return [] if value is None else [value] if isinstance(value, str) else list(value)


def name_key(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().strip(".,;:").strip().lower()


def value_key(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def name_match(pred: str | None, truth) -> bool:
    return pred is not None and name_key(pred) in {name_key(a) for a in alts(truth)}


def value_match(pred: str | None, truth) -> bool:
    return pred is not None and value_key(pred) in {value_key(a) for a in alts(truth)}


# ------------------------------------------------------------------------------ OCR scoring

def token_pattern(token: str) -> re.Pattern:
    """Whole-token, case-insensitive, whitespace-tolerant ("500 mg" == "500mg") match that cannot hit
    inside a longer token: "5" does not match in "500" or "5.1"; "1.1" does not match in "1.15"."""
    body = r"\s*".join(re.escape(ch) for ch in token if not ch.isspace())
    return re.compile(rf"(?<![0-9A-Za-z])(?<!\d\.){body}(?![0-9A-Za-z])(?!\.\d)", re.I)


def count_token(token: str, text: str) -> int:
    return len(token_pattern(token).findall(text))


def critical_tokens(truth: dict, transcription: str | None) -> list[tuple[str, str]]:
    """(category, token) for every value whose exact reading matters clinically."""

    def pick(value):
        options = alts(value)
        if transcription:  # prefer the alternative actually written on the page (longest)
            present = [o for o in options if count_token(o, transcription)]
            if present:
                return max(present, key=len)
        return options[0] if options else None

    out = []
    for m in [*truth["medications"], *truth.get("medication_mentions", [])]:
        for category, field in (("medicine_name", "name"), ("dosage", "dosage"), ("frequency", "frequency"),
                                ("duration", "duration")):
            if (token := pick(m.get(field))) is not None:
                out.append((category, token))
    for r in truth["test_results"]:
        for category, field in (("lab_name", "name"), ("lab_value", "value")):
            if (token := pick(r[field])) is not None:
                out.append((category, token))
    for field in ("patient_name", "doctor_name"):
        if (token := pick(truth[field])) is not None:
            out.append(("header", token))
    if (token := pick(truth["date"])) is not None:
        out.append(("date", token))
    return out


def score_ocr(ocr_text: str, truth: dict, transcription: str | None) -> dict:
    """Critical-token accuracy (count-aware), CER, unsupported lines, word substitutions."""
    expected_by_token: dict[tuple[str, str], int] = {}
    for category, token in critical_tokens(truth, transcription):
        key = (category, token)
        truth_count = count_token(token, transcription) if transcription else 0
        expected_by_token[key] = max(expected_by_token.get(key, 0) + (0 if transcription else 1), truth_count, 1)
    categories: dict[str, dict] = {}
    missing = []
    for (category, token), expected in expected_by_token.items():
        found = min(expected, count_token(token, ocr_text))
        c = categories.setdefault(category, {"expected": 0, "found": 0})
        c["expected"] += expected
        c["found"] += found
        if found < expected:
            missing.append({"category": category, "token": token, "expected": expected, "found": found})
    total = {"expected": sum(c["expected"] for c in categories.values()), "found": sum(c["found"] for c in categories.values())}
    out = {"critical_by_category": categories, "critical_total": total, "missing": missing,
           "cer": None, "unsupported_lines": [], "substitutions": []}
    if transcription is not None:
        out["cer"] = cer(ocr_text, transcription)
        out["unsupported_lines"] = unsupported_lines(ocr_text, transcription)
        out["substitutions"] = substitutions(transcription, ocr_text)
    return out


def cer(hyp: str, ref: str) -> float:
    a, b = re.sub(r"\s+", " ", hyp).strip().lower(), re.sub(r"\s+", " ", ref).strip().lower()
    if not b:
        return float(len(a) > 0)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return round(prev[-1] / len(b), 3)


def unsupported_lines(ocr_text: str, transcription: str) -> list[str]:
    """OCR lines with no similar line in the transcription: text the page does not contain.

    Whitespace is normalised on both sides first: a table row padded with spaces, or a wide
    two-column header that OCR reflows into two lines, is still the page's own text. A line is
    also supported if it is contained in a transcription line (that is what reflow produces)."""
    def flat(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    truth_lines = [flat(l) for l in transcription.splitlines() if l.strip()]
    out = []
    for original in (l for l in ocr_text.splitlines() if l.strip()):
        line = flat(original)
        best = max((difflib.SequenceMatcher(None, line, t).ratio() for t in truth_lines), default=0.0)
        if best < 0.5 and not any(line in t for t in truth_lines):
            out.append(original.strip())
    return out


def substitutions(transcription: str, ocr_text: str) -> list[dict]:
    """Word-level differences between what is written and what was read (misreads, language-prior corrections)."""
    truth_words, ocr_words = transcription.split(), ocr_text.split()
    out = []
    matcher = difflib.SequenceMatcher(None, truth_words, ocr_words, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "equal":
            out.append({"op": op, "written": " ".join(truth_words[i1:i2]), "read": " ".join(ocr_words[j1:j2])})
    return out


# ------------------------------------------------------------------------------ extraction scoring

def _entities(e) -> list:
    out = [e.patient_name, e.doctor_name, e.date, *e.diagnoses, *e.symptoms, *e.tests, *e.allergies,
           *getattr(e, "panels", [])]
    for m in e.medications:
        out += [m.name, m.dosage, m.frequency, m.duration]
    for r in [*e.test_results, *getattr(e, "vitals", [])]:
        out += [r.name, r.value, getattr(r, "unit", None), r.reference_range]
    return [x for x in out if x is not None]


def score_extraction(result, truth: dict) -> dict:
    """Per-field TP/FP/FN, every individual error (with whether it was flagged for review), grounding
    failures and field-placement errors. An error with needs_review=False is 'unflagged' -- the dangerous kind."""
    e, raw = result.entities, result.raw_text
    counts: dict[str, dict[str, int]] = {}
    errors: list[dict] = []

    def bump(field, kind):
        counts.setdefault(field, {"tp": 0, "fp": 0, "fn": 0})[kind] += 1

    def err(kind, field, expected, got, entity=None):
        errors.append({"kind": kind, "field": field, "expected": expected, "got": got,
                       "needs_review": None if entity is None else bool(entity.needs_review)})

    def compare(field, entity, truth_value, match):
        if truth_value is None and entity is None:
            return
        if truth_value is None:
            bump(field, "fp")
            err("unexpected_value", field, None, entity.text, entity)
        elif entity is None:
            bump(field, "fn")
            err("missing", field, truth_value, None)
        elif match(entity.text, truth_value):
            bump(field, "tp")
        else:
            bump(field, "fp")
            bump(field, "fn")
            err("wrong_value", field, truth_value, entity.text, entity)

    # header
    compare("patient_name", e.patient_name, truth["patient_name"], name_match)
    compare("doctor_name", e.doctor_name, truth["doctor_name"], name_match)
    compare("date", e.date, truth["date"], value_match)

    # medications (prescribed) and medication_mentions (named only): one-to-one by exact name, then fields.
    # Scored separately on purpose -- a mention promoted to a prescription is a safety error, not a near miss.
    for field, predicted, expected in (("medication", e.medications, truth["medications"]),
                                       ("medication_mention", e.medication_mentions, truth.get("medication_mentions", []))):
        remaining = list(range(len(predicted)))
        for tm in expected:
            idx = next((i for i in remaining if name_match(predicted[i].name.text, tm["name"])), None)
            if idx is None:
                bump(field, "fn")
                err("missing", field, tm["name"], None)
                continue
            remaining.remove(idx)
            bump(field, "tp")
            pm = predicted[idx]
            for sub in ("dosage", "frequency", "duration"):
                if sub in tm:
                    compare(f"{field}.{sub}", getattr(pm, sub), tm[sub], value_match)
        for i in remaining:
            bump(field, "fp")
            err("false_positive", field, None, predicted[i].name.text, predicted[i].name)

    # lab results
    remaining = list(range(len(e.test_results)))
    for tr in truth["test_results"]:
        idx = next((i for i in remaining if name_match(e.test_results[i].name.text, tr["name"])), None)
        if idx is None:
            bump("test_result", "fn")
            err("missing", "test_result", tr["name"], None)
            continue
        remaining.remove(idx)
        bump("test_result", "tp")
        pr = e.test_results[idx]
        compare("test_result.value", pr.value, tr["value"], value_match)
        compare("test_result.unit", getattr(pr, "unit", None), tr["unit"], value_match)
        compare("test_result.reference_range", pr.reference_range, tr["reference_range"], value_match)
    for i in remaining:
        bump("test_result", "fp")
        err("false_positive", "test_result", None, e.test_results[i].name.text, e.test_results[i].name)

    # vitals (observations) and panels (test-group headings) are scored ONLY where a truth file declares
    # them. They were added after the held-out split was frozen, so scoring them against a truth file that
    # cannot mention them would turn correct extractions into false positives -- and invite editing frozen
    # labels to hide it. Dev truth files declare them, so dev measures them properly.
    if "vitals" in truth:
        vitals = list(getattr(e, "vitals", []))
        remaining = list(range(len(vitals)))
        for tv in truth["vitals"]:
            idx = next((i for i in remaining if name_match(vitals[i].name.text, tv["name"])), None)
            if idx is None:
                bump("vital", "fn")
                err("missing", "vital", tv["name"], None)
                continue
            remaining.remove(idx)
            bump("vital", "tp")
            for sub in ("value", "unit"):
                if sub in tv:
                    compare(f"vital.{sub}", getattr(vitals[idx], sub, None), tv[sub], value_match)
        for i in remaining:
            bump("vital", "fp")
            err("false_positive", "vital", None, vitals[i].name.text, vitals[i].name)

    if "panels" in truth:
        pred = list(getattr(e, "panels", []))
        for item in truth["panels"]:
            idx = next((i for i, p in enumerate(pred) if name_match(p.text, item)), None)
            if idx is None:
                bump("panel", "fn")
                err("missing", "panel", item, None)
            else:
                pred.pop(idx)
                bump("panel", "tp")
        for p in pred:
            bump("panel", "fp")
            err("false_positive", "panel", None, p.text, p)

    # simple lists
    for field in LIST_FIELDS:
        pred = list(getattr(e, field, []))
        for item in truth.get(field, []):
            idx = next((i for i, p in enumerate(pred) if name_match(p.text, item)), None)
            if idx is None:
                bump(field, "fn")
                err("missing", field, item, None)
            else:
                pred.pop(idx)
                bump(field, "tp")
        for p in pred:
            bump(field, "fp")
            err("false_positive", field, None, p.text, p)

    # a wrong/extra value that is the truth for a DIFFERENT field is a placement error
    truth_values = _truth_values(truth)
    for error in errors:
        if error["got"] is None:
            continue
        for other_field, candidates in truth_values.items():
            if other_field != error["field"] and any(name_key(error["got"]) == name_key(c) or value_key(error["got"]) == value_key(c) for c in candidates):
                error["placement"] = other_field
                break

    ungrounded = [ent.text for ent in _entities(e) if raw[ent.start:ent.end] != ent.text]
    for field in counts.values():
        tp, fp, fn = field["tp"], field["fp"], field["fn"]
        field["precision"] = round(tp / (tp + fp), 3) if tp + fp else None
        field["recall"] = round(tp / (tp + fn), 3) if tp + fn else None
    return {
        "document_type": {"expected": truth["document_type"], "got": result.document_type.value,
                          "ok": truth["document_type"] == result.document_type.value},
        "fields": counts,
        "errors": errors,
        "unflagged_errors": [x for x in errors if x["got"] is not None and x["needs_review"] is False],
        "placement_errors": [x for x in errors if "placement" in x],
        "ungrounded": ungrounded,
    }


def _truth_values(truth: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}

    def add(field, value):
        out.setdefault(field, []).extend(alts(value))

    for field in ("patient_name", "doctor_name", "date"):
        add(field, truth[field])
    for field, items in (("medication", truth["medications"]), ("medication_mention", truth.get("medication_mentions", []))):
        for m in items:
            add(field, m["name"])
            for f in ("dosage", "frequency", "duration"):
                add(f"{field}.{f}", m.get(f))
    for r in truth["test_results"]:
        add("test_result", r["name"])
        for f in ("value", "unit", "reference_range"):
            add(f"test_result.{f}", r[f])
    for field in LIST_FIELDS:
        for item in truth[field]:
            add(field, item)
    return out


def aggregate(rows: list[dict]) -> dict:
    fields: dict[str, dict[str, int]] = {}
    for row in rows:
        for field, c in row["extraction"]["fields"].items():
            agg = fields.setdefault(field, {"tp": 0, "fp": 0, "fn": 0})
            for k in ("tp", "fp", "fn"):
                agg[k] += c[k]
    for c in fields.values():
        c["precision"] = round(c["tp"] / (c["tp"] + c["fp"]), 3) if c["tp"] + c["fp"] else None
        c["recall"] = round(c["tp"] / (c["tp"] + c["fn"]), 3) if c["tp"] + c["fn"] else None
    tp, fp, fn = (sum(c[k] for c in fields.values()) for k in ("tp", "fp", "fn"))
    return {
        "fields": dict(sorted(fields.items())),
        "overall": {"tp": tp, "fp": fp, "fn": fn,
                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else None},
        "false_positives": sum(1 for r in rows for x in r["extraction"]["errors"] if x["kind"] in ("false_positive", "unexpected_value")),
        "false_negatives": sum(1 for r in rows for x in r["extraction"]["errors"] if x["kind"] == "missing"),
        "wrong_values": sum(1 for r in rows for x in r["extraction"]["errors"] if x["kind"] == "wrong_value"),
        "unflagged_errors": sum(len(r["extraction"]["unflagged_errors"]) for r in rows),
        "placement_errors": sum(len(r["extraction"]["placement_errors"]) for r in rows),
        "grounding_failures": sum(len(r["extraction"]["ungrounded"]) for r in rows),
        "document_type_accuracy": round(sum(r["extraction"]["document_type"]["ok"] for r in rows) / len(rows), 3) if rows else None,
    }

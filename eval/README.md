# Evaluation

One command runs everything:

```bash
.venv/bin/python eval/run.py                               # all splits, text + OCR, reliability (~15 min on an M5)
.venv/bin/python eval/run.py --split real_world --mode ocr  # just the real documents
.venv/bin/python eval/run.py --mode text                    # extraction only (no OCR model needed)
```

It writes `eval/reports/SUMMARY.md` (every document listed individually, every error named, and
whether each error was flagged `needs_review`) plus one JSON report per split/mode and
`eval/reports/reliability.json`.

## Splits — and the rule that keeps them honest

| Folder | What | May be used to tune rules/prompts? |
|---|---|---|
| `dev/` | Everything used while building: MediKiosk-2 / SIH_test fixtures, generated handwriting, probes, and five texts that were held out in an earlier round and then used to find bugs | **Yes** — so dev numbers are optimistic by construction |
| `heldout/` | Eight documents (+ rendered variants) written **before** the current extraction rules and never used to tune them. `MANIFEST.sha256` freezes them; `run.py` warns loudly if anything changed | **No** |
| `real_world/` | Real, consented, de-identified documents. Empty until someone adds them | **No** |
| `controls/` | Non-documents (blurred, dark, table photo) used by the reliability check | — |

If a held-out or real-world document ever reveals a bug and you fix it, **move that document to
`dev/`** and say so in its `notes`. A split you have tuned on is no longer held out.

All `dev/` and `heldout/` content is synthetic: no real patient, doctor or clinic. The handwriting
is rendered from fonts, which is far easier than real doctors' handwriting — only `real_world/`
can show real handwriting performance.

## Adding a document

For a document `<stem>`:

- the file: `<stem>.<ext>` or `<stem>_<variant>.<ext>` (`.png .jpg .jpeg .tif .tiff .webp .bmp .heic .heif .pdf`);
  several variants can share one truth file (`rx12_scan.png`, `rx12_photo.heic`);
- `<stem>.truth.json`: what is actually written on the page (format below);
- `<stem>.txt` (recommended): an exact transcription, line by line. Enables OCR scoring (critical
  tokens, CER, substitutions, invented lines) and text-mode extraction scoring.

`eval/real_world/truth_template.json` is a blank truth file to copy.

## Truth format

```json
{
 "document_type": "prescription",
 "patient_name": "Kiran Patil",
 "doctor_name": ["Dr Anjali Deshpande", "Dr. Anjali Deshpande"],
 "date": "19-08-2026",
 "medications": [
  {"name": "Levocet", "dosage": "2.5ml", "frequency": "HS", "duration": "5 days"}
 ],
 "medication_mentions": [],
 "test_results": [
  {"name": "HbA1c", "value": "8.2", "unit": "%", "reference_range": "4.0 - 5.6"}
 ],
 "tests": ["lipid profile"],
 "diagnoses": ["viral fever"],
 "symptoms": ["fever", "runny nose"],
 "allergies": [],
 "notes": "optional free text"
}
```

- Every key except `notes` and `medication_mentions` is required; unknown keys are rejected (typos cannot
  silently score as misses).
- `document_type`: `prescription`, `lab_report`, `discharge_summary`, `medical_invoice`,
  `pharmaceutical_information`, `other_medical`, `unknown`.
- Values are **as written on the page** — misspellings, abbreviations and units included
  (`"Augmtin"`, `"PCM"`, `"500MG"`). Never the corrected or expanded form.
- `null` = not on the page. `[]` = none on the page.
- Any value may be a list of acceptable alternatives when more than one reading is equally right
  (`["Mr. Vikram Rathod", "Vikram Rathod"]`). List items in `tests`/`diagnoses`/`symptoms`/`allergies`
  may themselves be alternatives lists.
- `tests` are tests mentioned or advised without a result; `test_results` have a value.
- `medications` are medicines the document presents as prescribed to or taken by a patient.
  `medication_mentions` (same shape, optional) are medicines the document only **names** — invoice line
  items, package inserts, advertising. A medicine belongs to one list or the other, never both; absent
  means none expected.

## Matching (strict)

Implemented in `eval/metrics.py`, unit-tested in `tests/unit/test_metrics.py`.

- **Values** (doses, frequencies, durations, dates, lab values, units, ranges): identical after
  lowercasing and removing whitespace. `"5"` ≠ `"500"`, `"D"` ≠ `"OD"`, `"1.1"` ≠ `"1.15"`, `"500MG"` = `"500 mg"`.
- **Names** (medicines, tests, diagnoses, symptoms, allergies, patient, doctor): identical after
  lowercasing, collapsing whitespace and trimming surrounding punctuation. No substring matching —
  use alternatives in the truth file instead.
- **OCR critical tokens**: each truth value must appear in the OCR text as a whole token
  (`"5"` is not found in `"500"` or `"5.1"`), counted as many times as it appears in the transcription.

## What is reported

Per document and in aggregate:

- **OCR**: critical-token accuracy by category (medicine name, dosage, frequency, duration, lab
  name, lab value, header, date), CER, word substitutions ("written X, read Y"), and lines in
  the OCR output that do not exist on the page.
- **Extraction**: TP/FP/FN, precision and recall per field; every false positive, false negative
  and wrong value by name; **unflagged errors** (wrong or extra values with `needs_review=false`
  — the dangerous kind); placement errors (a correct value in the wrong field); grounding failures;
  document-type accuracy; crashes.
- **Reliability**: non-documents (white page, noise, dust, dark object, blurred/dark/table photos)
  must return `unreadable` with no entities; the hallucination detector is exercised by feeding
  each page its true text plus one invented line (OCR stubbed, so this measures the check, not the model).

## Other scripts

| Script | Purpose |
|---|---|
| `model_selection/ocr_candidates.py` | OCR model comparison (Tesseract, GOT-OCR2, GLM-OCR, PaddleOCR-VL, khedim TrOCR, Qwen3-VL); `--rescore` recomputes from saved outputs |
| `model_selection/prompt_and_grounding_probe.py` | prompt variants against language-prior corrections; line-box (grounded) OCR feasibility |
| `model_selection/extraction_candidates.py`, `llm_extraction_probe.py` | GLiNER sizes; a generative LLM as extractor |
| `tools/profile_pipeline.py` | per-stage latency and memory over repeated requests |
| `tools/make_handwritten_fixtures.py`, `make_unreadable_fixtures.py` | regenerate dev/control images |
| `tools/make_heldout_fixtures.py` | rendered the frozen held-out set (re-running it changes the manifest) |

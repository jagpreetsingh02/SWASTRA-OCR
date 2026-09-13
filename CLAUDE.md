# CLAUDE.md — MediKiosk OCR

## Project Context

This repository is a standalone OCR and medical-document extraction engine for **MediKiosk**.

MediKiosk is a healthcare assistant designed to maintain a continuous patient health history. Patients can provide information through conversation and medical documents, while doctors review and verify important information before it becomes part of the longitudinal record.

The main MediKiosk application already handles areas such as:
- patient and doctor workflows
- longitudinal patient history
- provenance and source tracking
- physician verification
- red-flag screening
- FHIR/export workflows
- database persistence

This repository should **not recreate those systems**.

Its only responsibility is to turn a medical document into reliable, structured information that the main MediKiosk application can later consume.

---

## Core Goal

Keep the OCR system small, understandable, testable and reliable.

The intended flow is:

```text
Medical document
    ↓
Preprocessing
    ↓
OCR
    ↓
Raw text
    ↓
Local medical-information extraction
    ↓
Structured JSON
    ↓
Returned to MediKiosk for human verification
```

The system should support both:

- printed medical documents
- handwritten medical documents / prescriptions

The final output should make it easy for the main MediKiosk application to review, verify and store the extracted information.

---

## Design Philosophy

Prefer a **simple architecture that works well** over a complicated architecture with many backends, fallback chains and routing layers.

Do not add complexity unless testing shows that it solves a real problem.

Each major responsibility should stay clear:

1. preprocess the input
2. read the document
3. extract useful medical information
4. validate the output
5. expose a clean interface for integration

The codebase should be easy for another engineer to understand quickly.

---

## Scope of This Repository

This repository may contain:

- document/image preprocessing
- OCR model inference
- handwritten and printed-text recognition
- local transformer/neural-network based extraction
- structured output schemas
- confidence/error reporting
- evaluation and regression tests
- a small API or callable interface for future MediKiosk integration

It should not contain:

- patient authentication
- Supabase/Postgres logic
- longitudinal medical-record logic
- doctor dashboards
- frontend code
- FHIR
- ABHA
- red-flag decision logic
- permanent clinical storage
- physician confirmation workflows

Those remain responsibilities of the main MediKiosk repository.

---

## Expected Output

The exact schema can evolve, but the result should conceptually provide:

```json
{
  "raw_text": "...",
  "document_type": "...",
  "confidence": null,
  "entities": {
    "patient_name": null,
    "date": null,
    "doctor_name": null,
    "medications": [],
    "dosages": [],
    "frequencies": [],
    "diagnoses": [],
    "symptoms": [],
    "tests": [],
    "test_results": [],
    "allergies": []
  }
}
```

Do not fabricate information that is not present in the source document.

Unknown or uncertain values should remain unknown/uncertain.

---

## Model Selection

Do not assume that an existing OCR model is correct simply because it loads successfully.

A previous handwritten prescription model produced fluent but input-disconnected outputs, so every model must be evaluated against real test documents before being trusted.

Choose models based on actual performance on this use case.

Prefer local inference where practical, especially for the medical-information extraction stage, but do not force a model that is unsuitable for the available hardware.

---

## Testing Priorities

Testing is a core part of this repository.

At minimum, cover:

- clean printed reports
- degraded/scanned reports
- handwritten prescriptions
- mixed printed + handwritten documents
- blank or unreadable input
- different documents producing meaningfully different outputs
- hallucination resistance
- medicine name preservation
- dosage/frequency preservation
- numeric lab-value preservation
- stable structured JSON output
- model/inference failure handling

Where possible, evaluate both OCR quality and medical-entity extraction quality.

---

## Integration Boundary

The future MediKiosk integration should be simple.

MediKiosk should send a document to this engine and receive a structured result.

This repository should not need to understand how MediKiosk stores the result afterwards.

Keep the integration contract stable and model-independent so the OCR or extraction models can be replaced later without changing the main application.

---

## Engineering Guidance

- Keep files and responsibilities small.
- Avoid unnecessary abstractions.
- Avoid duplicated pipelines.
- Prefer one obvious execution path.
- Use typed schemas for input/output.
- Keep model-specific code isolated.
- Fail clearly instead of silently returning fake results.
- Preserve raw OCR text alongside structured extraction.
- Never treat AI extraction as verified medical truth.
- Do not make diagnostic or treatment decisions.

When uncertain about implementation details, inspect the code, evaluate options and choose the simplest design that satisfies the goal.

---

## Current Implementation (keep in sync with the code)

One execution path, one module per responsibility (`medikiosk_ocr/`):

```text
preprocess.py  bytes -> pages (images or PDF text layer); blank pages never reach OCR
ocr.py         page image -> text + token probability per character      (all OCR-model code: Qwen3-VL-2B)
validate.py    is the text plausible for the image? withhold unsupported text;
               later: flag values that look misread (never corrects them)
extract.py     text -> grounded entities                                  (all extraction-model code: GLiNER-BioMed + patterns)
pipeline.py    runs the above; enforces value.text == raw_text[start:end]; never raises
api.py         POST /v1/extract, GET /health
```

- The integration contract is `medikiosk_ocr/schema.py`, published as `contract/extraction_result.schema.json`
  (schema_version 2.2). Observations measured on the patient (BP, pulse, SpO2) are `vitals`, never
  `test_results`; a panel heading is `panels`, its analytes are the rows in `test_results`.
  `document_type` is decided from document-level evidence only, never from the
  entities found, and it routes meaning: medicines a bill or a package insert merely names go to
  `medication_mentions`, never to `medications`, which is reserved for what a document presents as
  prescribed to a patient. The conceptual "Expected Output" above maps to it: `confidence` is split into
  `ocr_confidence` (generative token probability) and per-value `extractor_score`, and every value
  carries offsets, page, `needs_review` and `review_reasons`. `verification_required` is always true.
- Evaluation: `eval/run.py`. `eval/dev` may be used for tuning; `eval/heldout` (frozen by
  `MANIFEST.sha256`) and `eval/real_world` must never be. A document used to fix a bug moves to `eval/dev`.
- Tests: `tests/unit` (no weights), `tests/integration` (GLiNER), `tests/e2e` (both models).

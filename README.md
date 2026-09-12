# MediKiosk OCR

Standalone engine that turns a medical document (photo, scan or PDF; printed or handwritten) into
raw text plus structured, **unverified** medical information for MediKiosk to show a person for
verification.

```
document ─► preprocess ─► OCR (Qwen3-VL-2B) ─► page checks ─► extraction (GLiNER-BioMed + patterns)
                                                   │                          │
                                     withhold text the page             review flags for values
                                     does not support                   that look misread
                                                   └──────────► grounded JSON (ExtractionResult 2.0) ─► MediKiosk
```

It does not store anything, authenticate anyone, make clinical decisions, or know about patients,
FHIR, ABHA or red flags. See `CLAUDE.md` for the boundary.

---

## Quick start

```bash
# 1. environment
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. optional local settings (only needed for gated/private Hugging Face repos; these models are public)
cp .env.example .env        # then put HF_TOKEN=... in .env if you need one. .env is git-ignored.

# 3. run the server (it serves BOTH the API and the test page)
.venv/bin/uvicorn medikiosk_ocr.api:app --host 127.0.0.1 --port 8000

# 4. open the test bench IN THE BROWSER at the address the server prints
open http://127.0.0.1:8000
```

> **Open the page from the server, not from the file system.** `medikiosk_ocr/static/index.html` posts to
> `v1/extract` relative to the page it is served from. Opening it with VS Code Live Server (or as a
> `file://` URL) sends the upload to that server instead, which replies with an HTML page — the
> `SyntaxError: Unexpected token '<' … is not valid JSON` error. The page now detects this and tells you.
> One FastAPI process serves `GET /`, `GET /health` and `POST /v1/extract`, so there is no second port and no CORS.

```bash
curl http://127.0.0.1:8000/health                          # models, device, readiness (never the token)
curl -F "file=@prescription.jpg" http://127.0.0.1:8000/v1/extract
```

```python
from medikiosk_ocr import extract_document
result = extract_document(open("prescription.heic", "rb").read())   # -> ExtractionResult
```

Hardware: developed and measured on Apple M5 / 16 GB (MPS). Both models stay loaded: ~4.7 GB of
GPU memory for Qwen3-VL-2B (bf16) plus ~1.8 GB for GLiNER-BioMed-large on CPU. CUDA is used
automatically if present; CPU-only works but OCR speed on CPU has not been measured.

---

## Integration contract

`POST /v1/extract` — `multipart/form-data`, field `file`.

| HTTP | When | Body |
|---|---|---|
| 200 | any uploaded file, including unreadable or invalid ones | `ExtractionResult`; check `status` |
| 413 | upload over 25 MB | `ExtractionResult` with `status=failed`, `error.code=file_too_large` |
| 422 | malformed request (no `file` field) | `ExtractionResult` with `status=failed`, `error.code=invalid_request` |

`GET /health` → `{"status", "schema_version", "engine", "models_loaded": {"ocr", "extractor"}, "ready", "warm_up_error"}`.

The contract is [`medikiosk_ocr/schema.py`](medikiosk_ocr/schema.py), published as
[`contract/extraction_result.schema.json`](contract/extraction_result.schema.json) (a unit test fails if
they diverge). Nothing in it names a model.

### `ExtractionResult` (schema_version `2.0`)

| Field | Meaning |
|---|---|
| `schema_version` | `"2.0"` |
| `verification_required` | always `true` — nothing here is approved medical information |
| `status` | `ok` · `low_confidence` (read, but something is doubtful — see `warnings`) · `unreadable` (blank, nothing legible, or text withheld as unsupported; no entities) · `failed` (see `error`) |
| `document_type` | `prescription` · `lab_report` · `discharge_summary` · `other_medical` · `unknown` |
| `raw_text` | everything read, pages joined by a blank line; kept even when extraction fails or text is withheld |
| `ocr_confidence` | mean generative token probability over OCR'd characters; `null` if no page was OCR'd. **Not a correctness score** |
| `entities` | `patient_name`, `doctor_name`, `date`, `medications[]` (`name`, `dosage`, `frequency`, `duration`, `source_line`), `dosages[]`/`frequencies[]` (the same objects as in `medications`), `diagnoses[]`, `symptoms[]`, `tests[]` (mentioned without a result), `test_results[]` (`name`, `value`, `unit`, `reference_range`, `source_line`), `allergies[]` |
| `pages[]` | `index`, `source` (`text_layer` · `ocr` · `text`), `status` (`ok` · `blank` · `no_text` · `suspect`), `lines[]` (`text`, `start`, `end`, `ocr_confidence`, `review_reasons`) |
| `warnings` | human-readable reasons for doubt, with page numbers |
| `error` | `{code, message}` when `status=failed` |
| `engine`, `timings_ms` | diagnostics only; do not branch on them |

Every value is an **Entity**:

```json
{"text": "HbAlc", "start": 131, "end": 136, "page": 0, "method": "pattern",
 "ocr_confidence": 0.999, "extractor_score": null,
 "needs_review": true, "review_reasons": ["'HbAlc' may be a misreading of 'HbA1c' (easily confused characters)"]}
```

| Error code | Meaning |
|---|---|
| `empty_file` | no bytes, or a PDF with no pages |
| `unsupported_format` | not a readable image/PDF: corrupt, encrypted, unknown type, or not page-shaped (< 32 px or > 20:1) |
| `file_too_large` | > 25 MB, or an image over 80 megapixels |
| `too_many_pages` | > 10 pages (PDF or multi-page TIFF) |
| `ocr_failed` | the OCR model failed on a page (message names the page; earlier pages are returned) |
| `extraction_failed` | the extraction model failed, or returned a value that is not a verbatim span of `raw_text` |
| `internal_error` | an unexpected bug — reported, never hidden as an empty result |
| `invalid_request` | HTTP only: malformed request |

### Guarantees MediKiosk can rely on

1. **Grounding, enforced at runtime.** For every value, `value.text == raw_text[value.start:value.end]`.
   The pipeline checks this after extraction; if any value fails, or comes from text that was withheld,
   the whole document returns `status=failed` / `extraction_failed`. Values are never normalised,
   corrected, expanded ("PCM" stays "PCM") or inferred. Unknown means `null` / `[]`.
2. The guarantee is about the **OCR text**, not the paper: if OCR misread the page, the value
   faithfully repeats the misreading (and may be flagged — see below).
3. **Never raises.** Bad files, decoder errors, OCR crashes, extraction crashes and bugs all come back
   as `status=failed` with a code (`tests/unit/test_pipeline_failures.py`, `tests/unit/test_api.py`).
4. **`needs_review` is per value and independent of `status`.** `status=ok` does not mean every value
   is trustworthy, and `needs_review=false` does not mean verified. No threshold approves anything.

### Changes from 1.0

`confidence` (a single number mixing OCR probability and extractor score) was replaced by
`ocr_confidence`, `extractor_score` and `method`; values gained `page` and `review_reasons`;
`TestResult.value` is now the number only with a separate `unit`; pages gained `status`;
`verification_required` was added; error codes `internal_error` and `invalid_request` were added.

---

## How it works

| Step | File | What happens |
|---|---|---|
| Preprocess | `preprocess.py` | PDF: digital pages use their text layer (exact, no OCR); scanned pages — including scans that carry an embedded OCR text layer, which is not trusted — are rendered at 200 dpi, capped at 3000 px. Images: JPEG decoded at reduced size, every frame of a multi-page TIFF, HEIC/HEIF, EXIF rotation, 16/32-bit greyscale rescaled, transparency → white, downscaled to ≤ 2400 px. Limits refuse bombs and non-page shapes. Blank pages are detected here and never sent to OCR. |
| OCR | `ocr.py` | Qwen3-VL-2B transcribes each page (≤ 1.4 MP) with greedy decoding and a "copy exactly, add nothing" prompt; the probability of each emitted token is recorded. "No readable text" replies become empty text. |
| Page checks | `validate.check_page` | Compares the text with the image: no visible lines of writing but text returned → the page is `suspect` and its text withheld from extraction; far fewer lines read than visible, or ≥ 2 more (≥ 25 %) → a doubt attached to every value on the page; lines repeated 3+ times (generation loops), lines in an unexpected script, and model commentary ("Here is the transcription:") → withheld. |
| Extraction | `extract.py` | GLiNER-BioMed labels drugs, diseases, symptoms, lab/imaging tests and allergens (spans of the text only). Patterns take dose units, dosing codes (OD/BD/TDS/HS/SOS/1-0-1/q6h…), dosing phrases, durations, dates, lab values/units/ranges and `Dr …`/`Patient …` headers. Section labels (`Dx:`, `Imp:`, `c/o`, `Allergy:`) route values. A model-found drug becomes a medication only with prescription context on its line; a lab-shaped row is a result even when the model calls the analyte a drug or does not recognise it. |
| Value checks | `validate.flag_entities` | Adds `review_reasons` (never edits values) for: lab names one confusable character away from a known analyte (`HbAlc`→`HbA1c`), doses with letters for digits (`SMG`), a dose followed by a stray capital (`400 D` from `40 OD`), dosing codes containing letters (`1-O-1`), dates that are impossible, in the future, 2-digit or `|`-separated, lab values > 10× outside their reference range (decimal slips), low OCR token probability, low extractor score, pattern-only names, and page-level doubts. |
| Grounding + status | `pipeline.py` | Enforces grounding; `low_confidence` if any page/line doubt, withheld text, a line with mean token probability < 0.60, document mean < 0.80, or truncated OCR output. |
| Interface | `api.py` | Upload size gate before parsing, one document processed at a time (`MEDIKIOSK_OCR_MAX_CONCURRENT`), models warmed at start-up (`MEDIKIOSK_OCR_PRELOAD=0` to disable). |

### Confidence — what the numbers are

| Number | Definition | What it is not |
|---|---|---|
| token probability | softmax of the float32 logits at each step, taken after all built-in logits processors; under greedy decoding the maximum is the probability of the token emitted (verified: emitted token = argmax at every step) | not a sequence score, not calibrated |
| per character | each character inherits the probability of the token that produced it | |
| `Line.ocr_confidence` | mean over the line's non-space characters (a single doubtful character is diluted) | |
| `ExtractionResult.ocr_confidence` | mean over OCR'd alphanumeric characters | |
| `Entity.ocr_confidence` | lowest character probability inside the value; `null` for text-layer or typed text | not the probability the value is right |
| `Entity.extractor_score` | GLiNER span score when `method=model`; `null` when `method=pattern` | not a probability of correctness |
| `needs_review` | `true` iff `review_reasons` is non-empty. Triage thresholds: token probability < 0.80, extractor score < 0.60 — heuristics for "look at this first", never approval | `false` ≠ verified |

What it catches and misses, measured: handwritten *Augmtin* read as *Augmentin* came from token `ment`
at p = 0.31 → flagged. `HbA1c` read as `HbAlc` came from token `Al` at **p = 0.999** (also at full
resolution and on a line crop) → the probability says nothing; the lexicon check catches it instead.
A misreading that forms another plausible value — `5 mg`→`50 mg`, `OD`→`BD`, `1-0-1`→`1-1-1`,
`1.15`→`1.1` — is undetectable from text and model probabilities alone. That is what the mandatory
human verification is for.

---

## Supported input

| Format | Notes |
|---|---|
| PDF | digital text layer used directly; scanned pages OCR'd; ≤ 10 pages; corrupt/encrypted → `unsupported_format` |
| JPEG, PNG, WEBP, BMP, GIF | EXIF rotation applied; ≤ 80 MP decoded |
| TIFF | every page (≤ 10); 16-bit and 32-bit greyscale scans rescaled |
| HEIC / HEIF | via `pillow-heif` (iPhone photos) |

Limits: 25 MB upload, 80 megapixels, 10 pages, 32 px minimum side, 20:1 maximum aspect ratio.

---

## Model selection

`eval/model_selection/ocr_candidates.py --rescore` (strict, count-aware whole-token matching; 13 dev pages):

| Engine | Printed (7) | Handwritten (5*) | Mixed (1) | s/page (M5) | Output on non-documents | Verdict |
|---|---|---|---|---|---|---|
| **Qwen3-VL-2B-Instruct** | 0.98 | **0.95** | **1.00** | 10.5 | white page, noise: 7 chars ("1. 100%") | **chosen** |
| GLM-OCR (0.9B) | 1.00 | 0.90 | 0.77 | 13.9 | **1,115 chars of invented Chinese text on noise** | rejected |
| GOT-OCR2 | 0.99 | 0.73 | 0.92 | 4.7 | **1,024 chars ("100\n100…") on a blurred photo** | rejected |
| Tesseract 5 | 0.94 | 0.16 | 0.62 | 0.8 | nothing | rejected (handwriting) |
| khedim/Medical-Prescription-OCR | 0.00 | 0.00 (1*) | — | 0.3 | **"date: 2024-12-16" for blank, noise and every line crop** | rejected |
| PaddleOCR-VL-1.6 | — | — | — | ~0.7 tok/s | — | rejected on this hardware |

\*khedim was benchmarked before the generated handwriting existed (1 handwritten page). Qwen, GLM,
Tesseract and khedim saw only the white-page and noise controls; GOT saw all five. The Qwen prompt
in this benchmark is shorter than the production prompt; production OCR is measured by `eval/run.py`.

- **khedim TrOCR** (MediKiosk's previous model) outputs text unrelated to the input.
- **GLM-OCR** read "Telma 40 OD" as "Telma **400** D", dropped a printed header, and invented text on noise.
- **GOT-OCR2** dropped lines on degraded and photographed prescriptions and looped on a blurred photo.
- **Tesseract** never invents text but cannot read handwriting.
- **PaddleOCR-VL-1.6** runs at ~0.7 tokens/s on Apple MPS (minutes per page); worth re-testing on CUDA.

Experiments that did **not** change the design (reports in `eval/model_selection/reports/`):

- **Stricter prompts** against language-prior "corrections": identical critical-token accuracy (173/177)
  and substitution count (9) on dev; *Augmtin* became *Augmin* instead of *Augmentin* — still wrong. Kept the production prompt.
- **Grounded OCR** (Qwen returning a box per line, to check each line against the ink): valid JSON and
  plausible boxes, but 44.8 s per page vs 13 s. Too slow on this hardware.
- **Tesseract as a second reader** to confirm lines: it shares the `HbAlc` misreading, misreads what Qwen gets
  right (`SOOMG`, `SMG` at confidence 95), cannot read handwriting, and an invented "Tab Warfarin 5 mg OD"
  line still matched 60–80 % of words already on a prescription. Not a useful witness; not added.
- **Generative extraction** (Qwen as a JSON extractor): values put in wrong fields, a duration copied onto
  other medicines, 10–24 s per document. GLiNER + patterns kept.
- **float16 instead of bfloat16** (`eval/model_selection/dtype_probe.py`): byte-identical text on four dev
  pages and no speed-up (bf16/fp16 = 0.99). Kept bfloat16.
- **GLiNER labels**: adding "Imaging test" found `chest X-ray` with no new false positives on dev; adopted.
  "Medical investigation" was noisy; rejected.

---

## Testing

```bash
.venv/bin/pytest tests/unit            # no model weights; ~6 s
.venv/bin/pytest tests/integration     # real GLiNER, OCR stubbed; ~1 min
.venv/bin/pytest tests/e2e             # both real models; ~3 min
.venv/bin/pytest                       # everything
```

| Folder | Covers |
|---|---|
| `tests/unit` | every input format, EXIF, 16-bit, multi-page TIFF, scanned PDF with a text layer, huge PDF pages, bombs, truncated/corrupt/unknown files, non-page shapes; page checks (no writing, missing/extra lines, loops, script, commentary); value checks (confusable lab names, `SMG`, `400 D`, `1-O-1`, dates, decimal slips); pipeline failures with stubbed models (OCR crash on page 2, extraction crash, ungrounded extractor output, decoder exception, internal bug, blank/junk/invented text); schema and OpenAPI contract; HTTP behaviour (422/413/200); strict metrics; held-out manifest |
| `tests/integration` | grounding and honest scores on every dev text; medicine/dose/frequency/duration and lab value/unit/range preservation; regressions (Vitamin D row, `Pt` header without colon, whole diagnosis items, imaging tests, misread `HbAlc` row, non-medicines, two medicines per line); multi-page digital PDF and TIFF page provenance; low token probability, missing/invented lines and loops through the whole pipeline |
| `tests/e2e` | real models on printed, degraded, photographed and synthetic-handwriting documents (exact medicines and doses); misread values must be flagged; HEIC; scanned 2-page PDF; unreadable photos and noise |

### Results

**175 passed, 0 failed** in 3 m 36 s (2026-09-12, Apple M5 / 16 GB): 120 unit (~6 s), 40 integration
(~26 s), 15 end-to-end with the real models (~3 min).

The suite is meant to fail when behaviour regresses, not to decorate a green badge. Every bug found in
this pass has a test that fails without its fix: the pypdfium2 API change (scanned-PDF detection), the
page separator left in `raw_text` after an OCR failure, 16-bit scans read as blank, dropped TIFF pages,
degenerate image dimensions crashing the pipeline, ungrounded extractor output, `HbAlc` extracted as a
medicine, `Vitamin D (25-OH)` as a medicine, `SpO2` as a lab result, and a single invented line passing
unflagged. One test was itself wrong and was fixed: the `/health` check asserted `ready is False`, which
only held when it ran alone — it now asserts that `/health` does not change what is loaded.

---

## Evaluation

`eval/run.py` — see [`eval/README.md`](eval/README.md) for splits, truth format and strict matching.

```bash
.venv/bin/python eval/run.py          # writes eval/reports/SUMMARY.md with every document and every error
```

Measured 2026-09-12 on Apple M5 / 16 GB. Full per-document detail, with every error named and whether
it was flagged, is in `eval/reports/SUMMARY.md`.

| Split | Mode | Precision | Recall | Unflagged errors | Ungrounded | Crashes | Critical OCR tokens | CER | Invented lines | s/file |
|---|---|---|---|---|---|---|---|---|---|---|
| dev (16 docs, **tuned on**) | text | 0.996 | 1.000 | 0 | 0 | 0 | — | — | — | 0.3 |
| dev (16 files, **tuned on**) | OCR | 0.978 | 0.978 | **0** | 0 | 0 | 0.982 | 0.005 | 0 | 9.1 |
| **held-out (9 docs, never tuned on)** | text | **0.956** | **0.901** | 7 | 0 | 0 | — | — | — | 0.3 |
| **held-out (11 files, never tuned on)** | OCR | **0.947** | **0.907** | 8 | 0 | 0 | **1.000** | 0.020 | 0 | 12.9 |
| real_world | — | — | — | — | — | — | — | — | — | — |

**Every clinically critical token on the held-out images was read exactly** (1.000: medicine names,
doses, frequencies, durations, lab names, lab values, headers, dates); its extraction misses are
formatting gaps, listed under Limitations. Dev OCR by category: dosage 38/38, frequency 40/40,
duration 26/26, header 12/12, lab value 25/25, medicine name 39/40, date 15/16, lab name 20/22
(the two misses are `HbA1c`→`HbAlc`, both flagged).

**Distinctness:** every document's OCR text is closest to its own source (dev 16/16, held-out 11/11),
so different documents do not collapse into one memorised output. **Invented lines:** 0 in both splits —
no OCR line is absent from the page.

**Reliability** (`eval/reports/reliability.json`): non-documents (white page, noise, dust, dark object,
blurred/dark/table photos) → 7/7 `unreadable` with no entities. Invented-line detector (OCR stubbed with
each page's true text plus one fabricated line): **19/23 detected, 0 false alarms** on clean text; the
4 misses are pages where the line estimator over-counts by one, so the extra line fits in its slack
(16 invented values unflagged there).

`real_world/` is empty: **no real document has been evaluated.** The workflow is ready
(`eval/real_world/README.md`, `truth_template.json`, `eval/run.py --split real_world`).

---

## Performance and resources

Measured with `eval/tools/profile_pipeline.py` (Apple M5 / 16 GB, 14 requests per run, before and after
this pass's changes).

| | before | after |
|---|---|---|
| printed page (mean of 9 runs of the same page) | 14.7 s | 13.0 s |
| handwritten page | 8.9 s | 7.4 s |
| digital PDF page (text layer, no OCR) | 1.12 s | 0.56 s |
| share of time in `model.generate` | 95.5 % | 96.6 % |
| model load at start-up (OCR + extractor) | 13.9 s + 11.2 s | 13.3 s + 10.2 s |
| peak process RSS | 3968 MB | 3753 MB |
| GPU (MPS) memory, start → after 14 requests | 4712 → 4716 MB | 4712 → 4716 MB |

**Generation is ~96 % of every page.** Everything else — decoding, blank check, line estimate, page
checks, GLiNER (0.23–0.40 s), value checks (< 1 ms), character-confidence mapping (< 20 ms) — is under
half a second combined. There is no meaningful speed-up left without changing the OCR model or
degrading quality, and the alternatives were measured and rejected (see Model selection). The
differences above are modest and partly run-to-run variance; what changed deliberately was:
token probabilities kept as device tensors instead of one GPU sync per token, JPEG decoded at reduced
size, PDF pages rasterised with a size cap, and both models loaded once and warmed at start-up.

**Resource behaviour:** both models stay resident (~4.7 GB GPU + ~3.8 GB RSS). Memory is flat across
repeated requests — no growth, no reloads. One document is processed at a time
(`MEDIKIOSK_OCR_MAX_CONCURRENT`, default 1), so concurrent uploads queue instead of multiplying memory;
the GPU cache is released if a generation fails. Expect ~13 s per photographed page and ~2 minutes for a
10-page PDF: HTTP clients need a long timeout.

---

## Known limitations

### Needs real-world data (not a code problem)

- **No real document has ever been read by this engine.** All handwriting is rendered from fonts, which
  is far easier than a doctor's hand. Nothing here predicts field accuracy. This is the one blocking
  gap, and it needs consented, de-identified samples, not more code.
- English/Latin script only. Hindi and other Indian-language documents are untested.

### Known code limitations (measured, unfixed by choice)

These come from the held-out run. They are **not fixed**, because tuning on held-out results would
destroy the only unbiased measurement in the repository; the documents stay in `heldout/` and the
fixes belong in a later pass, verified against a fresh held-out set.

- Reference ranges in **square brackets** (`SGPT (ALT) 64 U/L [7 - 56]`) are not captured — the pattern
  accepts `( )` or bare ranges. 6 rows in one document, 8 more in the merged two-page PDF.
- Unit `mill/cumm` is not in the lab-unit list, so that row's unit and range are missed.
- `BBF` (before breakfast) is not a known dosing code, and `2 tsp` yields dosage `2` (tsp is not a dose unit).
- A heading (`COMPLETE BLOOD COUNT`) and a parenthetical abbreviation (`ALT` from `SGPT (ALT)`) are
  listed as test mentions.
- `Allergies: None known` produces two allergy entries (`Allergies`, `None known`); only the second is flagged.
- A patient name can run into the next label (`Lakshmi Iyer IP` from `Patient: Lakshmi Iyer  IP No: 55392`).
- Two held-out "errors" are truth-annotation inconsistencies, not engine faults: `chest X-ray` is
  annotated as a test in dev and as nothing in held-out; and the merged two-page truth keeps page 1's
  `Reported` date while the engine prefers page 2's labelled `Sample Date`. Left as-is rather than
  editing a frozen truth file after seeing results.

### Limits of the checks themselves

- **Confident misreadings are undetectable from text.** `HbA1c`→`HbAlc` came at token p = 0.999 (the
  lexicon check catches this one); `5 mg`→`50 mg`, `OD`→`BD`, `1-0-1`→`1-1-1`, `1.15`→`1.1` form
  plausible values and nothing in this engine can catch them. Human verification is the control.
- **One invented line can still slip through** when the line estimator over-counts (4 of 23 measured);
  the invented text is then extracted with a page-level doubt only if the count exceeds the estimate.
- A wide two-column header that OCR reflows into two lines makes a page look longer than it is, so some
  correct pages come back `low_confidence` (safe direction, extra review effort).
- `document_type` is keyword-based. Line counting is coarse and tested on synthetic pages only.
- Values are grounded to the **OCR text**, not to the paper: a misread is faithfully preserved.
- Throughput: one document at a time. A 10-page PDF takes ~2 minutes; HTTP clients need a long timeout.

---

## Folder structure

```
medikiosk_ocr/
  schema.py        the integration contract (pydantic)
  preprocess.py    bytes -> pages; formats, limits, blank detection
  ocr.py           Qwen3-VL-2B; token probability per character          (all OCR-model code)
  validate.py      page checks; misreading flags                          (no model code)
  extract.py       GLiNER-BioMed + patterns -> grounded entities          (all extraction-model code)
  pipeline.py      the single execution path; grounding enforcement; statuses
  api.py           POST /v1/extract, GET /health, GET / (test bench)
  static/index.html
contract/extraction_result.schema.json
tests/unit  tests/integration  tests/e2e
eval/
  run.py  metrics.py  README.md
  dev/  heldout/ (MANIFEST.sha256)  real_world/ (README, truth_template.json)  controls/
  model_selection/   OCR/prompt/grounding/extractor comparisons + reports
  tools/             fixture generators, profiler
  reports/           generated
```

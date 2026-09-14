# Real-world validation set

Real, de-identified prescriptions from a third-party corpus — see `DATASET.md` for source, licence and
hashes. The images are **gitignored**: only truth files, the manifest and provenance are committed.

## Splits

| split | documents | may be used for | state |
|---|---|---|---|
| `real_world_dev` | 21 (`rw_001`–`rw_021`) | validation, and OCR **model selection** | evaluated — results in `eval/reports/` |
| `real_world_holdout` | 9 (listed in `manifest.json`) | ONE final check after a model is chosen and frozen | **untouched**: never staged, annotated, inspected or run |

The holdout pages are not in this directory at all — they exist only inside the source archive — so no
benchmark here can reach them even by accident. `manifest.json` records `runs_to_date: 0` for the
holdout; keep it that way until a model has been selected.

**Privacy:** `rw_013` carries a handwritten patient name despite the corpus being described as
de-identified. The image is gitignored like every other page, and no truth file records the name
(`patient_name` is null for all 21 pages).

> **Known incident — the name reached a public commit.** An earlier version of this file claimed the
> name "is not transcribed into any committed file". That was wrong. OCR transcribes what it sees, so
> the name appeared in `raw_text` for `rw_013` inside `eval/reports/real_world_ocr.json`, which was
> committed in `840ded5` and pushed to a public GitHub remote. The check that produced the false
> all-clear searched for the name as one word, but the model wrote it letter-spaced, so the search
> could not match. The working tree is now redacted, but **rewriting the pushed history is a separate,
> still-outstanding step** — until it is done, the name remains reachable in that commit.

**Rule this incident establishes:** any file holding verbatim OCR output of a real page is
patient data, regardless of what the source corpus calls itself. Such files stay local. Only
aggregates with no free text are committed — see the `model_selection_real_world` rules in
`.gitignore`. When checking for an identifier, normalise the text first (drop non-letters);
OCR output routinely mangles spacing.

## Before adding anything

Only add a document when all of these are true:

- [ ] The patient (or guardian) consented to its use for software validation.
- [ ] It is de-identified: patient name, phone, address, ID/UHID/ABHA numbers, faces and signatures
      are removed or replaced with fictitious values **on the image itself**, not only in the truth file.
- [ ] It has not been used to write or tune any rule, prompt or threshold in this repository.
- [ ] Files stay local to this evaluation; they are not uploaded to external services.

Check your organisation's data-governance rules before committing any real document to version control.

## Adding a document

1. Put the file here as `rw_<id>.<ext>` (or `rw_<id>_<variant>.<ext>` for several photos of one page).
2. Copy `truth_template.json` to `rw_<id>.truth.json` and fill it in from the **image**, value by value,
   exactly as written (see `eval/README.md`, "Truth format"). Do not look at the engine's output while
   annotating — it biases the truth towards what the model read.
3. Recommended: add `rw_<id>.txt`, an exact line-by-line transcription, to enable OCR scoring.
4. Have a second person check the truth file for clinically critical values (names, doses, frequencies, lab numbers).
5. Run: `.venv/bin/python eval/run.py --split real_world`

Results appear under "real_world" in `eval/reports/SUMMARY.md`, per document, with every error that
was not flagged for review listed by name.

If a real document reveals a bug and you change code because of it, move it to `eval/dev/` and note
why — from then on it is tuning data, not validation data.

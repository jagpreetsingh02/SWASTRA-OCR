# Real-world validation set

**Empty.** No real documents have been evaluated. Until this folder has samples, nothing in this
repository shows how the engine performs on real doctors' handwriting or real clinic paperwork.

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

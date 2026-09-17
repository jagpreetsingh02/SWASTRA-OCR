# Real-world validation set

Real external prescriptions require local privacy controls even when a source claims de-identification.
See `DATASET.md` for provenance and `manifest.json` for sampling and split metadata.

- `real_world_dev`: 21 pages already used for validation/model selection.
- `real_world_holdout`: 9 pages in the source archive only; never opened, annotated or evaluated in
  the privacy-remediation pass. Do not inspect them until the model decision is frozen.

Images, transcriptions and truth annotations are ignored by path and remain local. Preserve local
copies when re-cloning after the history rewrite. The source archive itself is also ignored.
Only reviewed metadata and numeric aggregates may be committed. Per-document outputs from
`eval/run.py` and `eval/model_selection/real_handwriting.py` stay local, including incomplete runs
and `eval/reports/SUMMARY.md`. Removing historical artifacts did not rerun or tune any benchmark.

A patient identifier previously reached a public commit through raw OCR output. The privacy pass
removes historical raw artifacts wholesale; working-tree redaction alone was insufficient. Old
GitHub objects may still require Support cleanup after branch rewriting. See `../../PRIVACY.md`.

Before using additional samples, obtain appropriate permission and remove identifiers from the
images themselves. Do not rely on searching for names: OCR can corrupt spelling and spacing.
Write local truth annotations from the image before examining model output, and arrange independent
review of critical values. Never treat AI-authored truth as clinician-verified ground truth.

The existing local workflow remains `.venv/bin/python eval/run.py --split real_world`.
Do not run it as part of privacy remediation. Documents used to tune the engine belong to a local
real-world development split, never an untouched holdout or the public synthetic fixture folders.

# Private evaluation artifacts

Raw real-world images, OCR text, per-document results and annotations stay local. A dataset's
"de-identified" label is not a guarantee: source images and OCR may still contain identifiers.
Only reviewed provenance metadata and numeric aggregate metrics belong in Git. Synthetic fixtures
in `eval/dev`, `eval/heldout` and `eval/controls` are separate; never move real data there to bypass
these protections. Real-world holdout images remain unopened and unevaluated during privacy work.

## Before committing

Enable the local index check once per clone:

```sh
git config core.hooksPath .githooks
python3 tools/check_privacy.py --all
python3 -m unittest discover -s tests/privacy -v
```

The hook reads **staged** contents and rejects protected paths even after `git add -f`, credential
patterns, and source text in numeric aggregate reports. GitHub Actions also checks the tracked tree.
Hooks can be bypassed and CI cannot undo an upload; `.gitignore`, local checks and careful review
are all needed. These checks are not proof that an arbitrary document is de-identified. Never paste
raw OCR into issues, pull requests, commit messages, screenshots or logs shared publicly.

Protected locations include `prescription-data/`, `eval/real_world*/` (except reviewed metadata),
real-world generated reports, the combined `eval/reports/SUMMARY.md`, dataset archives, uploads,
model caches and weights, `.env` and environment variants. Keep `HF_TOKEN=` empty in `.env.example`.
The four metadata exceptions are README.md, DATASET.md, manifest.json and truth_template.json;
review them manually and never add source transcriptions or identifying annotations to them.

## History cleanup, September 2026

The known incident involved a patient identifier in a historical real-world OCR report. Cleanup
removes the entire report history rather than relying on spelling or spacing of a name. It also
removes raw prescription screenshots, real-world annotations, detailed model reports (including an
incomplete report containing transcriptions), and the combined generated summary. The remaining
model comparison summary contains numeric metrics only. OCR/extraction/model-selection code,
synthetic fixtures and numeric scores are not changed or re-evaluated by this operation.

Old clones and recovery copies still contain old objects. Do not merge or push old history back;
re-clone after shared refs are rewritten. If local work must be recovered, transfer reviewed code
patches only. The operator's restricted recovery bundle is local, outside this repository, and
contains sensitive history; it is not a publishable backup. Retire it after recovery is no longer
needed. Local ignored source data is retained for the owner's evaluation workflow.

A rewritten branch does **not** prove deletion from GitHub caches, pull-request refs, forks or other
clones. Test old commit/blob URLs after pushing. If they remain accessible, the repository owner
must request GitHub Support sensitive-data cleanup and supply affected object IDs privately.
See the remediation handoff for observed remote status; do not claim complete deletion merely
because branch history is clean.

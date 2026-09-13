# Real-world validation corpus — provenance

The documents evaluated in this split are **not** part of this repository's history: they are real,
de-identified prescriptions published by a third party under a licence that permits evaluation. The
images themselves are deliberately **not committed** (see `.gitignore`); this file plus
`manifest.json` records exactly what was used so the run can be reproduced from the original source.

## Source

| | |
|---|---|
| Title | A Curated Bangladesh-Based Dataset of Handwritten and Printed Prescription Images |
| Repository | Mendeley Data, dataset `k62rfd23kz`, version 2 |
| URL | https://data.mendeley.com/datasets/k62rfd23kz/2 |
| Licence | **CC BY 4.0** (permits reuse and redistribution with attribution) |
| Archive | `Dataset.zip`, 21,829,651 bytes |
| SHA-256 | `ced4394523998386b274e549469c144fa9718402b4c52764552914182bb331db` (verified on download) |
| Contents | 200 prescription images, 200 YOLO label files (medicine-name boxes), `prescription_box_counts.csv` |

## De-identification

The publishers state that direct identifiers — patient and physician names, phone numbers, physician
degrees, signatures, chamber details and registration numbers — were removed before publication. Spot
checks on sampled pages show those regions blurred or cropped on the image itself. No attempt was made
to re-identify anyone, and no document was uploaded to any external service during evaluation.

## What this corpus is, and is not

- **Is:** 200 genuinely unseen, real, full-page handwritten prescriptions photographed in clinics —
  skewed, shadowed, some with objects resting on the page. Nothing here was used to write or tune any
  rule, prompt or threshold in this repository.
- **Is not:** a mixed corpus. There are no laboratory reports, no printed-only prescriptions, no
  table-heavy clinical documents. Every page is a handwritten prescription, so this validation speaks
  to that one category only.
- **Language:** Bangla, English and mixed. Medicine names are written in Latin script, but dosing is
  frequently written in Bangla numerals (`২+০+১` where this engine expects `1-0-1`) and advice lines
  are Bangla prose. This engine is documented as English/Latin only, so part of every page is outside
  the language it claims to support.

## Ground truth

The dataset ships **no transcriptions** — its labels are YOLO bounding boxes around medicine-name
regions (`classes.txt`), plus a CSV of box counts per page. Ground truth for this validation was
therefore written by hand from the images, before the engine was run on them, recording only what is
legibly present and leaving everything else `null`. Fields that could not be read with confidence —
most Bangla dosing and frequency — were left `null` rather than guessed.

**This truth is AI-authored on real handwriting and has not been checked by a clinician.** It is
weaker evidence than dataset-provided labels or a second human annotator, and the repository's own
protocol (`eval/real_world/README.md`, step 4) asks for a second person to check clinically critical
values. Treat the numbers accordingly.

## Reproducing

```bash
# 1. fetch and verify the source archive (21.8 MB)
curl -sL -o Dataset.zip \
  "https://data.mendeley.com/public-files/datasets/k62rfd23kz/files/28517918-d3a5-4416-a607-6fcf7529e289/file_downloaded"
shasum -a 256 Dataset.zip     # must equal the SHA-256 above

# 2. stage the sampled pages under the names recorded in manifest.json
# 3. run the frozen engine
.venv/bin/python eval/run.py --split real_world
```

The sample was drawn with a fixed seed (see `manifest.json`) *before* any annotation or OCR, so it is
reproducible and was not chosen by looking at which pages the engine happens to read well.

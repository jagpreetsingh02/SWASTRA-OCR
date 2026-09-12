# Claude Code Prompt — Build the Standalone MediKiosk OCR Engine

You are working inside a new repository that will become the standalone OCR and medical-document extraction engine for **MediKiosk**.

Read `CLAUDE.md` first and use it as the project boundary.

## Goal

Build a clean, minimal and independently testable pipeline that can accept printed or handwritten medical documents and return structured medical information.

The intended flow is:

```text
document
→ preprocessing
→ OCR
→ raw text
→ local medical-information extraction
→ validated structured JSON
```

The project should stay small and easy to understand.

Do not reproduce the complexity of the existing MediKiosk OCR implementation. Do not create many layers, routers, fallback systems or abstractions unless testing proves they are needed.

## What I want you to do

Start by inspecting the environment and deciding the simplest practical architecture.

Then:

- create the minimal project structure
- implement preprocessing for common image/PDF inputs
- choose and integrate a suitable OCR approach for printed and handwritten medical documents
- implement a local neural-network/transformer-based extraction stage that converts OCR text into structured medical data
- define clean typed input/output schemas
- preserve raw OCR text
- handle uncertainty and failures explicitly
- create a useful test/evaluation set structure
- add tests for printed, handwritten, degraded and failure cases
- expose one simple interface/API that MediKiosk can integrate with later
- document how to run and test the project

Use your own reasoning to choose libraries, models and internal structure.

Do not assume a model is good because it loads successfully. Test it against representative inputs. If a model produces hallucinated or input-disconnected text, reject it and explain why.

Prefer local inference where practical, especially for the structured medical extraction stage. If hardware limitations make a specific model unrealistic, choose a more suitable approach and explain the tradeoff.

## Important boundaries

This repository is only responsible for:

```text
document → OCR → structured medical information
```

Do not build:

- authentication
- database persistence
- Supabase/Postgres integration
- patient history
- doctor dashboards
- frontend
- FHIR
- ABHA
- red-flag logic
- permanent medical-record workflows

The main MediKiosk application will handle those later.

## Expected behavior

The final result should contain:

- raw OCR text
- useful confidence/error information
- structured medical entities such as medications, dosage, frequency, diagnoses, symptoms, tests, test results, dates, allergies, patient/doctor names when present
- no fabricated values
- clear handling of uncertain/unknown fields

Keep the output contract model-independent so OCR or extraction models can be changed later without affecting MediKiosk.

## Working style

Do not over-engineer.

Use your reasoning capacity to make good architectural and model choices instead of following an overly prescriptive file-by-file plan.

Before making major model choices, validate feasibility and expected hardware requirements.

Work toward a functional end-to-end pipeline first, then improve it based on tests.

At the end, report:

1. the final architecture
2. the models/libraries chosen and why
3. the folder structure
4. how the pipeline works end-to-end
5. test results
6. known limitations
7. the integration contract MediKiosk should use later

"""The integration contract MediKiosk depends on. A failure here means the contract changed:
update contract/extraction_result.schema.json deliberately (and the schema_version) or fix the code."""

import json

from medikiosk_ocr.api import app
from medikiosk_ocr.schema import ERROR_CODES, SCHEMA_VERSION, ExtractionResult, Status

from ..conftest import ROOT


def test_published_json_schema_matches_the_code():
    published = json.loads((ROOT / "contract" / "extraction_result.schema.json").read_text())
    assert published == ExtractionResult.model_json_schema(), (
        "Schema changed. Regenerate: .venv/bin/python -c \"import medikiosk_ocr.schema as s; print(s.json_schema())\" > contract/extraction_result.schema.json")


def test_top_level_shape_and_version():
    data = json.loads(ExtractionResult(status=Status.ok).model_dump_json())
    assert set(data) == {"schema_version", "verification_required", "status", "document_type", "raw_text", "ocr_confidence",
                         "entities", "pages", "warnings", "error", "engine", "timings_ms"}
    assert data["schema_version"] == SCHEMA_VERSION == "2.0"
    assert data["verification_required"] is True
    assert set(data["entities"]) == {"patient_name", "date", "doctor_name", "medications", "dosages", "frequencies",
                                     "diagnoses", "symptoms", "tests", "test_results", "allergies"}


def test_values_carry_provenance_and_honest_scores():
    schema = ExtractionResult.model_json_schema()["$defs"]
    assert set(schema["Entity"]["properties"]) == {"text", "start", "end", "page", "method", "ocr_confidence",
                                                   "extractor_score", "needs_review", "review_reasons"}
    assert "confidence" not in schema["Entity"]["properties"]  # no single number that mixes different things
    assert set(schema["TestResult"]["properties"]) == {"name", "value", "unit", "reference_range", "source_line"}
    assert schema["Status"]["enum"] == ["ok", "low_confidence", "unreadable", "failed"]
    assert set(schema["Page"]["properties"]["status"]["enum"]) == {"ok", "blank", "no_text", "suspect"}


def test_error_codes_are_documented_and_stable():
    assert set(ERROR_CODES) == {"empty_file", "unsupported_format", "file_too_large", "too_many_pages", "ocr_failed",
                                "extraction_failed", "internal_error", "invalid_request"}


def test_openapi_exposes_only_the_two_endpoints():
    spec = app.openapi()
    assert set(spec["paths"]) == {"/health", "/v1/extract"}
    op = spec["paths"]["/v1/extract"]["post"]
    assert "multipart/form-data" in op["requestBody"]["content"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ExtractionResult"}


def test_results_round_trip_through_json():
    result = ExtractionResult(status=Status.low_confidence, raw_text="x", warnings=["w"])
    assert ExtractionResult.model_validate_json(result.model_dump_json()) == result

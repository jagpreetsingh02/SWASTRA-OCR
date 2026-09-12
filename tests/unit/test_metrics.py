"""The evaluation's matching rules must be strict, or reported numbers mean nothing."""

import sys

import pytest

from ..conftest import ROOT

sys.path.insert(0, str(ROOT / "eval"))
import metrics  # noqa: E402
import run  # noqa: E402

from medikiosk_ocr.schema import DocumentType, Entities, Entity, ExtractionResult, Medication, Method, Status, TestResult  # noqa: E402


@pytest.mark.parametrize("pred,truth,match", [
    ("5", "500", False), ("500", "5", False), ("D", "OD", False), ("1.1", "1.15", False), ("1.15", "1.1", False),
    ("500MG", "500 mg", True), ("OD", "od", True), ("12/08/2026", "12/08/26", False),
])
def test_values_match_only_when_identical_apart_from_case_and_spacing(pred, truth, match):
    assert metrics.value_match(pred, truth) is match


def test_names_have_no_substring_matching_but_accept_listed_alternatives():
    assert not metrics.name_match("COPD", "Acute exacerbation of COPD")
    assert not metrics.name_match("Zerodol", "Zerodol SP")
    assert metrics.name_match("Mr. Vikram Rathod", ["Vikram Rathod", "Mr. Vikram Rathod"])


@pytest.mark.parametrize("token,text,count", [
    ("5", "500 mg", 0), ("5", "5.1 mg", 0), ("1.1", "1.15", 0), ("OD", "BOD OD", 1), ("500 mg", "500mg and 500 MG", 2),
    ("HbA1c", "HbAlc", 0),
])
def test_ocr_token_counting_is_whole_token(token, text, count):
    assert metrics.count_token(token, text) == count


def test_truth_files_with_unknown_or_missing_keys_are_rejected(tmp_path):
    bad = tmp_path / "x.truth.json"
    bad.write_text('{"document_type": "prescription", "medication": []}')
    with pytest.raises(ValueError):
        metrics.load_truth(bad)


def test_every_repository_truth_file_is_valid():
    files = list((ROOT / "eval").glob("*/*.truth.json"))
    assert len(files) >= 20
    for path in files:
        metrics.load_truth(path)


def test_heldout_set_is_unchanged_since_it_was_frozen():
    assert run.verify_heldout_manifest() == []


def ent(text, start, needs_review=False):
    return Entity(text=text, start=start, end=start + len(text), page=0, method=Method.pattern,
                  ocr_confidence=None, extractor_score=None, needs_review=needs_review)


def test_wrong_dose_counts_as_an_error_and_unflagged_errors_are_listed():
    raw = "Tab Telma 400 D"
    result = ExtractionResult(status=Status.ok, raw_text=raw, document_type=DocumentType.prescription, entities=Entities(
        medications=[Medication(name=ent("Telma", 4), dosage=ent("400", 10), source_line=raw)]))
    truth = {"document_type": "prescription", "patient_name": None, "doctor_name": None, "date": None,
             "medications": [{"name": "Telma", "dosage": "40", "frequency": "OD", "duration": None}],
             "test_results": [], "tests": [], "diagnoses": [], "symptoms": [], "allergies": []}
    score = metrics.score_extraction(result, truth)
    assert score["fields"]["medication"]["tp"] == 1
    assert score["fields"]["medication.dosage"] == {"tp": 0, "fp": 1, "fn": 1, "precision": 0.0, "recall": 0.0}
    assert score["fields"]["medication.frequency"]["fn"] == 1
    assert [e["got"] for e in score["unflagged_errors"]] == ["400"]


def test_value_predicted_in_the_wrong_field_is_a_placement_error():
    raw = "HbA1c 8.2 %"
    result = ExtractionResult(status=Status.ok, raw_text=raw, entities=Entities(
        medications=[Medication(name=ent("HbA1c", 0), dosage=ent("8.2 %", 6), source_line=raw)]))
    truth = {"document_type": "lab_report", "patient_name": None, "doctor_name": None, "date": None, "medications": [],
             "test_results": [{"name": "HbA1c", "value": "8.2", "unit": "%", "reference_range": None}],
             "tests": [], "diagnoses": [], "symptoms": [], "allergies": []}
    score = metrics.score_extraction(result, truth)
    assert any(e["placement"] == "test_result" for e in score["placement_errors"])

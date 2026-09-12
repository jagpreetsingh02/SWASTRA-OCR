"""Failures and non-documents through the pipeline, with the models stubbed. No weights needed:
every path here returns before real extraction runs (or extraction is replaced)."""

import pytest
from PIL import Image

from medikiosk_ocr import pipeline
from medikiosk_ocr.schema import DocumentType, Entities, Entity, Medication, Method, Status

from ..conftest import CONTROLS, DEV, dark_object_image, dust_image, image_bytes, noise_image

INVENTED = "Dr. A. Rao\nDate: 01/01/2026\nDx: Hypertension\nTab Amlodipine 5mg OD x 30 days\nTab Metformin 500mg BD"


def assert_structured_failure(result, code):
    assert result.status == Status.failed and result.error.code == code
    assert result.entities.is_empty() and result.verification_required is True
    assert result.timings_ms["total"] >= 0 and result.engine


@pytest.mark.parametrize("data,code", [(b"", "empty_file"), (b"GIF89a-not-really", "unsupported_format")])
def test_bad_input_returns_a_failed_result_without_calling_ocr(fake_ocr, data, code):
    calls = fake_ocr("unused")
    assert_structured_failure(pipeline.extract_document(data), code)
    assert calls == []


@pytest.mark.parametrize("size", [(2, 30000), (3000, 20)])
def test_degenerate_image_dimensions_are_rejected_not_crashed(fake_ocr, size):
    calls = fake_ocr("unused")
    assert_structured_failure(pipeline.extract_document(image_bytes(Image.new("L", size, 255))), "unsupported_format")
    assert calls == []


def test_unexpected_decoder_exception_is_a_structured_failure(fake_ocr, monkeypatch):
    fake_ocr("unused")
    monkeypatch.setattr(pipeline, "load_document", lambda data: (_ for _ in ()).throw(ValueError("decoder blew up")))
    assert_structured_failure(pipeline.extract_document(b"anything"), "unsupported_format")


def test_ocr_crash_is_reported_and_earlier_pages_are_kept(fake_ocr, monkeypatch):
    fake_ocr(["page one text is here and readable", RuntimeError("MPS backend out of memory")])
    monkeypatch.setattr(pipeline.validate, "check_page", lambda image, text, n: pipeline.validate.PageCheck())
    scan = Image.open(DEV / "prescription_scan.png")
    result = pipeline.extract_document(image_bytes(scan, "TIFF", save_all=True, append_images=[scan]))
    assert_structured_failure(result, "ocr_failed")
    assert "page 2" in result.error.message and "out of memory" in result.error.message
    assert result.raw_text == "page one text is here and readable" and len(result.pages) == 1


def test_extraction_crash_keeps_raw_text(fake_ocr, monkeypatch):
    fake_ocr((DEV / "prescription.txt").read_text())
    monkeypatch.setattr(pipeline.extract, "extract_entities", lambda *a, **k: (_ for _ in ()).throw(ValueError("tokenizer exploded")))
    result = pipeline.extract_document((DEV / "prescription_scan.png").read_bytes())
    assert_structured_failure(result, "extraction_failed")
    assert "METFORMIN" in result.raw_text and result.pages


def test_ungrounded_value_from_the_extractor_fails_the_document(fake_ocr, monkeypatch):
    fake_ocr((DEV / "prescription.txt").read_text())
    fabricated = Entity(text="WARFARIN", start=0, end=8, page=0, method=Method.model, ocr_confidence=0.99,
                        extractor_score=0.9, needs_review=False)
    monkeypatch.setattr(pipeline.extract, "extract_entities",
                        lambda *a, **k: (Entities(medications=[Medication(name=fabricated, source_line="")]), DocumentType.prescription))
    result = pipeline.extract_document((DEV / "prescription_scan.png").read_bytes())
    assert_structured_failure(result, "extraction_failed")
    assert "WARFARIN" in result.error.message and result.raw_text.startswith("SHRI VENKATESHWARA")


def test_a_bug_anywhere_becomes_internal_error_not_an_exception(fake_ocr, monkeypatch):
    fake_ocr("text")
    monkeypatch.setattr(pipeline, "is_blank", lambda image: 1 / 0)
    assert_structured_failure(pipeline.extract_document((DEV / "prescription_scan.png").read_bytes()), "internal_error")


def test_blank_page_skips_ocr_and_is_unreadable(fake_ocr):
    calls = fake_ocr("Tab Paracetamol 500 mg BD")  # what a hallucinating model might say
    result = pipeline.extract_document(image_bytes(Image.new("RGB", (1240, 1754), "white")))
    assert calls == [] and result.status == Status.unreadable and result.entities.is_empty()
    assert result.pages[0].status == "blank"


def test_tiny_junk_output_is_unreadable(fake_ocr):
    fake_ocr("1. 100%")
    result = pipeline.extract_document(image_bytes(Image.open(DEV / "prescription_scan.png")))
    assert result.status == Status.unreadable and result.entities.is_empty()


@pytest.mark.parametrize("name", ["no_document_table.jpg", "unreadable_blurred.jpg", "unreadable_dark.jpg"])
def test_unreadable_photos_never_yield_entities_even_if_ocr_invents_text(fake_ocr, name):
    fake_ocr(INVENTED)
    result = pipeline.extract_document((CONTROLS / name).read_bytes())
    assert result.status == Status.unreadable and result.entities.is_empty()


@pytest.mark.parametrize("make", [noise_image, dark_object_image, dust_image], ids=["noise", "dark_object", "dust"])
def test_fluent_text_for_a_non_blank_image_without_writing_is_kept_but_not_extracted(fake_ocr, make):
    calls = fake_ocr(INVENTED)
    result = pipeline.extract_document(image_bytes(make()))
    assert calls, "OCR must actually run: these images are not blank"
    assert result.status == Status.unreadable and result.entities.is_empty()
    assert result.raw_text == INVENTED and result.pages[0].status == "suspect"
    assert any("may be invented" in w for w in result.warnings)

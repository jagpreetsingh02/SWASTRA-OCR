"""Whole pipeline with real extraction and stubbed OCR: pages, provenance, statuses, review flags."""

import io

import pypdfium2 as pdfium
from PIL import Image

from medikiosk_ocr import pipeline
from medikiosk_ocr.schema import Status

from ..conftest import DEV, image_bytes

SCAN = Image.open(DEV / "prescription_scan.png").convert("RGB")
LAB = Image.open(DEV / "lab_report_scan.png").convert("RGB")


def assert_grounded(result):
    for v in result.entities.values():
        assert result.raw_text[v.start:v.end] == v.text
        page_start = next(l.start for l in result.pages[v.page].lines)
        page_end = result.pages[v.page].lines[-1].end
        assert page_start <= v.start and v.end <= page_end, f"{v.text!r} is not inside page {v.page}"


def test_digital_pdf_uses_its_text_layer_without_ocr(fake_ocr):
    calls = fake_ocr("unused")
    result = pipeline.extract_document((DEV / "lab_report.pdf").read_bytes())
    assert calls == [] and result.status == Status.ok and result.ocr_confidence is None
    assert result.pages[0].source == "text_layer" and len(result.entities.test_results) == 7
    assert all(v.ocr_confidence is None for v in result.entities.values())
    assert_grounded(result)


def test_multipage_digital_pdf_keeps_page_order_and_provenance(fake_ocr):
    fake_ocr("unused")
    merged = pdfium.PdfDocument.new()
    for name in ("prescription.pdf", "lab_report.pdf"):
        merged.import_pages(pdfium.PdfDocument((DEV / name).read_bytes()))
    buf = io.BytesIO()
    merged.save(buf)
    result = pipeline.extract_document(buf.getvalue())
    assert [p.index for p in result.pages] == [0, 1] and all(p.source == "text_layer" for p in result.pages)
    assert {m.name.page for m in result.entities.medications} == {0}
    assert {r.name.page for r in result.entities.test_results} == {1}
    assert result.raw_text.index("METFORMIN") < result.raw_text.index("Haemoglobin")
    assert_grounded(result)


def test_multipage_tiff_every_page_read_in_order_with_page_status(fake_ocr):
    calls = fake_ocr([(DEV / "prescription.txt").read_text(), (DEV / "lab_report.txt").read_text()])
    blank = Image.new("RGB", SCAN.size, "white")
    result = pipeline.extract_document(image_bytes(SCAN, "TIFF", save_all=True, append_images=[blank, LAB]))
    assert len(calls) == 2  # the blank middle page is not sent to OCR
    assert [(p.index, p.status) for p in result.pages] == [(0, "ok"), (1, "blank"), (2, "ok")]
    assert {m.name.page for m in result.entities.medications} == {0}
    assert {r.name.page for r in result.entities.test_results} == {2}
    assert any("Page 2 appears blank" in w for w in result.warnings)
    assert_grounded(result)


def test_low_ocr_token_probability_is_reported_per_value(fake_ocr):
    fake_ocr((DEV / "prescription.txt").read_text(), confidence=0.42)
    result = pipeline.extract_document(image_bytes(SCAN))
    assert result.status == Status.low_confidence and result.ocr_confidence == 0.42
    for m in result.entities.medications:
        assert m.name.ocr_confidence == 0.42 and m.name.needs_review
        assert any("token probability 0.42" in r for r in m.name.review_reasons)


def test_confident_ocr_with_consistent_text_is_ok_but_still_requires_verification(fake_ocr):
    fake_ocr((DEV / "prescription.txt").read_text(), confidence=0.99)
    result = pipeline.extract_document(image_bytes(SCAN))
    assert result.status == Status.ok and result.verification_required is True
    assert len(result.entities.medications) == 4


def test_far_fewer_lines_than_visible_marks_every_value_on_the_page(fake_ocr):
    fake_ocr("SHRI VENKATESHWARA POLYCLINIC\nTAB. METFORMIN 500MG 1-0-1 x 30 days")
    result = pipeline.extract_document(image_bytes(SCAN))
    assert result.status == Status.low_confidence and any("may be missing" in w for w in result.warnings)
    assert result.entities.medications and all(v.needs_review for v in result.entities.values())


def test_invented_extra_lines_on_a_real_page_raise_a_doubt_on_its_values(fake_ocr):
    lines = (DEV / "prescription.txt").read_text().strip().splitlines()
    invented = lines[:8] + ["TAB. WARFARIN 5MG OD x 10 days", "TAB. DIGOXIN 0.25MG OD x 30 days", "TAB. LASIX 40MG BD"] + lines[8:]
    fake_ocr("\n".join(invented))
    result = pipeline.extract_document(image_bytes(SCAN))
    assert result.status == Status.low_confidence
    warfarin = next(m for m in result.entities.medications if m.name.text == "WARFARIN")
    assert warfarin.name.needs_review and any("invented" in r for r in warfarin.name.review_reasons)


def test_repeated_line_loop_is_not_extracted_twice(fake_ocr):
    text = (DEV / "prescription.txt").read_text().rstrip() + "\n" + "\n".join(["TAB. AMLODIPINE 5MG OD x 30 days"] * 3)
    fake_ocr(text)
    result = pipeline.extract_document(image_bytes(SCAN))
    assert [m.name.text for m in result.entities.medications].count("AMLODIPINE") == 1
    assert any("repeatedly" in w for w in result.warnings)

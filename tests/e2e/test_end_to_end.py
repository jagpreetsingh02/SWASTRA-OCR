"""Real models, real files (dev + controls only). Slow: ~2-3 minutes, needs ~6 GB of model weights.

Asserts what matters clinically -- medicine names, doses and lab numbers surviving from pixels
to JSON exactly -- and the safety property for known misreadings: a value OCR gets wrong must
come back flagged for review. Handwriting fixtures are synthetic fonts; these tests guard
against regressions, they do not prove accuracy on real handwriting.
"""

import io

import numpy as np
import pillow_heif
import pytest
from PIL import Image

from medikiosk_ocr.pipeline import extract_document
from medikiosk_ocr.schema import DocumentType, Status

from ..conftest import CONTROLS, DEV, image_bytes


def table(result):
    return {m.name.text: (m.dosage and m.dosage.text, m.frequency and m.frequency.text) for m in result.entities.medications}


@pytest.mark.parametrize("name", ["prescription_scan.png", "prescription_degraded.png", "prescription_photo_handheld.jpg"])
def test_printed_prescription_medications_survive_exactly(name):
    result = extract_document((DEV / name).read_bytes())
    assert result.document_type == DocumentType.prescription
    assert table(result) == {"METFORMIN": ("500MG", "1-0-1"), "AMLODIPINE": ("5MG", "OD"),
                             "ATORVASTATIN": ("10MG", "HS"), "OMEPRAZOLE": ("20MG", "1-0-0")}


def test_degraded_lab_report_values_units_survive_and_a_misread_name_is_flagged():
    result = extract_document((DEV / "lab_report_degraded.png").read_bytes())
    rows = {r.value.text: r for r in result.entities.test_results}
    assert set(rows) == {"9.4", "8.2", "168", "1.1", "6.8", "214", "34"}
    hba1c = rows["8.2"]
    assert hba1c.unit.text == "%"
    assert hba1c.name.text == "HbA1c" or hba1c.name.needs_review, "a misread analyte name must be flagged"


def test_handwritten_language_prior_substitution_is_flagged_if_it_happens():
    result = extract_document((DEV / "prescription_handwritten.png").read_bytes())
    first = result.entities.medications[0]
    assert (first.dosage.text, first.frequency.text) == ("625", "BD")
    assert first.name.text == "Augmtin" or first.name.needs_review


@pytest.mark.parametrize("name,expected", [
    ("hw_rx_bradley.png", {"Azithral": ("500", "OD"), "Crocin": ("5ml", "TDS"), "Cetirizine": ("10mg", "HS")}),
    ("hw_rx_chalkboard.png", {"Omez": ("20", "OD"), "Dolo": ("650", "SOS"), "Montek LC": (None, "HS")}),
    ("mixed_printed_handwritten.png", {"ORS": ("1 sachet", "after each stool"), "Zinconia": ("5ml", "OD"), "Ondem": ("2ml", "SOS")}),
])
def test_synthetic_handwriting_medications_survive_exactly(name, expected):
    assert table(extract_document((DEV / name).read_bytes())) == expected


def test_heic_photo_gives_the_same_medications_as_the_jpeg():
    pillow_heif.register_heif_opener()
    jpeg = (DEV / "prescription_photo_handheld.jpg").read_bytes()
    heic = image_bytes(Image.open(io.BytesIO(jpeg)), "HEIF", quality=85)
    assert table(extract_document(heic)) == table(extract_document(jpeg))


def test_scanned_two_page_pdf_reads_both_pages_in_order():
    scan, lab = Image.open(DEV / "prescription_scan.png").convert("RGB"), Image.open(DEV / "lab_report_scan.png").convert("RGB")
    result = extract_document(image_bytes(scan, "PDF", save_all=True, append_images=[lab]))
    assert [(p.index, p.source, p.status) for p in result.pages] == [(0, "ocr", "ok"), (1, "ocr", "ok")]
    assert {m.name.page for m in result.entities.medications} == {0} and len(result.entities.medications) == 4
    assert {r.name.page for r in result.entities.test_results} == {1} and len(result.entities.test_results) == 7
    for v in result.entities.values():
        assert result.raw_text[v.start:v.end] == v.text


@pytest.mark.parametrize("name", ["unreadable_blurred.jpg", "unreadable_dark.jpg", "no_document_table.jpg"])
def test_unreadable_photos_are_unreadable_with_no_entities(name):
    result = extract_document((CONTROLS / name).read_bytes())
    assert result.status == Status.unreadable and result.entities.is_empty()


def test_noise_goes_through_the_real_ocr_model_and_yields_nothing():
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (1754, 1240, 3), dtype=np.uint8))
    result = extract_document(image_bytes(noise))
    assert result.status == Status.unreadable and result.entities.is_empty()


def test_different_documents_produce_different_outputs():
    a = extract_document((DEV / "hw_rx_bradley.png").read_bytes())
    b = extract_document((DEV / "hw_rx_chalkboard.png").read_bytes())
    assert a.raw_text != b.raw_text and set(table(a)).isdisjoint(table(b))

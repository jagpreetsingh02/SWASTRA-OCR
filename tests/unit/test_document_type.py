"""What kind of document is this? Decided from document-level evidence only, so no models are needed.

The type must never be inferred from the entities extracted later: a medicine name on a bill does not make
the bill a prescription. That is why `classify_document` takes nothing but the text.
"""

import pytest

from medikiosk_ocr.extract import classify_document
from medikiosk_ocr.schema import DocumentType

from ..conftest import DEV


@pytest.mark.parametrize("name,expected", [
    ("prescription.txt", DocumentType.prescription),
    ("prescription_handwritten.txt", DocumentType.prescription),
    ("lab_report.txt", DocumentType.lab_report),
    ("lab_haematology_table.txt", DocumentType.lab_report),
    ("discharge.txt", DocumentType.discharge_summary),
    ("discharge_copd.txt", DocumentType.discharge_summary),
    ("invoice_pharmacy_gst.txt", DocumentType.medical_invoice),
    ("pharma_info_minipress_letter.txt", DocumentType.pharmaceutical_information),
    ("nonmedical_invoice.txt", DocumentType.unknown),
])
def test_dev_documents_are_classified_from_their_own_evidence(name, expected):
    assert classify_document((DEV / name).read_text()).kind is expected


@pytest.mark.parametrize("text,not_kind", [
    ("Please bring the invoice with you to the front desk.", DocumentType.medical_invoice),
    ("The prescription was left on the kitchen table.", DocumentType.prescription),
    ("Composition varies between batches.", DocumentType.pharmaceutical_information),
    ("The report is ready for collection after five o'clock.", DocumentType.lab_report),
])
def test_a_single_keyword_does_not_decide_the_document_type(text, not_kind):
    assert classify_document(text).kind is not not_kind


def test_an_invoice_for_non_medical_goods_is_not_a_medical_invoice():
    text = ("SPARK ELECTRICALS\nGSTIN: 29XYZ1234K1Z0    Tax Invoice\nInvoice No: 44/2026\n"
            "1  LED Bulb 9W   HSN 8539   10   80.00   800.00\nGrand Total   800.00")
    assert classify_document(text).kind is DocumentType.unknown


def test_a_medicine_name_alone_does_not_make_a_prescription():
    assert classify_document("Metformin").kind is not DocumentType.prescription


def test_invoices_and_product_information_are_about_products_not_a_patient():
    for name in ("invoice_pharmacy_gst.txt", "pharma_info_minipress_letter.txt"):
        assert not classify_document((DEV / name).read_text()).about_a_patient


def test_prescriptions_discharge_summaries_lab_reports_and_notes_are_about_a_patient():
    for name in ("prescription.txt", "discharge.txt", "lab_report.txt", "probe_medication_formats.txt"):
        assert classify_document((DEV / name).read_text()).about_a_patient


def test_a_prescription_bundled_with_a_lab_report_can_still_prescribe():
    """Multi-page documents mix kinds; whichever one wins, a patient's medicines must not become mentions."""
    text = (DEV / "prescription.txt").read_text() + "\n\n" + (DEV / "lab_report.txt").read_text()
    assert classify_document(text).about_a_patient

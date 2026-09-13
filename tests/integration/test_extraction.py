"""Structured extraction on known text (OCR excluded), with the real GLiNER model. Dev data only."""

from pathlib import Path

import pytest

from medikiosk_ocr.pipeline import analyse_text
from medikiosk_ocr.schema import DocumentType, Method

from ..conftest import DEV


def run(name_or_text: str):
    text = (DEV / name_or_text).read_text() if name_or_text.endswith(".txt") else name_or_text
    return analyse_text(text)


def meds(result):
    return [(m.name.text, m.dosage and m.dosage.text, m.frequency and m.frequency.text, m.duration and m.duration.text)
            for m in result.entities.medications]


@pytest.mark.parametrize("path", sorted(DEV.glob("*.txt")), ids=lambda p: p.name)
def test_every_value_is_a_verbatim_span_with_page_and_honest_scores(path: Path):
    result = run(path.name)
    assert result.status.value in ("ok", "low_confidence")
    for v in result.entities.values():
        assert result.raw_text[v.start:v.end] == v.text and v.page == 0
        assert v.ocr_confidence is None                      # text input: nothing was OCR'd
        assert (v.extractor_score is None) == (v.method is Method.pattern)
        assert v.needs_review == bool(v.review_reasons)


# ------------------------------------------------------------------------------ preservation

def test_medicine_names_doses_frequencies_durations_are_preserved_exactly():
    assert meds(run("prescription.txt")) == [
        ("METFORMIN", "500MG", "1-0-1", "30 days"), ("AMLODIPINE", "5MG", "OD", "30 days"),
        ("ATORVASTATIN", "10MG", "HS", "30 days"), ("OMEPRAZOLE", "20MG", "1-0-0", "14 days"),
    ]


def test_handwritten_abbreviations_are_not_corrected_or_expanded():
    names = [m[0] for m in meds(run("prescription_handwritten.txt"))]
    assert names == ["Augmtin", "PCM", "Pantop", "Zerodol SP"]


def test_lab_rows_split_into_value_unit_and_range():
    rows = {r.name.text: (r.value.text, r.unit and r.unit.text, r.reference_range and r.reference_range.text)
            for r in run("lab_report.txt").entities.test_results}
    assert rows["TSH"] == ("6.8", "uIU/mL", "0.4 - 4.0")
    assert rows["HbA1c"] == ("8.2", "%", "4.0 - 5.6")
    assert len(rows) == 7


def test_table_layout_lab_rows_with_wide_spacing():
    rows = {r.name.text: (r.value.text, r.unit and r.unit.text, r.reference_range and r.reference_range.text)
            for r in run("lab_haematology_table.txt").entities.test_results}
    assert rows["Total Leukocyte Count"] == ("11200", "/cumm", "4000 - 11000")
    assert rows["Platelet Count"] == ("1.8", "lakhs/cumm", "1.5 - 4.5")


# ------------------------------------------------------------------------------ regressions

def test_vitamin_d_row_is_a_lab_result_not_a_medicine():
    result = run("lab_haematology_table.txt")
    assert result.entities.medications == []
    vit = [r for r in result.entities.test_results if r.name.text.startswith("Vitamin D")]
    assert len(vit) == 1 and (vit[0].value.text, vit[0].unit.text, vit[0].reference_range.text) == ("14.2", "ng/mL", "30 - 100")


def test_patient_header_without_a_colon():
    patient = run("rx_paediatric_opd.txt").entities.patient_name
    assert patient.text == "Kiran Patil" and patient.needs_review


def test_diagnosis_item_is_kept_whole_and_imaging_tests_are_mentions():
    result = run("discharge_copd.txt")
    assert [d.text for d in result.entities.diagnoses] == ["Acute exacerbation of COPD", "Type 2 respiratory failure"]
    assert [t.text for t in result.entities.tests] == ["chest X-ray"]


def test_misread_lab_name_is_a_flagged_lab_result_not_a_medicine():
    result = run("Rx\nHbAlc 8.2 % (4.0 - 5.6)")
    assert result.entities.medications == []
    (row,) = result.entities.test_results
    assert (row.name.text, row.value.text, row.unit.text) == ("HbAlc", "8.2", "%")
    assert row.name.needs_review and any("HbA1c" in r for r in row.name.review_reasons)


def test_non_medicines_are_not_medicines():
    result = run("probe_false_positives.txt")
    assert result.entities.medications == []
    rows = {r.name.text: (r.value.text, r.unit.text) for r in result.entities.test_results}
    assert rows.get("Random sugar") == ("210", "mg%") and "SpO2" not in rows
    assert result.document_type == DocumentType.other_medical


def test_medication_formats_including_two_medicines_on_one_line():
    assert meds(run("probe_medication_formats.txt")) == [
        ("Metformin", "500 mg", "BD", None), ("Glimepiride", "1 mg", "OD", None),
        ("Insulin Glargine", "10 units", "at bedtime", None), ("Vitamin D3", "60000 IU", "once weekly", "8 weeks"),
        ("Lactulose", "15 ml", "HS", None), ("Paracetamol", "650 mg", "SOS", None), ("Mupirocin", None, "BD", "5 days"),
    ]


def test_advice_with_a_dosing_phrase_is_not_a_medicine():
    assert run("Exercise twice daily for 30 minutes\nDrink water 3 times a day").entities.medications == []


# ------------------------------------------------------------------------------ what the document IS
# Naming a medicine is not prescribing it. Both cases below came from real manual tests where the engine
# read a pharmacy bill and a package insert as if a patient had been prescribed something.

def test_pharmacy_invoice_sells_products_it_does_not_prescribe_them():
    result = run("invoice_pharmacy_gst.txt")
    assert result.document_type == DocumentType.medical_invoice
    assert result.entities.medications == []
    assert [(m.name.text, m.dosage and m.dosage.text) for m in result.entities.medication_mentions] == [
        ("Paracetamol", "500mg"), ("Cough Syrup", "100ml")]        # "Face Mask (3 ply)" is merchandise
    assert not (result.entities.diagnoses or result.entities.symptoms or result.entities.test_results)


def test_the_bank_account_holder_on_an_invoice_is_not_the_patient():
    assert run("invoice_pharmacy_gst.txt").entities.patient_name is None


def test_a_bare_name_label_in_a_payee_block_is_never_a_patient():
    assert run("Bank: State Bank of India\nIFSC: SBIN0004321\nBranch: Jayanagar\nName: Kamal").entities.patient_name is None


@pytest.mark.parametrize("label", ["Patient: Kamal", "Patient Name: Kamal", "Pt: Kamal", "Name of patient: Kamal"])
def test_an_explicit_patient_label_is_still_read(label):
    assert run(f"Rx\n{label}\nTab Dolo 650 SOS").entities.patient_name.text == "Kamal"


def test_a_bare_name_beside_patient_demographics_is_read_but_flagged():
    patient = run("City Clinic\nName: Kamal Raj    Age: 45/M\nRx\nTab Dolo 650 SOS").entities.patient_name
    assert patient.text == "Kamal Raj" and patient.needs_review


def test_product_information_is_not_a_prescription():
    result = run("pharma_info_minipress_letter.txt")
    assert result.document_type == DocumentType.pharmaceutical_information
    assert result.entities.medications == []
    assert [m.name.text for m in result.entities.medication_mentions] == ["MINIPRESS", "prazosin HCl"]
    assert all(m.dosage is None for m in result.entities.medication_mentions)   # 1mg/2mg/5mg is the product range


def test_indications_and_adverse_reactions_are_not_a_patients_findings():
    e = run("pharma_info_minipress_letter.txt").entities
    assert (e.diagnoses, e.symptoms, e.allergies, e.test_results) == ([], [], [], [])


def test_a_product_sold_in_several_strengths_is_a_mention_with_no_dose():
    # deliberately not the fixture's words: several strengths on one line state what a product is sold in
    result = run("ZOLTAN Tablets\n(cetirizine hydrochloride)\n5 mg, 10 mg and 20 mg\n\nCOMPOSITION\n"
                 "Each tablet contains cetirizine hydrochloride 5 mg.\nADVERSE REACTIONS\nSedation, dry mouth.\n"
                 "Manufactured by Acme Pharma Limited, Pune")
    assert result.document_type == DocumentType.pharmaceutical_information
    assert result.entities.medications == []
    first = result.entities.medication_mentions[0]
    assert first.name.text.startswith("ZOLTAN")   # the document's own wording is kept, never normalised
    assert first.dosage is None                   # "5 mg, 10 mg and 20 mg" is a product range, not a dose


def test_a_prescription_still_prescribes_and_mentions_nothing():
    result = run("prescription.txt")
    assert result.document_type == DocumentType.prescription
    assert len(result.entities.medications) == 4 and result.entities.medication_mentions == []


def test_a_medicine_named_in_an_invoice_line_is_never_promoted_to_prescribed():
    result = run("GSTIN: 29ABCDE1234F1Z5   Tax Invoice\nInvoice No: 7/2026   Date: 03/09/2026\n"
                 "S.No  Item            HSN    Qty  Rate   Amount\n1   Amoxicillin 500mg Cap  3004  10  4.00  40.00\n"
                 "Grand Total   40.00")
    assert result.document_type == DocumentType.medical_invoice
    assert result.entities.medications == []
    assert [m.name.text for m in result.entities.medication_mentions] == ["Amoxicillin"]


# ------------------------------------------------------------------------------ clinical categories
# A number with a unit is not automatically a lab result, and a name the model recognises is not
# automatically a test. Each of these was a real miscategorisation.

def test_an_analyte_alias_inside_a_row_is_not_a_second_test():
    """"SGPT (ALT) 64 U/L" is one result. The alias used to escape as a bare test mention."""
    result = run("SGPT (ALT) 64 U/L [7 - 56]")
    assert [r.name.text for r in result.entities.test_results] == ["SGPT"]
    assert result.entities.tests == []


def test_short_analytes_are_still_read_as_results():
    """A two-letter analyte is a real test. They are read as one document because a single short line is
    below the pipeline's minimum-legible-text gate and is correctly reported as unreadable."""
    rows = {r.name.text: r.value.text
            for r in run("Hb 10.8 g/dL\nNa 138 mEq/L\nK 4.2 mEq/L\nALT 52 U/L\nTSH 6.8 uIU/mL").entities.test_results}
    assert rows == {"Hb": "10.8", "Na": "138", "K": "4.2", "ALT": "52", "TSH": "6.8"}


def test_observations_are_vitals_not_lab_results():
    e = run("BP 150/90 mmHg  Pulse 88/min  Wt 72 kg  SpO2 98%").entities
    assert [(v.name.text, v.value.text, v.unit.text) for v in e.vitals] == [
        ("BP", "150/90", "mmHg"), ("Pulse", "88", "/min"), ("Wt", "72", "kg"), ("SpO2", "98", "%")]
    assert e.test_results == [] and e.tests == [] and e.symptoms == []   # not labs, not tests, not symptoms


def test_a_labelled_vitals_line_is_also_not_a_lab_row():
    """The guard used to be anchored to the start of the line, so a "Vitals:" prefix defeated it."""
    e = run("Vitals: BP 120/80 mmHg, Pulse 84/min, Temp 98.6 F, SpO2 97%").entities
    assert {v.name.text for v in e.vitals} == {"BP", "Pulse", "Temp", "SpO2"}
    assert e.test_results == []


def test_vitals_never_swallow_a_prescribed_medicine():
    assert [m.name.text for m in run("Inj Insulin 10 units BD, BP 140/90 mmHg").entities.medications] == ["Insulin"]


def test_a_panel_heading_groups_its_rows_instead_of_becoming_a_test():
    result = run("COMPLETE BLOOD COUNT\nHaemoglobin 10.8 g/dL 12.0 - 15.0\nPlatelet Count 1.15 lakhs/cumm 1.5 - 4.1")
    assert [p.text for p in result.entities.panels] == ["COMPLETE BLOOD COUNT"]
    assert [r.name.text for r in result.entities.test_results] == ["Haemoglobin", "Platelet Count"]
    assert result.entities.tests == []


@pytest.mark.parametrize("text,expected", [
    ("Review after 2 weeks with CBC", "CBC"),
    ("Follow up after 1 week with chest X-ray", "chest X-ray"),
])
def test_a_test_or_imaging_study_that_is_advised_stays_a_test_mention(text, expected):
    result = run(text)
    assert [t.text for t in result.entities.tests] == [expected]
    assert result.entities.panels == [] and result.entities.diagnoses == []   # neither a heading nor a diagnosis


@pytest.mark.parametrize("line", ["Allergies: None known", "Allergies: None", "Allergy: Nil", "NKDA"])
def test_a_recorded_absence_of_allergies_yields_no_allergy(line):
    assert run(line).entities.allergies == []


def test_real_allergens_are_still_read():
    assert [a.text for a in run("Allergy: Penicillin, Ibuprofen").entities.allergies] == ["Penicillin", "Ibuprofen"]


@pytest.mark.parametrize("header,expected", [
    ("Patient: Anita Rao   IP No: 4412", "Anita Rao"),
    ("Patient: Anita Rao   UHID: 77120", "Anita Rao"),
    ("Patient: Anita Rao   Ward: 3B", "Anita Rao"),
    ("Patient Name: Anita Rao   Age/Sex: 58/F", "Anita Rao"),
])
def test_the_next_field_label_does_not_stick_to_the_patient_name(header, expected):
    """"Lakshmi Iyer IP" was read as a name because the following field's label ran into it."""
    assert run(f"{header}\nRx\nTab Dolo 650 SOS").entities.patient_name.text == expected


def test_an_abbreviated_cell_count_unit_is_read_with_its_range():
    """"mill/cumm" is how RBC counts are printed; without the unit the reference range was lost too."""
    (row,) = run("RBC Count                4.12      mill/cumm      3.8 - 4.8").entities.test_results
    assert (row.name.text, row.value.text, row.unit.text, row.reference_range.text) == (
        "RBC Count", "4.12", "mill/cumm", "3.8 - 4.8")


def test_negated_findings_do_not_become_positive_ones():
    assert run("C/o No fever, no cough").entities.symptoms == []
    assert [s.text for s in run("C/o fever, no vomiting").entities.symptoms] == ["fever"]


# ------------------------------------------------------------------------------ safety

def test_non_medical_text_yields_nothing_medical():
    result = run("nonmedical_invoice.txt")
    assert result.document_type == DocumentType.unknown
    e = result.entities
    assert not (e.medications or e.diagnoses or e.test_results or e.symptoms or e.allergies)


def test_allergens_are_never_listed_as_prescribed_medicines():
    e = run("rx_clinic_uti.txt").entities
    allergies = {a.text.lower() for a in e.allergies}
    assert {"penicillin", "ibuprofen"} <= allergies
    assert not any(m.name.text.lower() in allergies for m in e.medications)


def test_no_known_allergies_is_not_an_allergy():
    assert run("hw_rx_chalkboard.txt").entities.allergies == []


def test_different_documents_give_different_extractions():
    a, b = run("prescription.txt"), run("discharge.txt")
    assert {m.name.text for m in a.entities.medications}.isdisjoint({m.name.text for m in b.entities.medications})


def test_empty_text_is_unreadable_with_no_entities():
    result = run("   \n  ")
    assert result.status.value == "unreadable" and result.entities.is_empty()

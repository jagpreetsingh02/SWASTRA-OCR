"""The patterns that decide which clinical category a value belongs to. No models.

A number with a unit is not automatically a laboratory result: "SpO2 98%" is measured on the patient,
"COMPLETE BLOOD COUNT" is a heading over the results, and "None known" records an absence. These are the
line-shape rules behind those decisions; the model-driven side is covered in tests/integration.
"""

import pytest

from medikiosk_ocr.extract import NO_CONTENT, PANEL_HEADING, VITAL_MEASURE


@pytest.mark.parametrize("line,expected", [
    ("BP 150/90 mmHg", [("BP", "150/90", "mmHg")]),
    ("Pulse 88/min", [("Pulse", "88", "/min")]),
    ("SpO2 98%", [("SpO2", "98", "%")]),
    ("Temp 98.6 F", [("Temp", "98.6", "F")]),
    ("Wt 72 kg", [("Wt", "72", "kg")]),
    ("Vitals: BP 120/80 mmHg, Pulse 84/min, SpO2 97%",
     [("BP", "120/80", "mmHg"), ("Pulse", "84", "/min"), ("SpO2", "97", "%")]),
])
def test_observations_are_recognised_with_their_value_and_unit(line, expected):
    found = [(m.group("name"), m.group("value"), m.group("unit")) for m in VITAL_MEASURE.finditer(line)]
    assert found == expected


@pytest.mark.parametrize("line", [
    "Haemoglobin 10.8 g/dL", "HbA1c 8.2 %", "Serum Creatinine 1.42 mg/dL", "ALT 52 U/L",
    "Tab Paracetamol 650 mg SOS", "Vitamin D (25-OH) 14.2 ng/mL",
])
def test_laboratory_rows_and_medicines_are_not_read_as_observations(line):
    assert not VITAL_MEASURE.search(line)


@pytest.mark.parametrize("line", [
    "COMPLETE BLOOD COUNT", "Liver Function Test", "LIVER & KIDNEY FUNCTION", "LIPID PROFILE",
    "HAEMATOLOGY", "Renal Function Tests", "  Thyroid Profile  ",
])
def test_a_panel_alone_on_a_line_is_a_heading(line):
    assert PANEL_HEADING.match(line.strip())


@pytest.mark.parametrize("line", [
    "Review after 2 weeks with CBC",            # advised, not a heading
    "Follow up after 1 week with chest X-ray",
    "Haemoglobin 10.8 g/dL 12.0 - 15.0",        # a row carries a value
    "Total WBC Count           11500     /cumm",
])
def test_an_advised_test_or_a_result_row_is_not_a_panel_heading(line):
    assert not PANEL_HEADING.match(line.strip())


@pytest.mark.parametrize("body", ["None", "none known", "Nil", "NAD", "No fever", "denies chest pain", "negative"])
def test_absence_is_recognised(body):
    assert NO_CONTENT.match(body)


@pytest.mark.parametrize("body", ["Penicillin", "fever", "Sulfonamides", "Dust and pollen", "nonspecific rash"])
def test_real_findings_are_not_mistaken_for_an_absence(body):
    assert not NO_CONTENT.match(body)

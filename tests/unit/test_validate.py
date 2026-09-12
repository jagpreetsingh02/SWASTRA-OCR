"""Quality checks: page plausibility and misreading flags. No models."""

import datetime as dt

import pytest
from PIL import Image, ImageDraw, ImageFont

from medikiosk_ocr import validate
from medikiosk_ocr.preprocess import load_document
from medikiosk_ocr.schema import Entities, Entity, Medication, Method, TestResult

from ..conftest import CONTROLS, DEV, dark_object_image, dust_image, noise_image

TODAY = dt.date(2026, 9, 12)


def page_with(lines: list[str]) -> Image.Image:
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    for i, line in enumerate(lines):
        draw.text((80, 100 + i * 55), line, font=font, fill="black")
    return img


THREE = ["Tab Dolo 650 SOS", "Tab Pan 40 OD", "Syp Crocin 5 ml TDS"]


# ------------------------------------------------------------------------------ visible lines

@pytest.mark.parametrize("name,truth", [
    ("prescription_scan.png", 11), ("prescription_photo_handheld.jpg", 11), ("lab_report_degraded.png", 9),
    ("hw_rx_cursive.png", 8), ("hw_rx_brush_hard.png", 6), ("mixed_printed_handwritten.png", 9),
])
def test_visible_line_estimate_is_close_on_real_pages(name, truth):
    assert abs(validate.estimate_text_lines(load_document((DEV / name).read_bytes())[0].image) - truth) <= 1


@pytest.mark.parametrize("make", [noise_image, dark_object_image, dust_image], ids=["noise", "dark_object", "dust"])
def test_images_without_writing_have_no_visible_lines(make):
    assert validate.estimate_text_lines(make()) == 0


# ------------------------------------------------------------------------------ check_page

@pytest.mark.parametrize("image", [noise_image(), dark_object_image(), dust_image(),
                                   Image.open(CONTROLS / "no_document_table.jpg").convert("RGB")],
                         ids=["noise", "dark_object", "dust", "table_photo"])
def test_text_for_an_image_without_writing_is_withheld(image):
    check = validate.check_page(image, "Tab Warfarin 5 mg OD", 1)
    assert check.status == "suspect" and check.withheld == [(0, 20)]


def test_consistent_text_passes():
    check = validate.check_page(page_with(THREE), "\n".join(THREE), 1)
    assert check.status == "ok" and not (check.withheld or check.page_reasons or check.warnings)


def test_one_invented_line_more_than_the_page_shows_raises_a_page_doubt():
    text = "\n".join(THREE[:2] + ["Tab Warfarin 5 mg OD"] + THREE[2:])
    check = validate.check_page(page_with(THREE), text, 1)
    assert check.status == "ok" and not check.withheld           # still extracted...
    assert check.page_reasons and "invented" in check.page_reasons[0]  # ...but every value on the page is doubted


def test_far_more_text_than_the_page_can_hold_is_withheld():
    text = "\n".join(THREE + [f"Tab Drug{i} {i * 10} mg OD" for i in range(10)])
    check = validate.check_page(page_with(THREE), text, 1)
    assert check.status == "suspect" and check.withheld == [(0, len(text))]


def test_far_fewer_lines_than_the_page_shows_raises_a_page_doubt():
    lines = [f"Line {i} of a long prescription" for i in range(12)]
    check = validate.check_page(page_with(lines), lines[0], 1)
    assert check.page_reasons and "missing" in check.page_reasons[0]


def test_repeated_lines_beyond_the_first_are_withheld():
    text = "Tab Dolo 650 SOS\nTab Pan 40 OD\nTab Pan 40 OD\nTab Pan 40 OD"
    check = validate.check_page(page_with(THREE), text, 1)
    assert sorted(check.line_reasons) == [2, 3] and len(check.withheld) == 2


def test_unexpected_script_and_model_commentary_are_withheld():
    check = validate.check_page(page_with(THREE), "Here is the transcription:\nTab Dolo 650 SOS\n区块链是一种数字货币\nTab Pan 40 OD", 1)
    assert set(check.line_reasons) == {0, 2}


# ------------------------------------------------------------------------------ flag_entities

def ent(text: str, start: int) -> Entity:
    return Entity(text=text, start=start, end=start + len(text), page=0, method=Method.pattern,
                  ocr_confidence=0.99, extractor_score=None, needs_review=False)


def entities_for(raw: str, **fields) -> Entities:
    return Entities(**fields)


def test_lab_name_with_confusable_characters_is_flagged_but_not_changed():
    raw = "HbAlc 8.2 %"
    result = TestResult(name=ent("HbAlc", 0), value=ent("8.2", 6), source_line=raw)
    e = Entities(test_results=[result])
    validate.flag_entities(e, raw, today=TODAY)
    assert result.name.text == "HbAlc" and result.name.needs_review
    assert "HbA1c" in result.name.review_reasons[0]


def test_correct_lab_names_are_not_flagged():
    raw = "HbA1c 8.2 %\nTSH 6.8"
    e = Entities(test_results=[TestResult(name=ent("HbA1c", 0), source_line=""), TestResult(name=ent("TSH", 12), source_line="")])
    validate.flag_entities(e, raw, today=TODAY)
    assert not any(v.needs_review for v in e.values())


def test_dose_with_letters_for_digits_is_flagged():
    raw = "TAB. AMLODIPINE SMG OD x 30 days"
    med = Medication(name=ent("AMLODIPINE", 5), frequency=ent("OD", 20), source_line=raw)
    validate.flag_entities(Entities(medications=[med]), raw, today=TODAY)
    assert med.name.needs_review and "SMG" in med.name.review_reasons[0]


def test_dose_followed_by_a_stray_letter_is_flagged():
    raw = "Tab Telma 400 D"
    med = Medication(name=ent("Telma", 4), dosage=ent("400", 10), source_line=raw)
    validate.flag_entities(Entities(medications=[med]), raw, today=TODAY)
    assert med.dosage.needs_review and med.name.needs_review


def test_dose_followed_by_a_duration_is_not_flagged():
    raw = "Tab Azithral 500 x 3 days"
    med = Medication(name=ent("Azithral", 4), dosage=ent("500", 13), source_line=raw)
    validate.flag_entities(Entities(medications=[med]), raw, today=TODAY)
    assert not med.dosage.needs_review


def test_dosing_pattern_with_letters_is_flagged():
    raw = "Tab Deriphyllin 1-O-1"
    med = Medication(name=ent("Deriphyllin", 4), source_line=raw)
    validate.flag_entities(Entities(medications=[med]), raw, today=TODAY)
    assert med.name.needs_review


@pytest.mark.parametrize("text,flagged", [
    ("14/03/2026", False), ("02 Aug 2026", False), ("30|05|2026", True), ("31/02/2026", True),
    ("12/08/2031", True), ("12/08/26", True), ("12/08/1921", True),
])
def test_dates(text, flagged):
    date = ent(text, 6)
    validate.flag_entities(Entities(date=date), "Date: " + text, today=TODAY)
    assert date.needs_review is flagged


def test_value_far_outside_its_range_is_flagged_as_a_possible_decimal_slip():
    raw = "Serum Creatinine 11.5 mg/dL (0.6 - 1.1)"
    ok_raw = "Serum Creatinine 1.3 mg/dL (0.6 - 1.1)"
    slipped = TestResult(name=ent("Serum Creatinine", 0), value=ent("11.5", 17), reference_range=ent("0.6 - 1.1", 29), source_line=raw)
    fine = TestResult(name=ent("Serum Creatinine", 0), value=ent("1.3", 17), reference_range=ent("0.6 - 1.1", 28), source_line=ok_raw)
    validate.flag_entities(Entities(test_results=[slipped]), raw, today=TODAY)
    validate.flag_entities(Entities(test_results=[fine]), ok_raw, today=TODAY)
    assert slipped.value.needs_review and not fine.value.needs_review


def test_context_doubts_attach_to_values_in_their_range():
    raw = "Tab Dolo 650 SOS\nTab Pan 40 OD"
    first, second = Medication(name=ent("Dolo", 4), source_line=""), Medication(name=ent("Pan", 21), source_line="")
    validate.flag_entities(Entities(medications=[first, second]), raw, [(17, 30, "page doubt")], today=TODAY)
    assert not first.name.needs_review and second.name.review_reasons == ["page doubt"]

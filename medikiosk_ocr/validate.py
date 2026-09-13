"""Quality checks between OCR and the result. No model code.

Two jobs, both producing evidence, never corrections:

1. check_page -- is this OCR text plausible for this image? Lines of writing actually visible,
   line counts, repeated-line loops, text in an unexpected script, model commentary. Text the page
   clearly does not support is withheld from extraction (it stays in raw_text for audit).
2. flag_entities -- does an extracted value look like a known kind of misreading? Letters read as
   digits in a dose, 1/l-type confusions in lab names (HbA1c -> HbAlc), impossible or future dates,
   decimal-point slips, "40 OD" read as "400 D". Such values get needs_review with a reason; their
   text is never changed.

None of this proves OCR is correct. A confident misreading that forms a plausible value (5 mg
read as 50 mg, OD read as BD) cannot be detected from the text alone -- that is what human
verification is for.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .schema import Entities, Entity

# ------------------------------------------------------------------------------ page checks

MISSING_LINES_RATIO = 0.6    # fewer than 60% of visible lines read (minus one) -> text may be missing
REPEATED_LINE_TIMES = 3      # the same line read this many times -> a generation loop

# Reading MORE lines than the estimator sees is graded by how far beyond the estimate the text goes:
#   any excess -> a doubt attached to every value on the page, worded as a disagreement: the text may
#                 carry an invented line, or the estimate may have missed writing in a dense layout
#   strong     -> the same doubt, stated as text the page cannot support
#   extreme    -> the page's text is withheld from extraction entirely
# The estimate is accurate to about a line on every test page, so even a one-line excess is worth a
# reviewer's attention; the honest phrasing, not a higher threshold, is what keeps it from overclaiming.
# Undercounting dense tables used to make this complain about invoices -- that is fixed in `_lines_in`,
# where the measurement belongs, rather than by making the check less sensitive.
# A page with no visible writing at all, generation loops, foreign script and model commentary are
# handled separately and keep their full strength.
STRONG_EXTRA_LINES = lambda visible: max(1.5 * visible + 4, visible + 6)
WITHHOLD_LINES = lambda visible: 2 * max(1, visible) + 6

META_COMMENTARY = re.compile(
    r"^\s*(?:here\s+is|here's|below\s+is|the\s+(?:image|text|document|page|photo)\s+(?:shows|contains|reads|says|is)"
    r"|i\s+(?:cannot|can't|can\s+not|am\s+unable|see)|sure[,.!]|certainly[,.!]|transcription\s*:|output\s*:)",
    re.I,
)


@dataclass
class PageCheck:
    status: str = "ok"                                              # ok | suspect
    withheld: list[tuple[int, int]] = field(default_factory=list)   # offsets in the page text
    line_reasons: dict[int, list[str]] = field(default_factory=dict)
    page_reasons: list[str] = field(default_factory=list)           # doubts that apply to every value on the page
    warnings: list[str] = field(default_factory=list)


def estimate_text_lines(img: Image.Image) -> int:
    """Rough count of horizontal lines of writing on the page, from ink alone (no model).

    A "line" is a band of rows with some, but not solid, ink and a text-like height. Solid rows
    (edges of a phone, a shadow, a border) and bands taller than a line (noise, pictures) are not
    writing. Counted in five vertical strips (a tilted photo smears lines across the full width)
    and the best strip is used. Deliberately coarse -- only large disagreements are acted on.
    """
    width = 800
    small = ImageOps.grayscale(img).resize((width, max(1, round(width * img.height / img.width))))
    gray = np.asarray(small, dtype=np.float32)
    background = np.asarray(small.filter(ImageFilter.BoxBlur(20)), dtype=np.float32)
    ink = (background - gray) > 35
    tallest = max(120, gray.shape[0] // 5)
    best = 0
    for strip in np.array_split(ink, 5, axis=1):
        density = strip.mean(axis=1)
        rows = (density > 0.01) & (density < 0.75)
        runs, run, gap = [], 0, 0
        for has_ink in rows:
            if has_ink:
                run, gap = run + 1, 0
            else:
                gap += 1
                if gap >= 3 and run:
                    runs.append(run)
                    run = 0
        if run:
            runs.append(run)
        best = max(best, _lines_in(runs, tallest))
    return best


def _lines_in(runs: list[int], tallest: int) -> int:
    """Count lines from ink-band heights. Bands too thin to be characters are specks or ruled lines; bands
    far taller than a line are pictures. Every other band is divided by the height of a normal line on this
    page, because rows of a dense table merge with their separators into one band -- counting such a band as
    a single line is what made page checks accuse invoices of inventing text."""
    normal = sorted(r for r in runs if 5 <= r <= tallest)
    if not normal:
        return 0
    typical = max(1, normal[len(normal) // 2])
    lines = 0
    for run in runs:
        # A band more than about six line-heights tall is not writing but a shadow, a dark edge or an object
        # in a photo. Measured on the test pages: merged table rows reach ~5 lines (a 54 px band where a line
        # is 11 px), while the smear down the side of a handheld photo was 116 px where a line is 10 px --
        # dividing that one produced twelve lines that do not exist.
        if run < 5 or run > 6 * typical:
            continue
        # Only a band clearly taller than a line holds several merged lines. Headings, ascenders and
        # descenders make ordinary lines up to about 1.5x the median, and dividing those would inflate
        # the estimate on handwriting -- which hides invented lines instead of revealing them.
        lines += round(run / typical) if run >= 1.7 * typical else 1
    return lines


def check_page(image: Image.Image, text: str, page_number: int) -> PageCheck:
    check = PageCheck()
    bounds, pos = [], 0
    for line in text.split("\n"):
        bounds.append((pos, pos + len(line)))
        pos += len(line) + 1
    read = [(i, s, e) for i, (s, e) in enumerate(bounds) if text[s:e].strip()]
    if not read:
        return check

    visible = estimate_text_lines(image)
    if visible == 0:
        check.status = "suspect"
        check.withheld.append((0, len(text)))
        check.warnings.append(f"Page {page_number}: text was returned but no lines of writing are visible in the image. "
                              "It may be invented, so nothing was extracted from this page.")
        return check
    if len(read) < MISSING_LINES_RATIO * visible - 1:
        reason = f"about {visible} lines of writing are visible on page {page_number} but only {len(read)} were read; text may be missing"
        check.page_reasons.append(reason)
        check.warnings.append(f"Page {page_number}: {reason}.")
    elif len(read) > visible:
        counted = f"{len(read)} lines were read on page {page_number} but only about {visible} are visible"
        if len(read) >= WITHHOLD_LINES(visible):
            check.status = "suspect"
            check.withheld.append((0, len(text)))
            check.warnings.append(f"Page {page_number}: far more text was returned than the page can hold; "
                                  "nothing was extracted from this page.")
            return check
        reason = (f"{counted}; some text may be invented" if len(read) >= STRONG_EXTRA_LINES(visible)
                  else f"{counted}; the extra text may be invented, or the estimate may have missed "
                       "writing in a dense layout")
        check.page_reasons.append(reason)
        check.warnings.append(f"Page {page_number}: {reason}.")

    counts: dict[str, int] = {}
    letters = [ch for ch in text if ch.isalpha()]
    cjk_share = sum(_is_cjk(ch) for ch in letters) / len(letters) if letters else 0.0
    for i, s, e in read:
        line = text[s:e]
        key = re.sub(r"\s+", " ", line.strip().lower())
        reason = None
        if len(key) >= 6:
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= 2 and sum(1 for _, a, b in read if re.sub(r"\s+", " ", text[a:b].strip().lower()) == key) >= REPEATED_LINE_TIMES:
                reason = "the same line was read repeatedly (possible OCR generation loop)"
        if reason is None and cjk_share < 0.3 and any(_is_cjk(ch) for ch in line):
            reason = "text in a script that does not match the rest of the page"
        if reason is None and META_COMMENTARY.match(line):
            reason = "commentary from the OCR model, not text from the document"
        if reason:
            check.withheld.append((s, e))
            check.line_reasons.setdefault(i, []).append(reason)
    if check.withheld:
        reasons = sorted({r for rs in check.line_reasons.values() for r in rs})
        check.warnings.append(f"Page {page_number}: {len(check.withheld)} line(s) were not used for extraction: {'; '.join(reasons)}.")
    return check


def _is_cjk(ch: str) -> bool:
    name = unicodedata.name(ch, "")
    return name.startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL"))


# ------------------------------------------------------------------------------ value checks

# Common lab analyte names/abbreviations containing characters OCR confuses (1/l/I, 0/O, 5/S ...).
LAB_LEXICON = {
    "hba1c", "a1c", "t3", "t4", "ft3", "ft4", "tsh", "b12", "25-oh", "ca-125", "ca125", "hbsag", "hcv", "hiv",
    "esr", "crp", "hb", "hgb", "wbc", "rbc", "tlc", "dlc", "pcv", "hct", "mcv", "mch", "mchc", "rdw", "sgot",
    "sgpt", "ast", "alt", "alp", "ggt", "ldl", "hdl", "vldl", "bun", "egfr", "inr", "aptt", "psa", "fbs",
    "ppbs", "rbs", "ige", "lh", "fsh", "cbc", "lft", "kft", "rft", "vdrl", "d3", "igg", "igm", "pth",
}
CONFUSABLE = {"1": "lI|i", "l": "1I|", "I": "1l|", "i": "1l", "|": "1lI", "0": "OoD", "O": "0Q", "o": "0",
              "5": "S", "S": "5", "s": "5", "8": "B", "B": "8", "2": "Z", "Z": "2", "6": "G", "G": "6"}
CONFUSED_DOSE = re.compile(r"(?<![A-Za-z0-9])(?=[0-9OoIlSBZ]*[OoIlSBZ])([0-9OoIlSBZ]{1,5})\s?(mg|mcg|ml|gm|iu)\b", re.I)
CONFUSED_CODE = re.compile(r"(?<![\w-])(?=[01lIO|]\s?-\s?[01lIO|]\s?-\s?[01lIO|])(?=.{0,9}[lIO|])[01lIO|]\s?-\s?[01lIO|]\s?-\s?[01lIO|](?![\w-])")
NUMERIC_DATE = re.compile(r"(\d{1,2})([/.\-|])(\d{1,2})\2(\d{2,4})")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)|<\s*(\d+(?:\.\d+)?)|>\s*(\d+(?:\.\d+)?)")


def flag_entities(entities: Entities, raw_text: str, context: list[tuple[int, int, str]] = (),
                  today: dt.date | None = None) -> None:
    """Add review reasons in place. `context` = (start, end, reason) doubts about stretches of raw_text."""
    today = today or dt.date.today()

    for value in entities.values():
        for start, end, reason in context:
            if start <= value.start < end:
                _add(value, reason)

    for result in entities.test_results:
        _check_lab_name(result.name)
        if result.value and result.reference_range:
            _check_decimal(result.value, result.reference_range)
    for test in entities.tests:
        _check_lab_name(test)

    # Mentions get the same misreading checks: a dose on an invoice line can be misread exactly like a
    # prescribed one, and the reader needs to see that either way.
    for med in [*entities.medications, *entities.medication_mentions]:
        line_end = raw_text.find("\n", med.name.start)
        segment = raw_text[med.name.start: line_end if line_end != -1 else len(raw_text)]
        if m := CONFUSED_DOSE.search(segment):
            reason = f"'{m.group(0)}' looks like a dose with letters where digits should be; check the dose against the document"
            _add(med.name, reason)
            if med.dosage:
                _add(med.dosage, reason)
        if m := CONFUSED_CODE.search(segment):
            _add(med.name, f"dosing pattern '{m.group(0)}' has letters where digits are expected")
            if med.frequency:
                _add(med.frequency, f"dosing pattern '{m.group(0)}' has letters where digits are expected")
        if med.dosage:
            after = raw_text[med.dosage.end: med.dosage.end + 3]
            if re.match(r"\s[A-WYZ](?![A-Za-z0-9])", after):  # "400 D": a stray capital after the dose (x is "x 5 days")
                reason = f"'{med.dosage.text}{after.rstrip()}' may be a misreading of a dose followed by a dosing code (e.g. 40 OD read as 400 D)"
                _add(med.dosage, reason)
                _add(med.name, reason)

    if entities.date:
        _check_date(entities.date, today)


def _add(entity: Entity, reason: str) -> None:
    if reason not in entity.review_reasons:
        entity.review_reasons.append(reason)
    entity.needs_review = True


def _check_lab_name(entity: Entity) -> None:
    for word in re.findall(r"[A-Za-z0-9|]+(?:-[A-Za-z0-9]+)?", entity.text):
        lower = word.lower()
        if lower in LAB_LEXICON or not re.search(r"[A-Za-z]", word):
            continue
        for i, ch in enumerate(word):
            for swap in CONFUSABLE.get(ch, ""):
                candidate = (word[:i] + swap + word[i + 1:]).lower()
                if candidate in LAB_LEXICON:
                    _add(entity, f"'{word}' may be a misreading of '{word[:i] + swap + word[i + 1:]}' (easily confused characters)")
                    return


def _check_decimal(value: Entity, reference: Entity) -> None:
    try:
        number = float(value.text)
    except ValueError:
        return
    m = RANGE.search(reference.text)
    if not m:
        return
    low, high = (float(m.group(1)), float(m.group(2))) if m.group(1) else (0.0, float(m.group(3) or m.group(4)))
    if (high > 0 and number > 10 * high) or (low > 0 and number < low / 10):
        reason = f"value {value.text} is more than ten times outside the reference range {reference.text}; check the decimal point against the document"
        _add(value, reason)


def _check_date(entity: Entity, today: dt.date) -> None:
    m = NUMERIC_DATE.fullmatch(entity.text)
    if not m:
        return
    day, sep, month, year = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
    if sep == "|":
        _add(entity, "unusual date separator '|' (often a misread '/'); check the date")
    if len(year) == 2:
        _add(entity, "two-digit year; check the century")
        full_year = 2000 + int(year)
    else:
        full_year = int(year)
    try:
        date = dt.date(full_year, month, day)
    except ValueError:
        try:
            date = dt.date(full_year, day, month)  # month-first order
        except ValueError:
            _add(entity, "not a valid calendar date; digits may be misread")
            return
    if date > today + dt.timedelta(days=31):
        _add(entity, "date is in the future; digits may be misread")
    elif full_year < 1950:
        _add(entity, "implausibly old date; digits may be misread")

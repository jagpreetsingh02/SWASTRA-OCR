"""Raw text -> Entities. All extraction-model code lives here.

Two kinds of evidence, both strictly extractive (every value is a span of the input text):

* GLiNER-BioMed (a local DeBERTa-based span model) for OPEN-vocabulary things: drug names,
  diseases, symptoms, lab/imaging test names, allergens. It can only label spans that exist in
  the text, so it cannot invent a medicine.
* Patterns for CLOSED-vocabulary things the model labels unreliably: dose units, dosing codes
  (OD, BD, 1-0-1 ...), durations, dates, lab values/units/ranges, "Dr ..." and "Patient ..." headers.

Section labels on a line ("Dx:", "c/o", "Allergy") decide where a span goes, because the same
word ("hypertension") is a diagnosis on one line and background elsewhere.

A span the model calls a drug only becomes a medication with contextual evidence on its line
(a dosage form, a dose with a unit, a dosing code, a dosing phrase or a duration); a lab-table
row whose analyte the model calls a drug ("Vitamin D (25-OH) 14.2 ng/mL 30 - 100") is a result.

Plausibility checks that look for misreadings (e.g. HbAlc) are in validate.py, not here.
"""

from __future__ import annotations

import bisect
import re
import threading
from dataclasses import dataclass

from .schema import DocumentType, Entities, Entity, Medication, Method, TestResult

NER_MODEL_ID = "Ihor/gliner-biomed-large-v1.0"
NER_THRESHOLD = 0.45
NER_LABELS = {"Drug": "drug", "Disease": "disease", "Symptom": "symptom", "Lab test": "test",
              "Imaging test": "test", "Allergy": "allergy"}

# Review triage thresholds. Heuristics for "show this to a person first", never approval.
OCR_REVIEW_BELOW = 0.80        # lowest OCR token probability over the value's characters
EXTRACTOR_REVIEW_BELOW = 0.60  # GLiNER span score

# ------------------------------------------------------------------------------ patterns

FORM = r"(?:tabs?|tablet|caps?|capsule|syp|syr|syrup|susp|inj|injection|oint|ointment|drops?|gel|cream|inh|neb|sachet)"
FORM_PREFIX = re.compile(rf"(?:\d{{1,2}}[.)]\s*)?{FORM}\b\.?\s*", re.I)       # used with .match(text, pos)
FORM_WORD = re.compile(rf"{FORM}\.?|rx", re.I)                                  # used with .fullmatch
# Only these prefixes start a second medicine inside one line ("..., Tab. Glimepiride 1 mg OD").
SEGMENT_START = re.compile(r"[\s,;+]((?:tabs?|tablet|caps?|capsule|syp|syr|syrup|inj|injection)\b\.?\s+)(?=[A-Za-z])", re.I)
NUMBERING = re.compile(r"\s*(?:\d{1,2}[.)]\s*)?")
DOSE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|gm|g|ml|iu|units?|%|sachets?|puffs?|drops?)(?![\w/%])", re.I)
MED_UNIT = re.compile(r"\d\s?(?:mg|mcg|µg|ug|gm|ml|iu|units?|sachets?|puffs?|drops?)(?![\w/%])", re.I)
BARE_NUMBER = re.compile(r"[\s:]*(\d+(?:\.\d+)?)(?![\d/.\-])")
FREQ_CODE = re.compile(
    r"(?<![\w-])(?:OD|BD|BID|TDS|TID|QID|QDS|HS|SOS|PRN|STAT|QHS|QAM|QPM|Q\d{1,2}H"
    r"|[01½]\s?-\s?[01½]\s?-\s?[01½](?:\s?-\s?[01½])?)(?![\w-])", re.I)
FREQ_PHRASE = re.compile(
    r"\b(?:once|twice|thrice)\s+(?:a\s+)?(?:day|daily|week|weekly)\b|\bat\s+bed\s?time\b"
    r"|\bafter\s+each\s+\w+|\bevery\s+\d+\s*(?:hours?|hrs?)\b", re.I)
FREQUENCY = re.compile(f"{FREQ_CODE.pattern}|{FREQ_PHRASE.pattern}", re.I)
DURATION = re.compile(r"(?:\bx|×|\bfor)\s*(\d+\s?(?:days?|d|weeks?|wks?|months?))\b", re.I)
DATE = re.compile(
    r"(?<![\d/.\-|])(\d{1,2})([/.\-|])(\d{1,2})\2(\d{4}|\d{2})(?![\d/.\-|])"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+\d{4}\b",
    re.I,
)
DOCTOR = re.compile(r"\bDr\.?\s+[A-Z][A-Za-z.']*(?: [A-Z][A-Za-z.']*){0,3}")
CREDENTIALS = {"MBBS", "MD", "MS", "DNB", "BAMS", "BHMS", "BDS", "FRCS", "MRCP", "DM", "MCH", "DGO", "DCH", "PHD"}
PATIENT = re.compile(r"\b(?:patient(?:'s)?\s*name|patient|pt|name)\s*[:.\-]\s*([A-Za-z][A-Za-z.']*(?: [A-Za-z][A-Za-z.']*){0,3})", re.I)
PATIENT_NO_SEPARATOR = re.compile(r"(?m)^[ \t]*(?:Pt|PT|Patient)\.?[ \t]+([A-Z][a-z]+(?:[ \t][A-Z][a-z]+){1,3})\b")
NOT_NAME_WORDS = {"age", "date", "sex", "gender", "dob", "id", "uhid", "no", "mrn"}
LAB_UNIT = (r"g/dl|mg/dl|mcg/dl|µg/dl|mg%|mmol/l|µiu/ml|uiu/ml|miu/l|iu/l|u/l|ng/ml|pg/ml|mm/hr|fl|pg|meq/l"
            r"|µmol/l|umol/l|g/l|mg/l|cells/cumm|/cumm|lakhs/cumm|million/cumm|/µl|/ul|x10\^?\d+/l|%")
LAB_RANGE = r"\d+(?:\.\d+)?[ \t]*[-–][ \t]*\d+(?:\.\d+)?|[<>][ \t]*\d+(?:\.\d+)?"
LAB_ROW = re.compile(  # what follows an analyte name the model found
    r"(?:[ \t]*\([^()\n]{1,20}\))?[ \t:=]*(?P<value>\d+(?:\.\d+)?)"
    rf"(?:[ \t]*(?P<unit>{LAB_UNIT}))?"
    rf"(?:[ \t]*\(?[ \t]*(?P<range>{LAB_RANGE})[ \t]*\)?)?"
    r"(?![\w/])",
    re.I,
)
LAB_ROW_LINE = re.compile(  # a whole line shaped like a lab row, for analytes the model did not recognise (e.g. misread "HbAlc")
    r"^[ \t]*(?P<name>[A-Za-z][A-Za-z0-9.()/+-]*(?:[ \t][A-Za-z][A-Za-z0-9.()/+-]*){0,4})[ \t:=]+(?P<value>\d+(?:\.\d+)?)"
    rf"(?:[ \t]*(?P<unit>{LAB_UNIT}))?"
    rf"(?:[ \t]*\(?[ \t]*(?P<range>{LAB_RANGE})[ \t]*\)?)?[ \t]*$",
    re.I,
)
VITALS_LINE = re.compile(r"^\s*(?:bp|pulse|temp|spo2|wt|weight|ht|height|bmi|rr|hr)\b", re.I)
DX_LINE = re.compile(r"^\s*(?:provisional\s+|final\s+)?(?:dx|diagnosis|diagnoses|impression|imp|diag)\b\s*[:.\-]?\s*", re.I)
COMPLAINT_LINE = re.compile(r"\b(?:c/o|complain(?:s|ts?|ing)?\s+of|chief\s+complaints?|presenting\s+complaints?)\s*[:.\-]?\s*", re.I)
ALLERGY_LINE = re.compile(r"\ballerg\w*\s*(?:to\b|:)?\s*", re.I)
NO_ALLERGY = re.compile(r"\b(?:nkda|nkfa|no known (?:drug )?allerg\w*)\b", re.I)
NOT_MED_LINE = re.compile(r"^\s*(?:date|dr\b|patient|pt\b|name|age|wt|weight|bp|pulse|temp|spo2|reg|adv|advice|review|diet|rx\s*$)", re.I)


@dataclass
class Span:
    kind: str
    start: int
    end: int
    score: float


# ------------------------------------------------------------------------------ model

_model = None
_model_lock = threading.Lock()   # guards loading AND prediction: one GLiNER call at a time


def _ner():
    global _model
    with _model_lock:
        if _model is None:
            from gliner import GLiNER

            _model = GLiNER.from_pretrained(NER_MODEL_ID)
            _model.eval()
    return _model


def is_loaded() -> bool:
    return _model is not None


def _ner_spans(text: str) -> list[Span]:
    model = _ner()
    spans: list[Span] = []
    for offset, chunk in _chunks(text):
        if not chunk.strip():
            continue
        with _model_lock:
            predicted = model.predict_entities(chunk, list(NER_LABELS), threshold=NER_THRESHOLD, flat_ner=True)
        for e in predicted:
            start, end = _tidy(text, offset + e["start"], offset + e["end"])
            token = text[start:end]
            # the model sometimes labels dosing codes and dosage forms as drugs/tests
            if end > start and not (FORM_WORD.fullmatch(token) or FREQUENCY.fullmatch(token) or DOSE.fullmatch(token)):
                spans.append(Span(NER_LABELS[e["label"]], start, end, float(e["score"])))
    return spans


def _chunks(text: str, max_chars: int = 900):
    """GLiNER sees ~384 tokens; feed it whole lines, a few at a time, keeping offsets."""
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            newline = text.rfind("\n", start, end)
            end = newline + 1 if newline > start else end
        yield start, text[start:end]
        start = end


def _tidy(text: str, start: int, end: int) -> tuple[int, int]:
    """Keep a span on one line and trim surrounding whitespace/punctuation."""
    newline = text.find("\n", start, end)
    if newline != -1:
        end = newline
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not (text[end - 1].isalnum() or text[end - 1] in "%)"):
        end -= 1
    return start, end


# ------------------------------------------------------------------------------ extraction

def extract_entities(text: str, char_confidence: list[float | None] | None = None,
                     page_starts: list[int] | None = None) -> tuple[Entities, DocumentType]:
    """`char_confidence[i]` is the OCR token probability behind text[i] (None where not OCR'd).
    `page_starts` are the offsets where each page begins in `text` (default: one page)."""
    if not text.strip():
        return Entities(), DocumentType.unknown
    ner = _ner_spans(text)
    starts = page_starts or [0]

    def make(start: int, end: int, method: Method, score: float | None = None, reasons: tuple[str, ...] = ()) -> Entity:
        known = [c for c in char_confidence[start:end] if c is not None] if char_confidence else []
        ocr = min(known) if known else None
        why = list(reasons)
        if ocr is not None and ocr < OCR_REVIEW_BELOW:
            why.append(f"OCR model was unsure of these characters (lowest token probability {ocr:.2f})")
        if score is not None and score < EXTRACTOR_REVIEW_BELOW:
            why.append(f"extraction model score is low ({score:.2f})")
        return Entity(text=text[start:end], start=start, end=end, page=bisect.bisect_right(starts, start) - 1,
                      method=method, ocr_confidence=None if ocr is None else round(ocr, 3),
                      extractor_score=None if score is None else round(score, 3),
                      needs_review=bool(why), review_reasons=why)

    ents = Entities()
    _header(text, ents, make)

    for ls, le in _line_bounds(text):
        line = text[ls:le]
        on_line = [s for s in ner if ls <= s.start < le]

        # allergies: everything named on an allergy line is an allergen, never a prescription
        if ALLERGY_LINE.search(line) or NO_ALLERGY.search(line):
            if not NO_ALLERGY.search(line):
                named = [s for s in on_line if s.kind in ("drug", "allergy", "disease")]
                body = ls + ALLERGY_LINE.search(line).end()
                ents.allergies += ([make(s.start, s.end, Method.model, s.score) for s in named] if named
                                   else _items(text, body, le, [], make))
            continue

        # diagnosis / complaint sections override the model's disease-vs-symptom call
        dx, complaint = DX_LINE.search(line), COMPLAINT_LINE.search(line)
        if dx or complaint:
            body = ls + (dx or complaint).end()
            named = [s for s in on_line if s.kind in ("disease", "symptom") and s.start >= body]
            (ents.diagnoses if dx else ents.symptoms).extend(_items(text, body, le, named, make))
            continue

        looks_prescribed = bool(FREQ_CODE.search(line) or MED_UNIT.search(line) or FORM_PREFIX.match(line.lstrip()))
        if not looks_prescribed and _lab_results(text, ls, le, on_line, ents, make, results=not VITALS_LINE.match(line)):
            continue

        found = _medications(text, ls, le, on_line, make)
        ents.medications += [m for m, _ in found]
        claimed = [(m.name.start, segment_end) for m, segment_end in found]
        for s in on_line:
            inside_medication = any(a <= s.start < b for a, b in claimed)
            if s.kind == "test" and not inside_medication:
                ents.tests.append(make(s.start, s.end, Method.model, s.score))
            elif not found and s.kind == "disease":
                ents.diagnoses.append(make(s.start, s.end, Method.model, s.score))
            elif not found and s.kind == "symptom":
                ents.symptoms.append(make(s.start, s.end, Method.model, s.score))

    ents.dosages = [m.dosage for m in ents.medications if m.dosage]
    ents.frequencies = [m.frequency for m in ents.medications if m.frequency]
    for field in ("diagnoses", "symptoms", "tests", "allergies"):
        setattr(ents, field, _dedupe(getattr(ents, field)))
    return ents, _document_type(text, ents)


def _header(text: str, ents: Entities, make) -> None:
    if m := DOCTOR.search(text):
        words = m.group(0).split(" ")
        while len(words) > 2 and words[-1].strip(".,").upper() in CREDENTIALS:
            words.pop()
        name = " ".join(words).rstrip(",. ")
        ents.doctor_name = make(m.start(), m.start() + len(name), Method.pattern)
    if m := PATIENT.search(text):
        words = m.group(1).split(" ")
        while words and words[-1].lower().strip(".") in NOT_NAME_WORDS:
            words.pop()
        if words:
            name = " ".join(words).rstrip(".")
            ents.patient_name = make(m.start(1), m.start(1) + len(name), Method.pattern)
    elif m := PATIENT_NO_SEPARATOR.search(text):
        ents.patient_name = make(m.start(1), m.end(1), Method.pattern,
                                 reasons=("patient name read from a label without ':' -- check it is the name",))
    dates = list(DATE.finditer(text))
    if dates:
        labelled = [d for d in dates if re.search(r"date|dated|collected|admitted|\bon\b", _line_of(text, d.start()), re.I)]
        d = (labelled or dates)[0]
        ents.date = make(d.start(), d.end(), Method.pattern)


def _lab_results(text: str, ls: int, le: int, on_line: list[Span], ents: Entities, make, results: bool = True) -> bool:
    """Lab rows: '<analyte> [(qualifier)] <value> [unit] [range]'. A span the model called a drug counts
    only with lab evidence (a lab unit or a reference range) -- vitamins and hormones are both.
    `results=False` (vitals lines): test names are still mentions, but no values are taken."""
    found = False
    line = text[ls:le]

    def add(name: Entity, row: re.Match, base: int) -> None:
        ents.test_results.append(TestResult(
            name=name,
            value=make(base + row.start("value"), base + row.end("value"), Method.pattern),
            unit=make(base + row.start("unit"), base + row.end("unit"), Method.pattern) if row.group("unit") else None,
            reference_range=make(base + row.start("range"), base + row.end("range"), Method.pattern) if row.group("range") else None,
            source_line=line.strip(),
        ))

    if not results:  # vitals line ("BP 150/90  SpO2 98%"): measurements, not tests or results
        return False
    for s in (s for s in on_line if s.kind in ("test", "drug")):
        row = LAB_ROW.match(text, s.end, le)
        if not row or DATE.match(text, row.start("value")):
            if s.kind == "test":
                ents.tests.append(make(s.start, s.end, Method.model, s.score))
                found = True
            continue
        if s.kind == "drug" and not (row.group("unit") or row.group("range")):
            continue
        add(make(s.start, s.end, Method.model, s.score), row, 0)
        found = True

    if not found and results and not NOT_MED_LINE.match(line) and not DATE.search(line):
        row = LAB_ROW_LINE.match(line)
        if row and (row.group("unit") or row.group("range")):
            name = make(ls + row.start("name"), ls + row.end("name"), Method.pattern,
                        reasons=("test name found by pattern only; the extraction model did not recognise it",))
            add(name, row, ls)
            found = True
    return found


def _medications(text: str, ls: int, le: int, on_line: list[Span], make) -> list[tuple[Medication, int]]:
    """Medications on one line, each with the offset where its part of the line ends."""
    line = text[ls:le]
    if NOT_MED_LINE.match(line):
        return []
    cuts = [ls] + [ls + m.start(1) for m in SEGMENT_START.finditer(line) if m.start(1) > 3] + [le]
    out = []
    for seg_start, seg_end in zip(cuts, cuts[1:]):
        med = _medication(text, seg_start, seg_end, [s for s in on_line if seg_start <= s.start < seg_end], make, line)
        if med:
            out.append((med, seg_end))
    return out


def _medication(text: str, ss: int, se: int, spans: list[Span], make, line: str) -> Medication | None:
    pos = NUMBERING.match(text, ss, se).end()
    form = FORM_PREFIX.match(text, pos, se)
    drugs = [s for s in spans if s.kind == "drug"]
    if drugs:
        start, end, score, method = drugs[0].start, drugs[0].end, drugs[0].score, Method.model
        if f := FORM_PREFIX.match(text, start, end):             # "TAB. METFORMIN" -> "METFORMIN"
            start = f.end()
    else:
        start, end, score, method = (form.end() if form else pos), se, None, Method.pattern
    # the name ends where the numbers or dosing codes begin: "Augmtin 625", "Montek LC HS"
    stop = re.search(r"\s(?=\d)|\s(?:" + FREQUENCY.pattern + ")", text[start:end], re.I)
    if stop and stop.start() > 0:
        end = start + stop.start()
    start, end = _tidy(text, start, end)
    if end - start < 2 or not re.search(r"[A-Za-z]{2}", text[start:end]):
        return None

    dose = DOSE.search(text, end, se)
    bare = None if dose else BARE_NUMBER.match(text, end, se)
    dose_span = (dose.start(), dose.end()) if dose else (bare.start(1), bare.end(1)) if bare else None
    code, phrase = FREQ_CODE.search(text, end, se), FREQ_PHRASE.search(text, end, se)
    freq = min((m for m in (code, phrase) if m), key=lambda m: m.start(), default=None)
    dur = DURATION.search(text, end, se)
    strong = bool(form or code or (dose and MED_UNIT.match(text, dose.start())))  # "8.2 %" is not dose evidence
    weak = bool(phrase or dur)
    # A model-found drug needs some prescription context; a pattern-only name needs strong context.
    # A bare number is never enough ("Vitamin D (25-OH) 14.2" is a lab row, not a prescription).
    if not (strong or (method is Method.model and weak)):
        return None
    reasons = () if method is Method.model else ("medicine name found by pattern only; the extraction model did not recognise it",)
    return Medication(
        name=make(start, end, method, score, reasons),
        dosage=make(*dose_span, Method.pattern) if dose_span else None,
        frequency=make(freq.start(), freq.end(), Method.pattern) if freq else None,
        duration=make(dur.start(1), dur.end(1), Method.pattern) if dur else None,
        source_line=line.strip(),
    )


def _items(text: str, start: int, end: int, named: list[Span], make) -> list[Entity]:
    """Items of a labelled section ("Dx: T2DM, HTN"). If the model found one short span inside an item
    ("COPD" in "Acute exacerbation of COPD") the whole item is kept; several spans are kept separately
    ("Type 2 diabetes mellitus with hypertension"); nothing found -> pattern-only item, flagged."""
    cut = re.search(r"\s(?:x|for|since)\s*\d", text[start:end])     # "fever, cough x 3 days"
    if cut:
        end = start + cut.start()
    out, pos = [], start
    for part in re.split(r"(,|;|\band\b)", text[start:end]):
        s, e = _tidy(text, pos, pos + len(part))
        pos += len(part)
        if part in (",", ";", "and") or e - s < 2 or not re.search(r"[A-Za-z]", text[s:e]):
            continue
        inside = [n for n in named if s <= n.start < e]
        if len(inside) == 1 and (inside[0].end - inside[0].start) < 0.6 * (e - s):
            out.append(make(s, e, Method.model, inside[0].score))
        elif inside:
            out += [make(n.start, n.end, Method.model, n.score) for n in inside]
        else:
            out.append(make(s, e, Method.pattern, reasons=("section item found by pattern only; the extraction model did not recognise it",)))
    return out


def _document_type(text: str, ents: Entities) -> DocumentType:
    t = text.lower()
    if re.search(r"discharge\s+summary|date of discharge|discharged|admitted", t):
        return DocumentType.discharge_summary
    if (len(ents.test_results) >= 3 and not ents.diagnoses) or re.search(r"\b(?:lab(?:oratory)?|biochemistry|haematology|pathology)\b.*report|reference range|sample collected", t):
        return DocumentType.lab_report
    if ents.medications or re.search(r"(?m)^\s*rx\b", t):
        return DocumentType.prescription
    if ents.diagnoses or ents.test_results or ents.tests or ents.symptoms:
        return DocumentType.other_medical
    return DocumentType.unknown


def _line_bounds(text: str) -> list[tuple[int, int]]:
    bounds, start = [], 0
    for line in text.split("\n"):
        bounds.append((start, start + len(line)))
        start += len(line) + 1
    return bounds


def _line_of(text: str, pos: int) -> str:
    end = text.find("\n", pos)
    return text[text.rfind("\n", 0, pos) + 1: end if end != -1 else len(text)]


def _dedupe(items: list[Entity]) -> list[Entity]:
    seen, out = set(), []
    for e in items:
        key = e.text.lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out

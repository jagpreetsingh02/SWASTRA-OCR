"""Raw text -> Entities. All extraction-model code lives here.

Two kinds of evidence, both strictly extractive (every value is a span of the input text):

* GLiNER-BioMed (a local DeBERTa-based span model) for OPEN-vocabulary things: drug names,
  diseases, symptoms, lab/imaging test names, allergens. It can only label spans that exist in
  the text, so it cannot invent a medicine.
* Patterns for CLOSED-vocabulary things the model labels unreliably: dose units, dosing codes
  (OD, BD, 1-0-1 ...), durations, dates, lab values/units/ranges, "Dr ..." and "Patient ..." headers.

What the document IS decides what its content MEANS. `classify_document` reads document-level
evidence only -- never the entities it will later produce -- and the kind then routes everything:

    naming a medicine  !=  prescribing it to a patient

A pharmacy invoice line ("Paracetamol 500mg Tablet  3004  10  2.50  25.00") and a package insert
("NEW MINIPRESS Capsules 1mg, 2mg, 5mg") are medication MENTIONS: kept as evidence in
`medication_mentions`, never presented as something a patient takes. Only documents that prescribe
(a prescription, a discharge summary, or an ordinary clinical note) can produce `medications`, and
only for lines carrying prescription context. Indications and adverse reactions printed in product
literature are likewise not a patient's diagnoses or symptoms.

Plausibility checks that look for misreadings (e.g. HbAlc) are in validate.py, not here.
"""

from __future__ import annotations

import bisect
import re
import threading
from dataclasses import dataclass, field

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
# "<Brand> Capsules", "<Brand> Tablets": a product named together with its dosage form. Finds brand names
# the extraction model does not know (MINIPRESS); the stop words keep prose like "Each capsule contains ..."
# from turning its first word into a product.
FORM_SUFFIX = re.compile(rf"(?i:new\s+|the\s+)?([A-Z][A-Za-z0-9'\-]{{2,}}(?:\s+[A-Z][A-Za-z0-9'\-]+){{0,2}})\s+(?i:{FORM})s?\b")
NOT_PRODUCT_WORDS = {"each", "every", "this", "these", "those", "one", "two", "per", "following",
                     "above", "oral", "the", "new", "and", "with", "for", "of", "in", "no"}
# Salt and hydrate forms. Ignored when deciding whether two mentions name the same medicine, never removed
# from the extracted text: "prazosin HCl" and "prazosin hydrochloride" are one medicine named twice.
SALT_WORDS = {"hcl", "hydrochloride", "sodium", "potassium", "calcium", "magnesium", "sulphate", "sulfate",
              "phosphate", "acetate", "citrate", "maleate", "tartrate", "succinate", "fumarate", "besylate",
              "mesylate", "monohydrate", "dihydrate", "trihydrate"}
# Only these prefixes start a second medicine inside one line ("..., Tab. Glimepiride 1 mg OD").
SEGMENT_START = re.compile(r"[\s,;+]((?:tabs?|tablet|caps?|capsule|syp|syr|syrup|inj|injection)\b\.?\s+)(?=[A-Za-z])", re.I)
NUMBERING = re.compile(r"\s*(?:\d{1,2}[.)]\s*)?")
DOSE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|gm|g|ml|iu|units?|%|sachets?|puffs?|drops?)(?![\w/%])", re.I)
MED_UNIT = re.compile(r"\d\s?(?:mg|mcg|µg|ug|gm|ml|iu|units?|sachets?|puffs?|drops?)(?![\w/%])", re.I)
BARE_NUMBER = re.compile(r"[\s:]*(\d+(?:\.\d+)?)(?![\d/.\-])")
# "1mg, 2mg, 5mg" / "1 mg, 2 mg or 5 mg": the strengths a product is SOLD in, never one patient's dose.
# A slash is deliberately NOT a separator: "Syp Calpol 250 mg/5 ml" is a single concentration ("per"), and
# reading it as several strengths demoted a prescribed syrup to a mere mention.
MULTI_STRENGTH = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|gm|g|ml|iu)\b(?:\s*(?:,|\bor\b|\band\b)\s*\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|gm|g|ml|iu)\b)+",
    re.I)
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
NAME_VALUE = r"([A-Za-z][A-Za-z.']*(?: [A-Za-z][A-Za-z.']*){0,3})"
# "Patient: X", "Patient Name: X", "Pt: X", "Name of patient: X" -- the label itself says whose name it is.
PATIENT_LABEL = re.compile(rf"\b(?:patient(?:'s)?\s*name|name\s+of\s+(?:the\s+)?patient|patient|pt)\s*[:.\-]\s*{NAME_VALUE}", re.I)
PATIENT_NO_SEPARATOR = re.compile(r"(?m)^[ \t]*(?:Pt|PT|Patient)\.?[ \t]+([A-Z][a-z]+(?:[ \t][A-Z][a-z]+){1,3})\b")
# A bare "Name:" belongs to whoever the surrounding block is about -- a patient, a payee, a company.
BARE_NAME_LABEL = re.compile(rf"(?mi)^[ \t]*name[ \t]*[:.\-][ \t]*{NAME_VALUE}")
DEMOGRAPHIC_CONTEXT = re.compile(
    r"\b(?:age|sex|gender|d\.?o\.?b|uhid|mrn|patient\s*id|ip\s*no|op\s*no|reg\s*no|years?|yrs?|male|female)\b"
    r"|\b\d{1,3}\s*(?:y|yr|yrs|years?)\b|\b\d{1,3}\s*/\s*[MFmf]\b|\b[MFmf]\s*/\s*\d{1,3}\b", re.I)
NOT_PATIENT_CONTEXT = re.compile(
    r"\b(?:bank|ifsc|a/c|account|beneficiary|branch|cheque|upi|paytm|gstin|gst|company|firm|manufactur\w*|marketed"
    r"|proprietor|customer|vendor|supplier|dealer|consignee|invoice|father|guardian|nominee|witness|signature)\b", re.I)
# Label words that sit beside a name on the same line ("Patient: Lakshmi Iyer   IP No: 55392"). They are
# trimmed off the end of a captured name, or the next field's label becomes part of the patient.
NOT_NAME_WORDS = {"age", "date", "sex", "gender", "dob", "id", "uhid", "no", "mrn", "ip", "op",
                  "reg", "ref", "ward", "bed", "room", "opd", "ipd"}
LAB_UNIT = (r"g/dl|mg/dl|mcg/dl|µg/dl|mg%|mmol/l|µiu/ml|uiu/ml|miu/l|iu/l|u/l|ng/ml|pg/ml|mm/hr|fl|pg|meq/l"
            r"|µmol/l|umol/l|g/l|mg/l|cells/cumm|/cumm|lakhs/cumm|million/cumm|mill/cumm|/µl|/ul|x10\^?\d+/l|%")
LAB_RANGE = r"\d+(?:\.\d+)?[ \t]*[-–][ \t]*\d+(?:\.\d+)?|[<>][ \t]*\d+(?:\.\d+)?"
LAB_ROW = re.compile(  # what follows an analyte name the model found
    r"(?:[ \t]*\([^()\n]{1,20}\))?[ \t:=]*(?P<value>\d+(?:\.\d+)?)"
    rf"(?:[ \t]*(?P<unit>{LAB_UNIT}))?"
    rf"(?:[ \t]*[(\[]?[ \t]*(?P<range>{LAB_RANGE})[ \t]*[)\]]?)?"
    r"(?![\w/])",
    re.I,
)
LAB_ROW_LINE = re.compile(  # a whole line shaped like a lab row, for analytes the model did not recognise (e.g. misread "HbAlc")
    r"^[ \t]*(?P<name>[A-Za-z][A-Za-z0-9.()/+-]*(?:[ \t][A-Za-z][A-Za-z0-9.()/+-]*){0,4})"
    r"(?:[ \t]*\([^()\n]{1,20}\))?[ \t:=]+(?P<value>\d+(?:\.\d+)?)"
    rf"(?:[ \t]*(?P<unit>{LAB_UNIT}))?"
    rf"(?:[ \t]*[(\[]?[ \t]*(?P<range>{LAB_RANGE})[ \t]*[)\]]?)?[ \t]*$",
    re.I,
)
# Physiological observations: measured on the patient, never laboratory results. "SpO2 98%" has a number
# and a unit-like symbol but is an observation. Matched ANYWHERE on the line -- a line-anchored check let a
# "Vitals: ..." prefix through, and SpO2 was then read as a lab row.
VITAL_NAME = (r"bp|b\.p\.|blood\s+pressure|pulse|hr|heart\s+rate|rr|resp(?:iratory)?\s*rate|spo2|sao2|"
              r"o2\s*sats?|temp(?:erature)?|wt|weight|ht|height|bmi")
VITAL_MEASURE = re.compile(
    rf"\b(?P<name>{VITAL_NAME})\b\s*[:=]?\s*(?P<value>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)"
    r"\s*(?P<unit>mmhg|bpm|/min|kg|lbs|cm|mm|%|°\s?[cf]|\b[cf]\b)?", re.I)
# A panel groups analytes. Alone on a line it is a HEADING and the analytes follow as rows; inside a
# sentence ("Review after 2 weeks with CBC") it is a test being advised, which belongs in `tests`.
PANEL_HEADING = re.compile(
    r"^\W*(?:complete\s+blood\s+count|cbc|liver\s+function\s+tests?|lft|kidney\s+function\s+tests?|"
    r"renal\s+function\s+tests?|kft|rft|lipid\s+profile|thyroid\s+(?:profile|function\s+tests?)|tft|"
    r"haematology|hematology|biochemistry|pathology|iron\s+studies|coagulation\s+profile|urine\s+routine|"
    r"[A-Za-z][A-Za-z&/ ]*(?:function|profile|panel|count|studies))\W*$", re.I)
# A section body that records the absence of something: "Allergies: None known", "No fever", "Nil", "NAD".
NO_CONTENT = re.compile(
    r"^\W*(?:none(?:\s+known)?|nil|nad|negative|not\s+known|(?:no|denies|denied|without)\s+\S.*?)\W*$", re.I)
DX_LINE = re.compile(r"^\s*(?:provisional\s+|final\s+)?(?:dx|diagnosis|diagnoses|impression|imp|diag)\b\s*[:.\-]?\s*", re.I)
COMPLAINT_LINE = re.compile(r"\b(?:c/o|complain(?:s|ts?|ing)?\s+of|chief\s+complaints?|presenting\s+complaints?)\s*[:.\-]?\s*", re.I)
ALLERGY_LINE = re.compile(r"\ballerg\w*\s*(?:to\b|:)?\s*", re.I)
NO_ALLERGY = re.compile(r"\b(?:nkda|nkfa|no known (?:drug )?allerg\w*)\b", re.I)
NOT_MED_LINE = re.compile(r"^\s*(?:date|dr\b|patient|pt\b|name|age|wt|weight|bp|pulse|temp|spo2|reg|adv|advice|review|diet|rx\s*$)", re.I)
# A billed line item: a quantity/price table row, or an HSN/SAC tax code. Selling is not prescribing.
INVOICE_ROW = re.compile(r"\b(?:hsn|sac)\b|\b\d+\.\d{2}\s*$|(?:₹|\brs\.?)\s*\d", re.I)

# ------------------------------------------------------------------------------ document-level evidence

INVOICE_SIGNALS = (
    (re.compile(r"\btax\s+invoice\b|\binvoice\s*(?:no|#|number)|\bbill\s+(?:to|no)\b|\bcash\s+memo\b|\breceipt\s*no\b", re.I), 3),
    (re.compile(r"\bgst(?:in)?\b|\b[cis]gst\b", re.I), 3),
    (re.compile(r"\bhsn\b|\bsac\b", re.I), 2),
    (re.compile(r"\b(?:sub\s*total|grand\s*total|total\s+amount|amount\s+payable|net\s+payable)\b", re.I), 2),
    (re.compile(r"\bqty\b|\bquantity\b|\brate\b", re.I), 1),
    (re.compile(r"\b(?:ifsc|a/c\s*no|account\s*(?:no|number)|bank\s+details)\b", re.I), 1),
    (re.compile(r"(?:₹|\brs\.?\b|\binr\b)\s*\d", re.I), 1),
)
PRODUCT_INFO_SIGNALS = (
    (re.compile(r"(?m)^\s*(?:composition|indications?|contra-?indications?|dosage\s+and\s+administration|adverse\s+"
                r"(?:reactions?|effects?)|side\s+effects?|warnings?(?:\s+and\s+precautions?)?|precautions?|storage|"
                r"overdosage|pharmacology|mechanism\s+of\s+action|presentation|packing)\b\s*:?\s*$", re.I), 3),
    (re.compile(r"\beach\s+(?:capsule|tablet|film[- ]coated\s+tablet|sachet|\d+\s*ml)\s+contains\b", re.I), 3),
    (re.compile(r"\b(?:manufactured|marketed)\s+by\b|\bmfg\.?\s*lic|®|™", re.I), 2),
    (re.compile(r"for\s+the\s+use\s+only\s+of\s+a\s+(?:registered\s+)?medical\s+practitioner", re.I), 3),
    (MULTI_STRENGTH, 2),
)
LAB_SIGNALS = (
    (re.compile(r"\b(?:lab(?:oratory)?|biochemistry|haematology|hematology|pathology|diagnostics)\b", re.I), 2),
    (re.compile(r"\breference\s+(?:range|interval)\b|\bsample\s+collected\b|\bspecimen\b|\bcollected\s+on\b", re.I), 3),
    (re.compile(r"\breport\b", re.I), 1),
)
DISCHARGE_SIGNALS = (
    (re.compile(r"\bdischarge\s+summary\b|\bdate\s+of\s+discharge\b", re.I), 3),
    (re.compile(r"\bdate\s+of\s+admission\b|\badmitted\b|\bdischarged\b|\bip\s*no\b", re.I), 2),
)
PRESCRIPTION_SIGNALS = (
    (re.compile(r"(?m)^\s*rx\b", re.I), 3),
    (re.compile(r"\bsig\b|\bprescription\b|\brefill\b", re.I), 2),
    (re.compile(r"\bfollow\s*up\b|\breview\s+after\b|\badvice\b", re.I), 1),
    (re.compile(r"\breg\.?\s*no\b|\bmbbs\b|\bmd\b\s*\(", re.I), 1),
)
# Words that make a document medical at all: without them an invoice is just an invoice. A strength written
# without a space ("Amoxicillin 500mg Cap") is the ordinary spelling on a pharmacy bill, so the unit is matched
# after a digit instead of as a word of its own -- `\bmg\b` never matches "500mg".
MEDICAL_CONTENT = re.compile(
    r"\b(?:tabs?|tablets?|caps?|capsules?|syrup|syp|susp|injections?|inj|ointment|drops?|sachet|medical|medicals|"
    r"medicine|pharmacy|chemist|clinic|hospital|drug|dosage|prescription)\b"
    r"|\d\s?(?:mg|mcg|µg|ug|gm|ml|iu)\b", re.I)


@dataclass
class DocumentContext:
    """What the document is, decided from the document itself -- never from the entities found in it."""
    kind: DocumentType
    scores: dict[str, int] = field(default_factory=dict)

    @property
    def about_a_patient(self) -> bool:
        """Is this document about a person, or about products?

        A bill and a package insert name medicines, strengths, indications and adverse reactions without
        anyone being prescribed or diagnosed anything, so their medicines are only mentions. Everything
        else -- prescriptions, discharge summaries, lab reports, clinical notes, and documents that could
        not be placed -- may be about a patient; that keeps the medicines of a prescription bundled into a
        multi-page lab report.
        """
        return self.kind not in (DocumentType.medical_invoice, DocumentType.pharmaceutical_information)


def classify_document(text: str) -> DocumentContext:
    lines = [l for l in text.splitlines() if l.strip()]
    scores = {name: sum(points for pattern, points in signals if pattern.search(text))
              for name, signals in (("invoice", INVOICE_SIGNALS), ("product_info", PRODUCT_INFO_SIGNALS),
                                    ("lab", LAB_SIGNALS), ("discharge", DISCHARGE_SIGNALS),
                                    ("prescription", PRESCRIPTION_SIGNALS))}
    # Structure counts, not just words: a prescription lists dosage forms and dosing codes; a lab report
    # lists value+unit+range rows.
    scores["prescription"] += 2 if sum(bool(FORM_PREFIX.match(l.strip())) for l in lines) >= 2 else 0
    scores["prescription"] += 2 if len(FREQ_CODE.findall(text)) >= 2 else 0
    scores["lab"] += 2 if sum(bool(LAB_ROW_LINE.match(l)) for l in lines) >= 3 else 0
    medical = bool(MEDICAL_CONTENT.search(text))

    if scores["discharge"] >= 3:
        kind = DocumentType.discharge_summary
    elif scores["lab"] >= 3:
        kind = DocumentType.lab_report
    elif scores["invoice"] >= 5:
        kind = DocumentType.medical_invoice if medical else DocumentType.unknown
    elif scores["product_info"] >= 4:
        kind = DocumentType.pharmaceutical_information
    elif scores["prescription"] >= 4:
        kind = DocumentType.prescription
    elif medical and (scores["prescription"] or scores["lab"] or scores["product_info"]):
        kind = DocumentType.other_medical
    else:
        kind = DocumentType.unknown
    return DocumentContext(kind=kind, scores=scores)


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
    context = classify_document(text)
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
    _header(text, ents, make, context)

    for ls, le in _line_bounds(text):
        line = text[ls:le]
        on_line = [s for s in ner if ls <= s.start < le]

        # allergies: everything named on an allergy line is an allergen, never a prescription
        if (label := ALLERGY_LINE.search(line)) or NO_ALLERGY.search(line):
            body = ls + label.end() if label else le
            # "Allergies: None known" and "NKDA" record that there is nothing to list, so nothing is taken.
            # Spans must start after the label, or the word "Allergies" itself becomes an allergen.
            if not NO_ALLERGY.search(line) and not NO_CONTENT.match(text[body:le]):
                named = [s for s in on_line if s.kind in ("drug", "allergy", "disease") and s.start >= body]
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

        # Vitals are handled here and nowhere else, so "SpO2 98%" cannot become a lab result and the
        # model's "Pulse" span cannot become a symptom. Skipped when the line is prescription-shaped, so
        # "Inj Insulin 10 units, BP 140/90" does not lose its medicine.
        if not looks_prescribed and (vitals := _vitals(text, ls, le, make)):
            ents.vitals += vitals
            continue

        if PANEL_HEADING.match(line.strip()):   # a heading: the analytes are the rows beneath it
            start, end = _tidy(text, ls, le)
            if end > start:
                ents.panels.append(make(start, end, Method.pattern))
            continue

        if not looks_prescribed and _lab_results(text, ls, le, on_line, ents, make):
            continue

        # Selling, listing or advertising a medicine is a mention; only prescription context prescribes it.
        mention_only = (not context.about_a_patient or bool(INVOICE_ROW.search(line)) or bool(MULTI_STRENGTH.search(line)))
        found = _medications(text, ls, le, on_line, make, mention_only)
        (ents.medication_mentions if mention_only else ents.medications).extend(m for m, _ in found)
        claimed = [(m.name.start, segment_end) for m, segment_end in found]
        for s in on_line:
            inside_medication = any(a <= s.start < b for a, b in claimed)
            if s.kind == "test" and not inside_medication:
                ents.tests.append(make(s.start, s.end, Method.model, s.score))
            elif not found and s.kind == "disease":
                ents.diagnoses.append(make(s.start, s.end, Method.model, s.score))
            elif not found and s.kind == "symptom":
                ents.symptoms.append(make(s.start, s.end, Method.model, s.score))

    if not context.about_a_patient:
        # Indications, adverse reactions and billed services are the document's content, not a patient's record.
        ents.diagnoses, ents.symptoms, ents.allergies, ents.tests, ents.test_results = [], [], [], [], []

    ents.medication_mentions = _dedupe_mentions(ents.medication_mentions)
    ents.dosages = [m.dosage for m in ents.medications if m.dosage]
    ents.frequencies = [m.frequency for m in ents.medications if m.frequency]
    for name in ("diagnoses", "symptoms", "tests", "allergies"):
        setattr(ents, name, _dedupe(getattr(ents, name)))
    return ents, context.kind


def _header(text: str, ents: Entities, make, context: DocumentContext) -> None:
    if m := DOCTOR.search(text):
        words = m.group(0).split(" ")
        while len(words) > 2 and words[-1].strip(".,").upper() in CREDENTIALS:
            words.pop()
        name = " ".join(words).rstrip(",. ")
        ents.doctor_name = make(m.start(), m.start() + len(name), Method.pattern)
    _patient_name(text, ents, make, context)
    dates = list(DATE.finditer(text))
    if dates:
        labelled = [d for d in dates if re.search(r"date|dated|collected|admitted|\bon\b", _line_of(text, d.start()), re.I)]
        d = (labelled or dates)[0]
        ents.date = make(d.start(), d.end(), Method.pattern)


def _patient_name(text: str, ents: Entities, make, context: DocumentContext) -> None:
    """A name is only a PATIENT name when the document says so. "Name: Kamal" under bank details is an
    account holder; on a package insert it is nobody. A bare "Name:" is accepted only with patient-style
    demographics beside it and no payee/company words in the same block."""

    def keep(match: re.Match, reasons: tuple[str, ...] = ()) -> bool:
        words = match.group(1).split(" ")
        while words and words[-1].lower().strip(".") in NOT_NAME_WORDS:
            words.pop()
        if not words:
            return False
        name = " ".join(words).rstrip(".")
        ents.patient_name = make(match.start(1), match.start(1) + len(name), Method.pattern, reasons=reasons)
        return True

    for match in PATIENT_LABEL.finditer(text):        # explicit: "Patient:", "Patient Name:", "Pt:"
        if keep(match):
            return
    if not context.about_a_patient:      # an invoice or a package insert has no patient to name
        return
    for match in BARE_NAME_LABEL.finditer(text):      # bare "Name:" needs patient-style context around it
        block = _block_around(text, match.start())
        if DEMOGRAPHIC_CONTEXT.search(block) and not NOT_PATIENT_CONTEXT.search(block):
            if keep(match, ("name read from a bare 'Name:' label; check that it is the patient",)):
                return
    if match := PATIENT_NO_SEPARATOR.search(text):
        ents.patient_name = make(match.start(1), match.end(1), Method.pattern,
                                 reasons=("patient name read from a label without ':' -- check it is the name",))


def _block_around(text: str, position: int, radius: int = 2) -> str:
    """The line at `position` plus the lines just above and below it."""
    lines = text.splitlines()
    index = text.count("\n", 0, position)
    return "\n".join(lines[max(0, index - radius): index + radius + 1])


def _vitals(text: str, ls: int, le: int, make) -> list[TestResult]:
    """Observations on one line: "BP 120/80 mmHg", "Pulse 84/min", "SpO2 98%", "Temp 98.6 F".

    Same name/value/unit shape as a lab row, and deliberately the same type, but kept in a separate field:
    these are measured on the patient, not run in a laboratory.
    """
    line = text[ls:le]
    out = []
    for m in VITAL_MEASURE.finditer(line):
        out.append(TestResult(
            name=make(ls + m.start("name"), ls + m.end("name"), Method.pattern),
            value=make(ls + m.start("value"), ls + m.end("value"), Method.pattern),
            unit=make(ls + m.start("unit"), ls + m.end("unit"), Method.pattern) if m.group("unit") else None,
            source_line=line.strip(),
        ))
    return out


def _lab_results(text: str, ls: int, le: int, on_line: list[Span], ents: Entities, make) -> bool:
    """Lab rows: '<analyte> [(qualifier)] <value> [unit] [range]'. A span the model called a drug counts
    only with lab evidence (a lab unit or a reference range) -- vitamins and hormones are both."""
    found = False
    consumed: list[tuple[int, int]] = []   # stretches a row has already explained
    line = text[ls:le]

    def add(name: Entity, row: re.Match, base: int) -> None:
        ents.test_results.append(TestResult(
            name=name,
            value=make(base + row.start("value"), base + row.end("value"), Method.pattern),
            unit=make(base + row.start("unit"), base + row.end("unit"), Method.pattern) if row.group("unit") else None,
            reference_range=make(base + row.start("range"), base + row.end("range"), Method.pattern) if row.group("range") else None,
            source_line=line.strip(),
        ))

    for s in sorted((s for s in on_line if s.kind in ("test", "drug")), key=lambda s: s.start):
        if any(a <= s.start < b for a, b in consumed):
            continue    # an alias inside a row already read: "SGPT (ALT) 64 U/L" is one result, not two
        row = LAB_ROW.match(text, s.end, le)
        if not row or DATE.match(text, row.start("value")):
            if s.kind == "test":
                ents.tests.append(make(s.start, s.end, Method.model, s.score))
                found = True
            continue
        if s.kind == "drug" and not (row.group("unit") or row.group("range")):
            continue
        add(make(s.start, s.end, Method.model, s.score), row, 0)
        consumed.append((s.start, row.end()))
        found = True

    if not found and not NOT_MED_LINE.match(line) and not DATE.search(line):
        row = LAB_ROW_LINE.match(line)
        if row and (row.group("unit") or row.group("range")):
            name = make(ls + row.start("name"), ls + row.end("name"), Method.pattern,
                        reasons=("test name found by pattern only; the extraction model did not recognise it",))
            add(name, row, ls)
            found = True
    return found


def _medications(text: str, ls: int, le: int, on_line: list[Span], make,
                 mention_only: bool = False) -> list[tuple[Medication, int]]:
    """Medications on one line, each with the offset where its part of the line ends."""
    line = text[ls:le]
    if NOT_MED_LINE.match(line):
        return []
    cuts = [ls] + [ls + m.start(1) for m in SEGMENT_START.finditer(line) if m.start(1) > 3] + [le]
    out = []
    for seg_start, seg_end in zip(cuts, cuts[1:]):
        med = _medication(text, seg_start, seg_end, [s for s in on_line if seg_start <= s.start < seg_end],
                          make, line, mention_only)
        if med:
            out.append((med, seg_end))
    return out


def _medication(text: str, ss: int, se: int, spans: list[Span], make, line: str,
                mention_only: bool = False) -> Medication | None:
    pos = NUMBERING.match(text, ss, se).end()
    form = FORM_PREFIX.match(text, pos, se)
    drugs = [s for s in spans if s.kind == "drug"]
    if drugs:
        start, end, score, method = drugs[0].start, drugs[0].end, drugs[0].score, Method.model
        if f := FORM_PREFIX.match(text, start, end):             # "TAB. METFORMIN" -> "METFORMIN"
            start = f.end()
    elif mention_only and (product := FORM_SUFFIX.match(text, pos, se)):
        start, end, score, method = product.start(1), product.end(1), None, Method.pattern
        if text[start:end].lower() in NOT_PRODUCT_WORDS:
            return None
    elif mention_only:
        return None            # a mention needs a medicine name, from the model or a product pattern
    else:
        start, end, score, method = (form.end() if form else pos), se, None, Method.pattern
    # the name ends where the numbers or dosing codes begin: "Augmtin 625", "Montek LC HS"
    stop = re.search(r"\s(?=\d)|\s(?:" + FREQUENCY.pattern + ")", text[start:end], re.I)
    if stop and stop.start() > 0:
        end = start + stop.start()
    start, end = _tidy(text, start, end)
    name = text[start:end]
    # A strength is not a name: "1mg, 2mg, 5mg" must never become a medicine called "1mg".
    if end - start < 2 or not re.search(r"[A-Za-z]{3,}", name) or DOSE.fullmatch(name) or MULTI_STRENGTH.match(name):
        return None

    strengths = MULTI_STRENGTH.search(text, end, se)
    dose = DOSE.search(text, end, se)
    bare = None if dose else BARE_NUMBER.match(text, end, se)
    dose_span = (dose.start(), dose.end()) if dose else (bare.start(1), bare.end(1)) if bare else None
    if strengths:  # "Capsules 1mg, 2mg, 5mg": the range a product is sold in, not a dose anyone takes
        dose_span = None
    code, phrase = FREQ_CODE.search(text, end, se), FREQ_PHRASE.search(text, end, se)
    freq = min((m for m in (code, phrase) if m), key=lambda m: m.start(), default=None)
    dur = DURATION.search(text, end, se)
    if mention_only:
        # The claim is only "this medicine is named here", so no prescription evidence is required -- and
        # nothing is presented as a patient's dose. But nothing corroborates a mention either, so it needs
        # medicine-shaped evidence beside the name (a strength or a dosage form) or a confident model span.
        # "Face Mask (3 ply)" on a pharmacy invoice has neither: merchandise, not medicine.
        if not (dose_span or strengths or form or FORM_SUFFIX.match(text, pos, se)) and (
                score is None or score < EXTRACTOR_REVIEW_BELOW):
            return None
        why = ["named in the document; this is not evidence that it was prescribed or taken"]
        if method is Method.pattern:
            why.append("product name found by pattern only; the extraction model did not recognise it")
        return Medication(name=make(start, end, method, score, tuple(why)),
                          dosage=make(*dose_span, Method.pattern) if dose_span else None,
                          source_line=line.strip())

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
        if NO_CONTENT.match(text[s:e]):
            continue    # "No fever", "none", "nil": the document records an absence, which is not a finding
        inside = [n for n in named if s <= n.start < e]
        if len(inside) == 1 and (inside[0].end - inside[0].start) < 0.6 * (e - s):
            out.append(make(s, e, Method.model, inside[0].score))
        elif inside:
            out += [make(n.start, n.end, Method.model, n.score) for n in inside]
        else:
            out.append(make(s, e, Method.pattern, reasons=("section item found by pattern only; the extraction model did not recognise it",)))
    return out


def _line_bounds(text: str) -> list[tuple[int, int]]:
    bounds, start = [], 0
    for line in text.split("\n"):
        bounds.append((start, start + len(line)))
        start += len(line) + 1
    return bounds


def _line_of(text: str, pos: int) -> str:
    end = text.find("\n", pos)
    return text[text.rfind("\n", 0, pos) + 1: end if end != -1 else len(text)]


def _dedupe_mentions(items: list[Medication]) -> list[Medication]:
    """One mention per medicine. Product literature names its own product on nearly every line, and names it
    in several ways ("prazosin", "prazosin HCl", "prazosin hydrochloride") -- all the same evidence. Salt words
    are ignored for comparison only; the kept mention still quotes the document exactly."""
    seen, out = set(), []
    for m in items:
        words = [w for w in re.split(r"[\s.]+", m.name.text.lower()) if w]
        while len(words) > 1 and words[-1].strip("()") in SALT_WORDS:
            words.pop()
        key = " ".join(words)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _dedupe(items: list[Entity]) -> list[Entity]:
    seen, out = set(), []
    for e in items:
        key = e.text.lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out

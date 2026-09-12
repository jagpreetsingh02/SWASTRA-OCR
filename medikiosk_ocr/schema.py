"""The integration contract. Model-independent: nothing here names an OCR or NER model.

Every extracted value is an `Entity` that points back into `raw_text` by character offsets and
page index, so a reviewer (or a test) can always check it against the source. Values that were
not in the document are never produced; unknown fields stay `None` / empty.

Numbers attached to a value are described for what they are -- a generative model's token
probability, or an extractor's span score -- and neither is a probability of being correct.
`verification_required` is always true: nothing in this result is approved medical information.

Regenerate the published JSON schema after changing this file:
    .venv/bin/python -c "import medikiosk_ocr.schema as s; print(s.json_schema())" > contract/extraction_result.schema.json
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "2.0"

ERROR_CODES = {
    "empty_file": "The upload contained no bytes.",
    "unsupported_format": "Not a readable image or PDF (corrupt, encrypted, unknown type, or not page-shaped).",
    "file_too_large": "Over the byte limit, or an image with too many pixels to decode safely.",
    "too_many_pages": "More pages than the limit.",
    "ocr_failed": "The OCR model failed (not loaded, out of memory, runtime error).",
    "extraction_failed": "The extraction model failed, or produced values that are not verbatim spans of raw_text.",
    "internal_error": "An unexpected bug. Reported, never hidden as an empty result.",
    "invalid_request": "HTTP only: the request itself was malformed (e.g. no file field).",
}


class Status(str, Enum):
    ok = "ok"                          # read and extracted; individual values may still need review
    low_confidence = "low_confidence"  # read, but parts are doubtful -- see warnings and review_reasons
    unreadable = "unreadable"          # blank, no legible text, or text that is not trusted; no entities
    failed = "failed"                  # bad input or engine failure; see `error`


class DocumentType(str, Enum):
    prescription = "prescription"
    lab_report = "lab_report"
    discharge_summary = "discharge_summary"
    other_medical = "other_medical"
    unknown = "unknown"


class Method(str, Enum):
    model = "model"      # a span labelled by the extraction model
    pattern = "pattern"  # a deterministic pattern (dose units, dosing codes, dates, labelled headers, sections)


class Entity(BaseModel):
    text: str = Field(description="Exactly raw_text[start:end]; never normalised or corrected.")
    start: int = Field(description="Character offset into raw_text.")
    end: int
    page: int = Field(description="0-based index into `pages`.")
    method: Method
    ocr_confidence: float | None = Field(
        description="Lowest generative token probability (0-1) over these characters: how certain the OCR model "
                    "was, NOT how likely the text is correct. null when the text came from a PDF text layer.")
    extractor_score: float | None = Field(
        description="Extraction model span score (0-1) for method=model; null for method=pattern. Not a probability of correctness.")
    needs_review: bool = Field(description="True when there is a specific reason to doubt this value (see review_reasons). "
                                           "False does NOT mean verified: every value still requires human verification.")
    review_reasons: list[str] = Field(default_factory=list)


class Medication(BaseModel):
    name: Entity
    dosage: Entity | None = None
    frequency: Entity | None = None
    duration: Entity | None = None
    source_line: str


class TestResult(BaseModel):
    __test__ = False  # a lab test result, not a pytest test class

    name: Entity
    value: Entity | None = Field(None, description="The number only, e.g. '9.4'.")
    unit: Entity | None = Field(None, description="e.g. 'g/dL', when written next to the value.")
    reference_range: Entity | None = Field(None, description="e.g. '12.0 - 15.0', when written on the same line.")
    source_line: str


class Entities(BaseModel):
    patient_name: Entity | None = None
    date: Entity | None = None
    doctor_name: Entity | None = None
    medications: list[Medication] = []
    dosages: list[Entity] = Field(default_factory=list, description="The dosage of every medication, in order (same objects).")
    frequencies: list[Entity] = Field(default_factory=list, description="The frequency of every medication, in order (same objects).")
    diagnoses: list[Entity] = []
    symptoms: list[Entity] = []
    tests: list[Entity] = Field(default_factory=list, description="Tests mentioned or advised without a result.")
    test_results: list[TestResult] = []
    allergies: list[Entity] = []

    def values(self) -> list[Entity]:
        """Every extracted value once (dosages/frequencies are the medication fields, not repeated)."""
        out = [self.patient_name, self.doctor_name, self.date, *self.diagnoses, *self.symptoms, *self.tests, *self.allergies]
        for m in self.medications:
            out += [m.name, m.dosage, m.frequency, m.duration]
        for r in self.test_results:
            out += [r.name, r.value, r.unit, r.reference_range]
        return [v for v in out if v is not None]

    def is_empty(self) -> bool:
        return not self.values()


class Line(BaseModel):
    text: str
    start: int
    end: int
    ocr_confidence: float | None = Field(None, description="Mean generative token probability over the line's non-space "
                                                           "characters; null for text-layer pages. Not a correctness score.")
    review_reasons: list[str] = Field(default_factory=list)


class Page(BaseModel):
    index: int
    source: Literal["text_layer", "ocr", "text"] = Field(description="PDF text layer, OCR of an image, or text given directly.")
    status: Literal["ok", "blank", "no_text", "suspect"] = Field(
        description="blank: no ink, not sent to OCR. no_text: OCR found nothing legible. "
                    "suspect: text returned that the page does not support; withheld from extraction.")
    lines: list[Line] = []


class ErrorInfo(BaseModel):
    code: str = Field(description="One of: " + ", ".join(ERROR_CODES))
    message: str


class ExtractionResult(BaseModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    verification_required: Literal[True] = Field(True, description="Always true. Extracted values are unverified machine output.")
    status: Status
    document_type: DocumentType = DocumentType.unknown
    raw_text: str = Field("", description="Everything read, pages joined by a blank line. Kept even when extraction fails.")
    ocr_confidence: float | None = Field(None, description="Mean generative token probability over OCR'd characters; "
                                                           "null if no page was OCR'd. Not a correctness score.")
    entities: Entities = Entities()
    pages: list[Page] = []
    warnings: list[str] = []
    error: ErrorInfo | None = None
    engine: dict[str, str] = Field(default_factory=dict, description="Model identifiers, for audit only.")
    timings_ms: dict[str, int] = Field(default_factory=dict)


class DocumentError(Exception):
    """Raised for input problems. Turned into `status=failed` at the pipeline boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def json_schema() -> str:
    return json.dumps(ExtractionResult.model_json_schema(), indent=1)

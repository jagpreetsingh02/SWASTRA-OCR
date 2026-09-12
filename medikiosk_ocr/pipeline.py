"""The one execution path:

    bytes -> pages (preprocess) -> text (ocr) -> quality checks (validate) -> entities (extract)
          -> review flags (validate) -> grounding check -> ExtractionResult

Never raises: bad input, model failures and even bugs become `status=failed` with an error code,
and whatever was read (raw_text, pages) is still returned.
"""

from __future__ import annotations

import logging
import time

from . import extract, ocr, validate
from .preprocess import is_blank, load_document
from .schema import DocumentError, Entities, ErrorInfo, ExtractionResult, Line, Page, Status

log = logging.getLogger("medikiosk_ocr")

MIN_READABLE_ALNUM = 12      # fewer legible characters than this = nothing usable was read
LOW_LINE_CONFIDENCE = 0.60   # a line whose mean OCR token probability is below this makes the document low_confidence
LOW_DOC_CONFIDENCE = 0.80


def engine_info() -> dict[str, str]:
    return {"ocr": ocr.MODEL_ID, "extractor": f"{extract.NER_MODEL_ID} + patterns"}


def models_loaded() -> dict[str, bool]:
    return {"ocr": ocr.is_loaded(), "extractor": extract.is_loaded()}


def warm_up() -> None:
    """Load both models now instead of on the first request."""
    ocr.load()
    extract._ner()


def extract_document(data: bytes) -> ExtractionResult:
    started, timings = time.perf_counter(), {}
    try:
        return _extract_document(data, started, timings)
    except Exception as exc:  # a bug: report it as a failure, never as an empty success
        log.exception("internal error")
        return _done(ExtractionResult(status=Status.failed, error=ErrorInfo(
            code="internal_error", message=f"{type(exc).__name__}: {exc}"[:300])), started, timings, [])


def analyse_text(text: str) -> ExtractionResult:
    """Extraction, review flags and grounding on text you already have (no image, no OCR).
    Used by the evaluation's text mode to measure extraction with perfect OCR."""
    started, timings = time.perf_counter(), {}
    try:
        page = Page(index=0, source="text", status="ok", lines=_lines(text, None, 0, {}))
        return _extract(text, None, [page], [0], [], [], [], started, timings)
    except Exception as exc:
        log.exception("internal error")
        return _done(ExtractionResult(status=Status.failed, raw_text=text, error=ErrorInfo(
            code="internal_error", message=f"{type(exc).__name__}: {exc}"[:300])), started, timings, [])


def _extract_document(data: bytes, started: float, timings: dict[str, int]) -> ExtractionResult:
    warnings: list[str] = []
    try:
        pages_in = load_document(data)
    except DocumentError as exc:
        return _done(ExtractionResult(status=Status.failed, error=ErrorInfo(code=exc.code, message=exc.message)), started, timings, warnings)
    except Exception as exc:  # an image/PDF decoder failure we did not anticipate: still a structured result
        log.exception("could not decode document")
        return _done(ExtractionResult(status=Status.failed, error=ErrorInfo(
            code="unsupported_format", message=f"File could not be decoded: {type(exc).__name__}: {exc}"[:300])), started, timings, warnings)
    timings["preprocess"] = _ms(started)

    raw_text = ""
    char_conf: list[float | None] = []
    pages: list[Page] = []
    page_starts: list[int] = []
    withheld: list[tuple[int, int]] = []          # raw_text ranges not used for extraction
    context: list[tuple[int, int, str]] = []      # raw_text ranges with a doubt attached to their values
    t_ocr = time.perf_counter()
    any_ocr = False
    for page in pages_in:
        n = page.index + 1
        separator = "\n\n" if raw_text else ""  # pages are joined by a blank line; added only when this page adds text
        offset = len(raw_text) + len(separator)
        page_starts.append(offset)
        if page.note:
            warnings.append(page.note)

        if page.text_layer is not None:
            text, conf, source, check = page.text_layer, None, "text_layer", validate.PageCheck()
        elif is_blank(page.image):
            warnings.append(f"Page {n} appears blank; nothing was read from it.")
            pages.append(Page(index=page.index, source="ocr", status="blank"))
            continue
        else:
            any_ocr = True
            try:
                read = ocr.read_page(page.image)
            except Exception as exc:  # model/inference failure: fail clearly, keep what earlier pages gave
                log.exception("ocr failed on page %s", n)
                timings["ocr"] = _ms(t_ocr)
                return _done(ExtractionResult(
                    status=Status.failed, raw_text=raw_text, pages=pages,
                    error=ErrorInfo(code="ocr_failed", message=f"OCR failed on page {n}: {type(exc).__name__}: {exc}"[:300]),
                ), started, timings, warnings)
            text, conf, source = read.text, read.char_confidence, "ocr"
            check = validate.check_page(page.image, text, n)
            if read.truncated:
                reason = f"OCR output for page {n} hit the length limit; text may be incomplete or repeated"
                check.page_reasons.append(reason)
                warnings.append(f"Page {n}: {reason}.")

        warnings += check.warnings
        context += [(offset, offset + len(text), reason) for reason in check.page_reasons]
        withheld += [(offset + s, offset + e) for s, e in check.withheld]
        lines = _lines(text, conf, offset, check.line_reasons)
        context += [(line.start, line.end, reason) for line in lines for reason in line.review_reasons]
        if check.status == "suspect":
            status = "suspect"
        elif sum(ch.isalnum() for ch in text) < MIN_READABLE_ALNUM:
            status = "no_text"
            warnings.append(f"Page {n}: no legible text was found.")
        else:
            status = "ok"
        pages.append(Page(index=page.index, source=source, status=status, lines=lines))
        raw_text += separator + text
        char_conf += [None] * len(separator) + (conf if conf is not None else [None] * len(text))
    if any_ocr:
        timings["ocr"] = _ms(t_ocr)
    return _extract(raw_text, char_conf if any_ocr else None, pages, page_starts, withheld, context, warnings, started, timings)


def _extract(raw_text: str, char_conf: list[float | None] | None, pages: list[Page], page_starts: list[int],
             withheld: list[tuple[int, int]], context: list[tuple[int, int, str]], warnings: list[str],
             started: float, timings: dict[str, int]) -> ExtractionResult:
    ocr_values = [c for ch, c in zip(raw_text, char_conf or []) if c is not None and ch.isalnum()]
    ocr_confidence = round(sum(ocr_values) / len(ocr_values), 3) if ocr_values else None
    trusted = raw_text
    for s, e in withheld:  # same length, so entity offsets still index raw_text
        trusted = trusted[:s] + " " * (e - s) + trusted[e:]

    if sum(ch.isalnum() for ch in trusted) < MIN_READABLE_ALNUM:
        if not withheld:
            warnings.append("No legible text was found. Retake the photo with the page flat, in focus and well lit.")
        return _done(ExtractionResult(status=Status.unreadable, raw_text=raw_text, ocr_confidence=ocr_confidence,
                                      pages=pages), started, timings, warnings)

    t_extract = time.perf_counter()
    try:
        entities, doc_type = extract.extract_entities(trusted, char_conf, page_starts)
        validate.flag_entities(entities, raw_text, context)
        if ungrounded := _ungrounded(entities, raw_text, withheld):  # enforced here, whatever the extractor does
            raise ValueError(f"extractor returned values that are not verbatim spans of raw_text: {ungrounded[:3]}")
    except Exception as exc:
        log.exception("extraction failed")
        return _done(ExtractionResult(
            status=Status.failed, raw_text=raw_text, ocr_confidence=ocr_confidence, pages=pages,
            error=ErrorInfo(code="extraction_failed", message=f"{type(exc).__name__}: {exc}"[:300]),
        ), started, timings, warnings)
    timings["extraction"] = _ms(t_extract)

    low_lines = [l for p in pages for l in p.lines
                 if l.ocr_confidence is not None and l.ocr_confidence < LOW_LINE_CONFIDENCE and l.text.strip()]
    if low_lines:
        warnings.append(f"{len(low_lines)} line(s) were read with low OCR token probability; check them against the document.")
    if entities.is_empty():
        warnings.append("Text was read but no medical information was recognised.")
    doubtful = (low_lines or withheld or context or any(p.status in ("no_text", "suspect") for p in pages)
                or (ocr_confidence is not None and ocr_confidence < LOW_DOC_CONFIDENCE))
    return _done(ExtractionResult(
        status=Status.low_confidence if doubtful else Status.ok, document_type=doc_type, raw_text=raw_text,
        ocr_confidence=ocr_confidence, entities=entities, pages=pages,
    ), started, timings, warnings)


def _done(result: ExtractionResult, started: float, timings: dict[str, int], warnings: list[str]) -> ExtractionResult:
    timings["total"] = _ms(started)
    result.timings_ms = timings
    result.engine = engine_info()
    result.warnings = warnings + result.warnings
    return result


def _lines(text: str, conf: list[float] | None, offset: int, reasons: dict[int, list[str]]) -> list[Line]:
    out, pos = [], 0
    for i, line in enumerate(text.split("\n")):
        seg = [c for ch, c in zip(line, conf[pos:pos + len(line)]) if not ch.isspace()] if conf is not None else []
        out.append(Line(text=line, start=offset + pos, end=offset + pos + len(line),
                        ocr_confidence=round(sum(seg) / len(seg), 3) if seg else None,
                        review_reasons=list(reasons.get(i, []))))
        pos += len(line) + 1
    return out


def _ungrounded(e: Entities, raw_text: str, blocked: list[tuple[int, int]]) -> list[str]:
    """Values that are not literally raw_text[start:end], or that come from a range withheld from extraction."""
    return [
        v.text for v in e.values()
        if not (0 <= v.start <= v.end <= len(raw_text)) or raw_text[v.start:v.end] != v.text
        or any(s < v.end and v.start < end for s, end in blocked)
    ]


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)

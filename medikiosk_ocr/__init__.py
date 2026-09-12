"""MediKiosk OCR: medical document in, structured and unverified extraction out.

    from medikiosk_ocr import extract_document
    result = extract_document(open("rx.jpg", "rb").read())   # -> ExtractionResult
"""

from .schema import ExtractionResult


def extract_document(data: bytes) -> ExtractionResult:
    from .pipeline import extract_document as _run  # models load on first use, not on import

    return _run(data)


__all__ = ["ExtractionResult", "extract_document"]

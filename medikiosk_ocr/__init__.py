"""MediKiosk OCR: medical document in, structured and unverified extraction out.

    from medikiosk_ocr import extract_document
    result = extract_document(open("rx.jpg", "rb").read())   # -> ExtractionResult
"""

from .env import load_env
from .schema import ExtractionResult

load_env()  # local .env (e.g. HF_TOKEN); exported variables always win


def extract_document(data: bytes) -> ExtractionResult:
    from .pipeline import extract_document as _run  # models load on first use, not on import

    return _run(data)


__all__ = ["ExtractionResult", "extract_document", "load_env"]

"""HTTP interface. One endpoint does the work; the UI at / is a temporary test bench.

    .venv/bin/uvicorn medikiosk_ocr.api:app --port 8000

Environment:
    MEDIKIOSK_OCR_PRELOAD=0          do not load models at start-up (default: load in the background)
    MEDIKIOSK_OCR_MAX_CONCURRENT=1   documents processed at once; the rest wait (GPU inference is serialised anyway)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .pipeline import engine_info, extract_document, models_loaded, warm_up
from .preprocess import MAX_BYTES
from .schema import SCHEMA_VERSION, ErrorInfo, ExtractionResult, Status

log = logging.getLogger("medikiosk_ocr")
STATIC = Path(__file__).parent / "static"
EXTRACT_PATH = "/v1/extract"
_slots = asyncio.Semaphore(int(os.environ.get("MEDIKIOSK_OCR_MAX_CONCURRENT", "1")))
_warm_up_error: str | None = None


def _background_warm_up() -> None:
    global _warm_up_error
    try:
        warm_up()
    except Exception as exc:  # reported by /health; requests will fail with ocr_failed/extraction_failed
        _warm_up_error = f"{type(exc).__name__}: {exc}"[:300]
        log.exception("model warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("MEDIKIOSK_OCR_PRELOAD", "1") != "0":
        threading.Thread(target=_background_warm_up, name="model-warm-up", daemon=True).start()
    yield


app = FastAPI(title="MediKiosk OCR", version=SCHEMA_VERSION, lifespan=lifespan)


def _failure(code: str, message: str, http_status: int) -> JSONResponse:
    body = ExtractionResult(status=Status.failed, error=ErrorInfo(code=code, message=message), engine=engine_info())
    return JSONResponse(status_code=http_status, content=body.model_dump(mode="json"))


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Refuse bodies over the limit before they are read (multipart parsing would otherwise spool them)."""
    if request.url.path == EXTRACT_PATH:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BYTES + 64 * 1024:
            return _failure("file_too_large", f"Upload is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    if request.url.path == EXTRACT_PATH:
        return _failure("invalid_request", "Send the document as multipart/form-data in a field named 'file'.", 422)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health() -> dict:
    loaded = models_loaded()
    return {"status": "ok", "schema_version": SCHEMA_VERSION, "engine": engine_info(), "models_loaded": loaded,
            "ready": all(loaded.values()), "warm_up_error": _warm_up_error}


@app.post(EXTRACT_PATH, response_model=ExtractionResult)
async def extract(file: UploadFile = File(...)):
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data += chunk
        if len(data) > MAX_BYTES:  # no Content-Length (chunked upload): stop reading at the limit
            return _failure("file_too_large", f"Upload is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    async with _slots:
        # Inference is blocking; keep it off the event loop. Failures come back as status=failed, never as a 500.
        return await run_in_threadpool(extract_document, bytes(data))

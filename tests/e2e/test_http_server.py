"""The real thing: start uvicorn, upload documents over HTTP, check what a browser would receive.

Loads the real Qwen3-VL and GLiNER models (~6 GB, several minutes on first run). This is the test
that proves the test bench works end to end; it is not a mock.
"""

import json
import socket
import subprocess
import sys
import time

import httpx
import pytest

from ..conftest import DEV, ROOT

BOOT_TIMEOUT = 180  # model load on first request can be slow


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = free_port()
    process = subprocess.Popen(
        [str(ROOT / ".venv" / "bin" / "uvicorn"), "medikiosk_ocr.api:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + BOOT_TIMEOUT
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.fail(f"server exited: {process.stdout.read()[-2000:]}")
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            pytest.fail("server did not start")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


def test_root_serves_the_test_bench_as_html(server):
    response = httpx.get(server + "/", timeout=30)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "MediKiosk OCR" in response.text


def test_health_reports_models_and_device_without_the_token(server):
    body = httpx.get(server + "/health", timeout=30).json()
    assert body["status"] == "ok" and body["service"] == "medikiosk-ocr"
    assert body["models"] == {"ocr": "Qwen/Qwen3-VL-2B-Instruct", "extraction": "Ihor/gliner-biomed-large-v1.0"}
    assert body["device"] in {"cuda", "mps", "cpu"}
    assert isinstance(body["huggingface_token_configured"], bool)
    assert "token" not in json.dumps(body).lower().replace("huggingface_token_configured", "")


def test_uploading_a_printed_prescription_returns_json_with_real_ocr(server):
    with open(DEV / "prescription_scan.png", "rb") as handle:
        response = httpx.post(server + "/v1/extract", files={"file": ("prescription_scan.png", handle, "image/png")},
                              timeout=BOOT_TIMEOUT)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    result = response.json()
    assert result["status"] in ("ok", "low_confidence") and result["verification_required"] is True
    assert "METFORMIN" in result["raw_text"]                      # Qwen actually read the page
    names = {m["name"]["text"] for m in result["entities"]["medications"]}
    assert {"METFORMIN", "AMLODIPINE", "ATORVASTATIN", "OMEPRAZOLE"} <= names   # GLiNER actually ran
    assert result["pages"][0]["source"] == "ocr" and result["ocr_confidence"] is not None
    assert result["timings_ms"]["total"] > 0


def test_digital_pdf_uses_its_text_layer_over_http(server):
    with open(DEV / "lab_report.pdf", "rb") as handle:
        result = httpx.post(server + "/v1/extract", files={"file": ("lab_report.pdf", handle, "application/pdf")},
                            timeout=BOOT_TIMEOUT).json()
    assert result["pages"][0]["source"] == "text_layer" and result["ocr_confidence"] is None
    assert len(result["entities"]["test_results"]) == 7


@pytest.mark.parametrize("name,payload,code", [
    ("empty.png", b"", "empty_file"),
    ("notes.txt", b"just some text, not a document", "unsupported_format"),
    ("broken.png", (DEV / "prescription_scan.png").read_bytes()[:4000], "unsupported_format"),
])
def test_bad_uploads_return_structured_json_not_html(server, name, payload, code):
    response = httpx.post(server + "/v1/extract", files={"file": (name, payload, "application/octet-stream")}, timeout=60)
    assert response.headers["content-type"].startswith("application/json")
    assert not response.text.lstrip().startswith("<")
    body = response.json()
    assert body["status"] == "failed" and body["error"]["code"] == code and body["error"]["message"]


def test_missing_file_field_returns_structured_json(server):
    response = httpx.post(server + "/v1/extract", data={"wrong": "field"}, timeout=30)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "invalid_request"

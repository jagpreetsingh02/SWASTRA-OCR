"""HTTP behaviour with the pipeline stubbed. No weights needed."""

import json
import os

os.environ["MEDIKIOSK_OCR_PRELOAD"] = "0"  # never load models from these tests

import pytest
from fastapi.testclient import TestClient

from medikiosk_ocr import api
from medikiosk_ocr.schema import ExtractionResult, Status


@pytest.fixture
def client():
    with TestClient(api.app) as c:
        yield c


def test_health_reports_version_engine_and_load_state_without_loading_models(client):
    from medikiosk_ocr import pipeline

    before = pipeline.models_loaded()           # whatever earlier tests in this process left loaded
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["schema_version"] == "2.0"
    assert set(body["models_loaded"]) == {"ocr", "extractor"}
    assert body["models_loaded"] == before and body["ready"] == all(before.values())
    assert pipeline.models_loaded() == before, "/health must not load models"
    assert body["engine"]["ocr"] and body["engine"]["extractor"]


def test_ui_is_served(client):
    assert "MediKiosk OCR" in client.get("/").text


def test_document_is_passed_to_the_pipeline_and_the_contract_comes_back(client, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "extract_document", lambda data: seen.append(data) or ExtractionResult(status=Status.ok, raw_text="hi"))
    response = client.post("/v1/extract", files={"file": ("rx.jpg", b"\xff\xd8 image bytes", "image/jpeg")})
    assert response.status_code == 200 and response.json()["raw_text"] == "hi"
    assert seen == [b"\xff\xd8 image bytes"]


def test_missing_file_field_is_a_structured_422(client):
    response = client.post("/v1/extract", data={"not_file": "x"})
    body = response.json()
    assert response.status_code == 422
    assert body["status"] == "failed" and body["error"]["code"] == "invalid_request" and body["schema_version"] == "2.0"


def test_oversized_upload_is_refused_with_a_structured_413(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_BYTES", 1000)
    monkeypatch.setattr(api, "extract_document", lambda data: pytest.fail("pipeline must not run"))
    response = client.post("/v1/extract", files={"file": ("big.png", b"x" * 200_000, "image/png")})
    assert response.status_code == 413 and response.json()["error"]["code"] == "file_too_large"


@pytest.mark.parametrize("payload,code", [(b"", "empty_file"), (b"not a document", "unsupported_format"),
                                          (b"%PDF-1.7 garbage", "unsupported_format")])
def test_bad_files_are_http_200_with_status_failed(client, payload, code):
    response = client.post("/v1/extract", files={"file": ("x.bin", payload, "application/octet-stream")})
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and response.json()["error"]["code"] == code


# ---------------------------------------------------------------- the test bench must never get HTML

def test_the_ui_is_html_but_the_api_never_is(client, monkeypatch):
    assert client.get("/").headers["content-type"].startswith("text/html")
    monkeypatch.setattr(api, "extract_document", lambda data: ExtractionResult(status=Status.ok, raw_text="hi"))
    responses = [
        client.post("/v1/extract", files={"file": ("rx.png", b"\x89PNG bytes", "image/png")}),   # success path
        client.post("/v1/extract", files={"file": ("empty.bin", b"", "application/octet-stream")}),  # handled failure
        client.post("/v1/extract", data={"wrong": "field"}),                                     # request error
    ]
    for response in responses:
        assert response.headers["content-type"].startswith("application/json"), response.text[:200]
        assert not response.text.lstrip().startswith("<"), "the API must never answer an upload with HTML"
        assert "status" in response.json()


def test_unknown_paths_answer_json_not_an_html_error_page(client):
    response = client.get("/v1/extarct")  # typo in the path: still JSON, so the page can report it
    assert response.status_code == 404 and response.headers["content-type"].startswith("application/json")


def test_health_reports_models_and_device_but_never_the_token(client, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value_that_must_not_leak")
    body = client.get("/health").json()
    assert body["models"] == {"ocr": "Qwen/Qwen3-VL-2B-Instruct", "extraction": "Ihor/gliner-biomed-large-v1.0"}
    assert body["device"] in {"cuda", "mps", "cpu", "unavailable"}
    assert body["huggingface_token_configured"] is True
    assert "hf_secret_value_that_must_not_leak" not in json.dumps(body)

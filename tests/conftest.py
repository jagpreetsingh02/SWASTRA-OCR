"""Shared helpers.

tests/unit         no model weights; OCR and extraction are stubbed where the pipeline would reach them
tests/integration  needs the GLiNER weights (extraction runs for real); OCR is stubbed
tests/e2e          needs both models; slow

Tests use eval/dev and eval/controls only. eval/heldout is for evaluation, never for tests or tuning.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "eval" / "dev"
CONTROLS = ROOT / "eval" / "controls"


def image_bytes(img: Image.Image, fmt: str = "PNG", **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def noise_image() -> Image.Image:
    return Image.fromarray(np.random.default_rng(0).integers(0, 255, (1754, 1240, 3), dtype=np.uint8))


def dark_object_image() -> Image.Image:
    img = Image.new("RGB", (1240, 1754), "white")
    img.paste((20, 20, 20), (300, 500, 900, 1100))  # e.g. a phone lying on an empty sheet
    return img


def dust_image() -> Image.Image:
    page = np.full((1754, 1240, 3), 205, dtype=np.uint8)
    for y in range(60, 1754, 100):
        for x in range(50, 1240, 100):
            page[y:y + 4, x:x + 4] = 40
    return Image.fromarray(page)


@pytest.fixture
def fake_ocr(monkeypatch):
    """Replace the OCR model: fake_ocr("text") or fake_ocr(["page 1 text", "page 2 text"]) or fake_ocr(RuntimeError())."""
    from medikiosk_ocr import ocr

    calls = []

    def install(output, confidence: float = 0.99, truncated: bool = False):
        outputs = output if isinstance(output, list) else None

        def read_page(image):
            calls.append(image.size)
            value = outputs[len(calls) - 1] if outputs is not None else output
            if isinstance(value, Exception):
                raise value
            return ocr.PageText(text=value, char_confidence=[confidence] * len(value), truncated=truncated)

        monkeypatch.setattr(ocr, "read_page", read_page)
        return calls

    return install

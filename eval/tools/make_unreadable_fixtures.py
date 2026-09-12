"""Realistic "the patient's photo is useless" inputs, for hallucination testing.

    .venv/bin/python eval/tools/make_unreadable_fixtures.py

A generative OCR model that returns fluent text for any of these is inventing it. Pure noise,
dust and a dark object on a white page are generated inside eval/run.py and the tests.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

EVAL = Path(__file__).resolve().parents[1]
SOURCE = EVAL / "dev" / "prescription_scan.png"
CONTROLS = EVAL / "controls"


def main() -> None:
    src = Image.open(SOURCE).convert("RGB")
    CONTROLS.mkdir(exist_ok=True)

    # 1. motion/defocus blur so strong no character survives
    src.filter(ImageFilter.GaussianBlur(14)).save(CONTROLS / "unreadable_blurred.jpg", quality=85)

    # 2. underexposed night photo: almost black, heavy sensor noise
    dark = np.asarray(ImageEnhance.Brightness(src).enhance(0.06), dtype=np.float32)
    dark += np.random.default_rng(1).normal(0, 9, dark.shape)
    Image.fromarray(np.clip(dark, 0, 255).astype(np.uint8)).save(CONTROLS / "unreadable_dark.jpg", quality=85)

    # 3. photo of a table top with no document in it (wood-ish texture, no text)
    rng = np.random.default_rng(2)
    grain = np.cumsum(rng.normal(0, 1, (1600, 1200)), axis=1)
    grain = (grain - grain.min()) / (np.ptp(grain) + 1e-6)
    table = np.stack([120 + 60 * grain, 80 + 40 * grain, 50 + 25 * grain], axis=-1)
    Image.fromarray(table.astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)).save(CONTROLS / "no_document_table.jpg", quality=85)
    print("wrote unreadable_blurred.jpg, unreadable_dark.jpg, no_document_table.jpg to", CONTROLS)


if __name__ == "__main__":
    main()

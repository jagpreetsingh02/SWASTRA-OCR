"""Generate the dev synthetic handwritten and mixed printed+handwritten prescriptions.

    .venv/bin/python eval/tools/make_handwritten_fixtures.py

Writes, per document: eval/dev/<name>.png and <name>.txt (the exact text on the page). Truth files
(<name>.truth.json) are maintained by hand in the format described in eval/README.md.

All content is invented: no real patient or doctor. Handwriting is simulated with macOS handwriting
fonts plus per-character rotation/size jitter, baseline drift, uneven ink, page skew, blur, noise and
an illumination gradient. This is still MUCH easier than real doctors' handwriting -- treat scores on
these as an upper bound, not as field accuracy. `_write_hand` is also used by make_heldout_fixtures.py.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "dev"
FONTS = Path("/System/Library/Fonts/Supplemental")

DOCS = [
    {
        "name": "hw_rx_bradley",
        "font": "Bradley Hand Bold.ttf",
        "printed_header": None,
        "lines": [
            "Dr A. Kulkarni  MBBS",
            "Date 12/08/2026",
            "Pt: Rohan Mehta  34/M",
            "c/o fever, sore throat x 2 days",
            "Dx: URTI",
            "Allergy: sulfa drugs",
            "Rx",
            "Tab Azithral 500 OD x 3d",
            "Syp Crocin 5ml TDS",
            "Tab Cetirizine 10mg HS x 5d",
        ],
    },
    {
        "name": "hw_rx_cursive",
        "font": "SnellRoundhand.ttc",
        "printed_header": None,
        "lines": [
            "Dr Priya Iyer",
            "Date 21/07/2026",
            "Dx: T2DM, HTN",
            "Rx",
            "Tab Glycomet 500 BD",
            "Tab Telma 40 OD",
            "Tab Ecosprin 75 OD",
            "Adv: HbA1c, lipid profile",
        ],
    },
    {
        "name": "hw_rx_chalkboard",
        "font": "Chalkboard.ttc",
        "printed_header": None,
        "lines": [
            "Dr M. Das",
            "05/06/2026",
            "c/o acidity, cough",
            "NKDA",
            "Cap Omez 20 OD bf x 14d",
            "Tab Dolo 650 SOS",
            "Tab Montek LC HS x 10d",
        ],
    },
    {
        "name": "hw_rx_brush_hard",
        "font": "Brush Script.ttf",
        "printed_header": None,
        "lines": [
            "Dr K. Singh",
            "Date 30/05/2026",
            "Dx: Hypothyroidism",
            "TSH 7.2",
            "Tab Thyronorm 50mcg OD",
            "Tab Shelcal 500 BD",
        ],
    },
    {
        "name": "mixed_printed_handwritten",
        "font": "Bradley Hand Bold.ttf",
        "printed_header": [
            "SUNRISE MEDICAL CENTRE",
            "Dr. Neha Kapoor, MD (Paediatrics)   Reg. No. MH/55821",
            "Patient: Aarav Joshi        Date: 18/08/2026",
        ],
        "lines": [
            "Wt 18 kg",
            "c/o loose stools x 3 days",
            "Dx: Acute gastroenteritis",
            "ORS 1 sachet after each stool",
            "Syp Zinconia 5ml OD x 14d",
            "Syp Ondem 2ml SOS",
        ],
    },
]

W, H = 1240, 1754


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _write_hand(page: Image.Image, text: str, x: int, y: int, font_name: str, rng: random.Random) -> None:
    base_size = 44
    drift_phase = rng.uniform(0, math.tau)
    for i, ch in enumerate(text):
        size = int(base_size * rng.uniform(0.9, 1.08))
        font = _load_font(font_name, size)
        if ch == " ":
            x += int(size * rng.uniform(0.3, 0.45))
            continue
        box = font.getbbox(ch)
        glyph = Image.new("L", (box[2] + 20, size * 2), 0)
        ImageDraw.Draw(glyph).text((10, size // 3), ch, font=font, fill=int(255 * rng.uniform(0.7, 1.0)))
        glyph = glyph.rotate(rng.uniform(-7, 7), resample=Image.BICUBIC, expand=False)
        dy = int(6 * math.sin(drift_phase + i / 6)) + rng.randint(-2, 2)
        ink = Image.new("RGB", glyph.size, (rng.randint(10, 40), rng.randint(20, 45), rng.randint(70, 110)))
        page.paste(ink, (x - 10, y + dy - size // 3), glyph)
        x += max(box[2] - box[0], 6) + rng.randint(-2, 3)


def render(doc: dict, seed: int) -> Image.Image:
    rng = random.Random(seed)
    page = Image.new("RGB", (W, H), (248, 246, 240))
    draw = ImageDraw.Draw(page)
    y = 110
    if doc["printed_header"]:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
        for line in doc["printed_header"]:
            draw.text((110, y), line, font=font, fill=(20, 20, 20))
            y += 52
        draw.line((100, y + 5, W - 100, y + 5), fill=(60, 60, 60), width=2)
        y += 50
    for line in doc["lines"]:
        _write_hand(page, line, 120 + rng.randint(-8, 8), y, doc["font"], rng)
        y += 78 + rng.randint(-6, 8)

    # camera/scan artefacts
    page = page.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, fillcolor=(230, 228, 222))
    page = page.filter(ImageFilter.GaussianBlur(0.8))
    arr = np.asarray(page, dtype=np.float32)
    gx = np.linspace(1.0, 0.82, W)[None, :, None]
    gy = np.linspace(0.95, 1.0, H)[:, None, None]
    arr = arr * gx * gy + np.random.default_rng(seed).normal(0, 7, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, doc in enumerate(DOCS):
        render(doc, seed=100 + i).save(OUT / f"{doc['name']}.png")
        text = "\n".join((doc["printed_header"] or []) + doc["lines"])
        (OUT / f"{doc['name']}.txt").write_text(text + "\n")
        print("wrote", doc["name"], "(truth stays in eval/dev/*.truth.json)")


if __name__ == "__main__":
    main()

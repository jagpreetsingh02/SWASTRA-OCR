"""Render the two semantic dev fixtures as realistic pages.

    .venv/bin/python eval/tools/make_semantic_fixtures.py

Both came from real manual tests that the engine interpreted wrongly:

* invoice_pharmacy_gst  -- a pharmacy GST invoice: a table with columns, so the page has far more
  lines of writing than a simple ink-band count suggests. Products are mentions, not prescriptions.
* pharma_info_minipress_letter -- printed product information plus an unrelated handwritten letter,
  i.e. a mixed printed/handwritten page that is not a prescription.

Text and truth live in eval/dev/<name>.txt / .truth.json; this only draws them.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_handwritten_fixtures import _write_hand  # noqa: E402

DEV = Path(__file__).resolve().parents[1] / "dev"
SUPP = Path("/System/Library/Fonts/Supplemental")
W, H = 1240, 1754


def scan(page: Image.Image, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    page = page.rotate(float(rng.uniform(-0.8, 0.8)), resample=Image.BICUBIC, fillcolor=(240, 240, 237))
    page = page.filter(ImageFilter.GaussianBlur(0.5))
    arr = np.asarray(page, dtype=np.float32) + rng.normal(0, 4, (H, W, 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def invoice() -> Image.Image:
    page = Image.new("RGB", (W, H), (252, 252, 250))
    draw = ImageDraw.Draw(page)
    bold = ImageFont.truetype(str(SUPP / "Arial Bold.ttf"), 30)
    mono = ImageFont.truetype(str(SUPP / "Courier New.ttf"), 24)
    small = ImageFont.truetype(str(SUPP / "Arial.ttf"), 22)
    lines = (DEV / "invoice_pharmacy_gst.txt").read_text().splitlines()

    draw.rectangle((70, 60, W - 70, 140), outline=(40, 40, 40), width=2)
    draw.text((90, 78), lines[0], font=bold, fill=(20, 20, 20))
    y = 165
    for line in lines[1:4]:
        draw.text((90, y), line, font=small, fill=(25, 25, 25))
        y += 34
    y += 20
    draw.line((70, y - 8, W - 70, y - 8), fill=(60, 60, 60), width=2)
    for line in lines[5:9]:                      # the table: header + three product rows
        draw.text((90, y), line, font=mono, fill=(20, 20, 20))
        y += 40
        draw.line((70, y - 10, W - 70, y - 10), fill=(170, 170, 170), width=1)
    for x in (70, 210, 660, 780, 870, 990, W - 70):
        draw.line((x, 250, x, y - 10), fill=(170, 170, 170), width=1)
    y += 20
    for line in lines[10:14]:                    # totals block, right aligned
        draw.text((640, y), line.strip(), font=mono, fill=(20, 20, 20))
        y += 34
    y += 30
    draw.text((90, y), lines[15], font=bold, fill=(20, 20, 20))
    y += 40
    for line in lines[16:]:
        draw.text((90, y), line, font=small, fill=(25, 25, 25))
        y += 32
    return scan(page, 21)


def pharma_page() -> Image.Image:
    page = Image.new("RGB", (W, H), (250, 249, 245))
    draw = ImageDraw.Draw(page)
    title = ImageFont.truetype(str(SUPP / "Times New Roman.ttf"), 42)
    body = ImageFont.truetype(str(SUPP / "Times New Roman.ttf"), 25)
    heading = ImageFont.truetype(str(SUPP / "Arial Bold.ttf"), 24)
    lines = (DEV / "pharma_info_minipress_letter.txt").read_text().splitlines()
    printed, letter = lines[:20], [l for l in lines[20:] if l.strip()]

    y = 70
    draw.text((90, y), printed[0], font=title, fill=(15, 15, 15))
    y += 56
    for line in printed[1:3]:
        draw.text((90, y), line, font=body, fill=(25, 25, 25))
        y += 32
    y += 10
    for line in printed[3:]:
        if not line.strip():
            y += 12
            continue
        is_heading = line.isupper() and len(line) < 40
        draw.text((90, y), line, font=heading if is_heading else body, fill=(15, 15, 15))
        y += 34 if is_heading else 30
    draw.line((90, y + 14, W - 90, y + 14), fill=(120, 120, 120), width=1)

    rng = random.Random(7)
    y += 60
    for line in letter:                          # the handwritten letter, same renderer as the hw fixtures
        _write_hand(page, line, 110 + rng.randint(-6, 6), y, "Bradley Hand Bold.ttf", rng)
        y += 74
    return scan(page, 22)


def main() -> None:
    invoice().save(DEV / "invoice_pharmacy_gst.png")
    pharma_page().save(DEV / "pharma_info_minipress_letter.png")
    print("wrote invoice_pharmacy_gst.png and pharma_info_minipress_letter.png to", DEV)


if __name__ == "__main__":
    main()

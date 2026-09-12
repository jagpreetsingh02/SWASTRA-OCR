"""Render the frozen held-out set (eval/heldout/hx_*.txt + .truth.json) to document images.

    .venv/bin/python eval/tools/make_heldout_fixtures.py

The held-out transcriptions and truth were written before the extraction rules were revised and
must never be used to tune them. Typefaces and handwriting styles here are deliberately NOT the
ones used for the dev set. Also produces a phone photo saved as HEIC with EXIF rotation, a
degraded JPEG, a two-page scanned PDF, and MANIFEST.sha256 (eval/run.py warns if any held-out
file changes afterwards). All content is invented: no real patient, doctor or clinic.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
import pillow_heif
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_handwritten_fixtures import _write_hand  # noqa: E402  (same renderer, different hands)

HELDOUT = Path(__file__).resolve().parents[1] / "heldout"
SUPP = Path("/System/Library/Fonts/Supplemental")
W, H = 1240, 1754


def lines_of(stem: str) -> list[str]:
    return [l for l in (HELDOUT / f"{stem}.txt").read_text().splitlines() if l.strip()]


def printed(lines: list[str], font_file: str, size: int = 30, pitch: int = 52) -> Image.Image:
    page = Image.new("RGB", (W, H), (250, 250, 247))
    draw = ImageDraw.Draw(page)
    font = ImageFont.truetype(str(SUPP / font_file), size)
    for i, line in enumerate(lines):
        draw.text((90, 110 + i * pitch), line, font=font, fill=(25, 25, 25))
    return page


def handwritten(lines: list[str], font_file: str, seed: int, header: list[str] | None = None) -> Image.Image:
    rng = random.Random(seed)
    page = Image.new("RGB", (W, H), (248, 246, 240))
    y = 110
    if header:
        draw = ImageDraw.Draw(page)
        font = ImageFont.truetype(str(SUPP / "Arial.ttf"), 28)
        for line in header:
            draw.text((90, y), line, font=font, fill=(20, 20, 20))
            y += 50
        draw.line((80, y + 5, W - 80, y + 5), fill=(60, 60, 60), width=2)
        y += 50
    for line in lines:
        _write_hand(page, line, 100 + rng.randint(-6, 6), y, font_file, rng)
        y += 82 + rng.randint(-5, 8)
    return page


def scan(page: Image.Image, seed: int, strength: float = 1.0) -> Image.Image:
    rng = np.random.default_rng(seed)
    page = page.rotate(float(rng.uniform(-1.2, 1.2)) * strength, resample=Image.BICUBIC, fillcolor=(235, 235, 232))
    page = page.filter(ImageFilter.GaussianBlur(0.5 + 0.9 * (strength - 1)))
    arr = np.asarray(page, dtype=np.float32)
    if strength > 1:
        arr = 128 + (arr - 128) * 0.65  # low contrast
    arr += rng.normal(0, 5 * strength, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _perspective_coeffs(dst, src):
    rows = []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(rows, dtype=float), np.array(src, dtype=float).reshape(8)).tolist()


def photo(page: Image.Image, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    canvas = Image.new("RGB", (1500, 2000), (72, 66, 60))
    canvas.paste(page.resize((1200, 1698)), (150, 150))
    w, h = canvas.size
    coeffs = _perspective_coeffs([(70, 40), (w - 30, 95), (w - 90, h - 35), (25, h - 80)], [(0, 0), (w, 0), (w, h), (0, h)])
    img = canvas.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    arr = np.asarray(img, dtype=np.float32)
    arr *= np.linspace(0.72, 1.04, w)[None, :, None] * np.linspace(1.0, 0.9, h)[:, None, None]
    arr += rng.normal(0, 6, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9))


def main() -> None:
    pillow_heif.register_heif_opener()
    out: dict[str, Image.Image] = {}

    gp = scan(printed(lines_of("hx_rx_printed_gp"), "Times New Roman.ttf"), 1)
    out["hx_rx_printed_gp.png"] = gp
    out["hx_rx_hand_iqbal.png"] = scan(handwritten(lines_of("hx_rx_hand_iqbal"), "Chalkduster.ttf", 11), 2)
    out["hx_rx_hand_banerjee.png"] = scan(handwritten(lines_of("hx_rx_hand_banerjee"), "Apple Chancery.ttf", 12), 3)
    cbc = scan(printed(lines_of("hx_lab_cbc"), "Courier New.ttf", size=26, pitch=48), 4)
    out["hx_lab_cbc.png"] = cbc
    out["hx_lab_cbc_degraded.jpg"] = scan(printed(lines_of("hx_lab_cbc"), "Courier New.ttf", size=26, pitch=48), 5, strength=2.0)
    biochem = scan(printed(lines_of("hx_lab_biochem"), "Georgia.ttf", size=29), 6)
    out["hx_lab_biochem.png"] = biochem
    out["hx_discharge_kmc.png"] = scan(printed(lines_of("hx_discharge_kmc"), "Times New Roman.ttf", size=28), 7)
    paed = lines_of("hx_mixed_paed")
    out["hx_mixed_paed.png"] = scan(handwritten(paed[3:], "Comic Sans MS.ttf", 13, header=paed[:3]), 8)
    out["hx_nonmedical_notice.png"] = scan(printed(lines_of("hx_nonmedical_notice"), "Verdana.ttf", size=24), 9)

    for name, img in out.items():
        path = HELDOUT / name
        if name.endswith(".jpg"):
            img.save(path, quality=60)
        else:
            img.save(path)

    # Phone photo of the printed prescription, stored rotated with EXIF orientation 6, as HEIC.
    exif = Image.Exif()
    exif[0x0112] = 6
    photo(gp, 10).rotate(90, expand=True).save(HELDOUT / "hx_rx_printed_gp_photo.heic", format="HEIF", quality=80, exif=exif.tobytes())

    # Two-page scanned PDF (image-only pages): CBC then biochemistry, with merged truth/transcription.
    cbc.save(HELDOUT / "hx_labs_2page.pdf", format="PDF", save_all=True, append_images=[biochem], resolution=150)
    first, second = (json.loads((HELDOUT / f"{s}.truth.json").read_text()) for s in ("hx_lab_cbc", "hx_lab_biochem"))
    merged = {**first, "test_results": first["test_results"] + second["test_results"]}
    (HELDOUT / "hx_labs_2page.truth.json").write_text(json.dumps(merged, indent=1) + "\n")
    (HELDOUT / "hx_labs_2page.txt").write_text(
        (HELDOUT / "hx_lab_cbc.txt").read_text().rstrip("\n") + "\n\n" + (HELDOUT / "hx_lab_biochem.txt").read_text())

    manifest = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
        for p in sorted(HELDOUT.iterdir()) if p.is_file() and p.name != "MANIFEST.sha256"
    )
    (HELDOUT / "MANIFEST.sha256").write_text(manifest)
    print("wrote", len(out) + 2, "held-out images and MANIFEST.sha256")


if __name__ == "__main__":
    main()

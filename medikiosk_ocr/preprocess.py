"""Bytes in, pages out. No model code here.

Deliberately light: decoding, orientation, colour depth, size, and a blank-page check. Binarisation
and deskew are not done -- the OCR model reads degraded scans and handheld photos without them, and
hard thresholding hurts neural OCR on photographs.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

import numpy as np
import pillow_heif
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from .schema import DocumentError

pillow_heif.register_heif_opener()  # iPhone photos (HEIC/HEIF)

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 10
MAX_PIXELS = 80_000_000      # decoded image size limit (80 MP); above this decoding is refused
PDF_RENDER_DPI = 200
MAX_RENDER_SIDE = 3000       # px; a PDF page is never rasterised larger than this, whatever its declared size
MAX_LONG_SIDE = 2400         # bigger photos are downscaled; phone photos are ~4000px
MIN_TEXT_LAYER_CHARS = 20    # a PDF page with fewer alphanumerics than this is treated as a scan
SCANNED_IMAGE_COVERAGE = 0.5 # a PDF page this much covered by images is a scan, even if it has a text layer
MIN_SIDE = 32                # px; smaller is not a document page (and breaks resizing)
MAX_ASPECT = 20              # longer side / shorter side; beyond this it is not a page
WIDE_MODES = ("I;16", "I;16B", "I;16L", "I;16N", "I", "F")  # 16/32-bit greyscale

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class PageInput:
    index: int
    image: Image.Image | None = None   # set when the page must be OCR'd
    text_layer: str | None = None      # set when a digital PDF already contains the text
    note: str | None = None            # something the caller should be told about this page


def load_document(data: bytes) -> list[PageInput]:
    if not data:
        raise DocumentError("empty_file", "The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise DocumentError("file_too_large", f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if data[:5] == b"%PDF-":
        return _load_pdf(data)
    return [PageInput(i, image=img) for i, img in enumerate(_load_images(data))]


def _load_images(data: bytes) -> list[Image.Image]:
    """Every frame of the file: a multi-page TIFF scan is read like a multi-page PDF."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            frames = getattr(img, "n_frames", 1)
            if frames > MAX_PAGES:
                raise DocumentError("too_many_pages", f"Image has {frames} pages; the limit is {MAX_PAGES}.")
            pages = []
            for i in range(frames):
                img.seek(i)
                if img.format == "JPEG":
                    img.draft("RGB", (MAX_LONG_SIDE, MAX_LONG_SIDE))  # decode at reduced size: faster, less memory
                img.load()
                pages.append(img.copy())
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise DocumentError("file_too_large", f"Image has too many pixels to decode safely (limit {MAX_PIXELS // 1_000_000} MP).") from exc
    except DocumentError:
        raise
    except (UnidentifiedImageError, OSError, EOFError, ValueError, SyntaxError) as exc:
        raise DocumentError("unsupported_format", "File is not a readable image or PDF.") from exc
    return [normalise_image(page) for page in pages]


def normalise_image(img: Image.Image) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(img)  # phone photos carry rotation in EXIF
    except Exception:  # corrupt EXIF: keep the pixels as stored rather than rejecting the page
        pass
    w, h = img.size
    if min(w, h) < MIN_SIDE or max(w, h) > MAX_ASPECT * min(w, h):
        raise DocumentError("unsupported_format", f"Image is {w}x{h} px, which is not the shape of a document page.")
    if img.mode in WIDE_MODES:  # rescale to 8-bit; convert("RGB") would clip every 16-bit pixel to white
        arr = np.asarray(img, dtype=np.float32)
        top = float(arr.max()) if arr.size else 0.0
        full_scale = 1.0 if top <= 1.0 else 255.0 if top <= 255 else float(2 ** int(top).bit_length() - 1)
        img = Image.fromarray(np.clip(arr * (255.0 / full_scale), 0, 255).astype(np.uint8), "L")
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA", "PA", "P"):  # flatten transparency onto white, not black
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
    long_side = max(img.size)
    if long_side > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / long_side
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img


def _load_pdf(data: bytes) -> list[PageInput]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise DocumentError("unsupported_format", "PDF could not be opened (corrupt or encrypted).") from exc
    try:
        if len(pdf) == 0:
            raise DocumentError("empty_file", "PDF has no pages.")
        if len(pdf) > MAX_PAGES:
            raise DocumentError("too_many_pages", f"PDF has {len(pdf)} pages; the limit is {MAX_PAGES}.")
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                raise DocumentError("unsupported_format", f"PDF page {i + 1} has no area.")
            text = page.get_textpage().get_text_bounded()
            scanned = _image_coverage(page, width, height, pdfium_c) >= SCANNED_IMAGE_COVERAGE
            if sum(c.isalnum() for c in text) >= MIN_TEXT_LAYER_CHARS and not scanned:
                pages.append(PageInput(i, text_layer=text.replace("\r\n", "\n").replace("\r", "\n")))
                continue
            note = None
            if scanned and sum(c.isalnum() for c in text) >= MIN_TEXT_LAYER_CHARS:
                note = (f"Page {i + 1} is a scanned image with an embedded text layer; the embedded text was not "
                        "trusted and the page was read by OCR.")
            scale = min(PDF_RENDER_DPI / 72, MAX_RENDER_SIDE / max(width, height))
            bitmap = page.render(scale=scale)
            pages.append(PageInput(i, image=normalise_image(bitmap.to_pil()), note=note))
        return pages
    except pdfium.PdfiumError as exc:
        raise DocumentError("unsupported_format", f"PDF could not be read: {exc}") from exc
    finally:
        pdf.close()


def _image_coverage(page, width: float, height: float, pdfium_c) -> float:
    covered = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        covered += max(0.0, min(right, width) - max(left, 0.0)) * max(0.0, min(top, height) - max(bottom, 0.0))
    return covered / (width * height)


def is_blank(img: Image.Image) -> bool:
    """True when the page has essentially no ink. Checked before OCR because generative OCR
    models tend to emit a few invented characters on an empty page."""
    small = ImageOps.grayscale(img).resize((600, max(1, round(600 * img.height / img.width))))
    gray = np.asarray(small, dtype=np.float32)
    if gray.std() < 4:
        return True
    # "Ink" = pixels clearly darker than their local background (tolerates shadows/gradients).
    background = np.asarray(small.filter(ImageFilter.BoxBlur(15)), dtype=np.float32)
    return ((background - gray) > 40).mean() < 0.0005

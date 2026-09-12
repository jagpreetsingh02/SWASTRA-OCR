"""Decoding and normalising uploads. No models."""

import io
import struct
import zlib

import numpy as np
import pillow_heif
import pytest
from PIL import Image

from medikiosk_ocr.preprocess import MAX_LONG_SIDE, MAX_PAGES, load_document, is_blank
from medikiosk_ocr.schema import DocumentError

from ..conftest import DEV, image_bytes

SCAN = Image.open(DEV / "prescription_scan.png").convert("RGB")


def codes(data: bytes) -> str:
    with pytest.raises(DocumentError) as exc:
        load_document(data)
    return exc.value.code


# ------------------------------------------------------------------------------ formats

@pytest.mark.parametrize("fmt,kwargs", [("PNG", {}), ("JPEG", {"quality": 90}), ("TIFF", {}), ("WEBP", {"quality": 90}), ("BMP", {})])
def test_common_image_formats_load_as_one_rgb_page(fmt, kwargs):
    pages = load_document(image_bytes(SCAN, fmt, **kwargs))
    assert len(pages) == 1 and pages[0].image.mode == "RGB" and not is_blank(pages[0].image)


def test_heic_photo_loads():
    pillow_heif.register_heif_opener()
    pages = load_document(image_bytes(SCAN, "HEIF", quality=80))
    assert len(pages) == 1 and pages[0].image.size == SCAN.size and not is_blank(pages[0].image)


def test_multipage_tiff_yields_every_page_in_order():
    other = Image.open(DEV / "lab_report_scan.png").convert("RGB")
    buf = io.BytesIO()
    SCAN.save(buf, format="TIFF", save_all=True, append_images=[other, SCAN])
    pages = load_document(buf.getvalue())
    assert [p.index for p in pages] == [0, 1, 2]
    assert all(p.image is not None for p in pages)


def test_image_with_too_many_pages_is_refused():
    buf = io.BytesIO()
    small = Image.new("L", (64, 64), 255)
    small.save(buf, format="TIFF", save_all=True, append_images=[small] * MAX_PAGES)
    assert codes(buf.getvalue()) == "too_many_pages"


def test_exif_rotation_is_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 CW to display"
    pages = load_document(image_bytes(Image.new("RGB", (400, 200), "white"), "JPEG", exif=exif))
    assert pages[0].image.size == (200, 400)


def test_sixteen_bit_greyscale_scan_is_scaled_not_clipped_to_white():
    scan16 = np.asarray(SCAN.convert("L"), dtype=np.uint16) * 257
    page = load_document(image_bytes(Image.fromarray(scan16)))[0].image
    assert page.mode == "RGB" and not is_blank(page)


def test_transparent_png_is_flattened_onto_white():
    page = load_document(image_bytes(Image.new("RGBA", (300, 300), (0, 0, 0, 0))))[0].image
    assert page.getpixel((10, 10)) == (255, 255, 255)


def test_large_photos_are_downscaled():
    page = load_document(image_bytes(SCAN.resize((4000, 5658)), "JPEG", quality=85))[0].image
    assert max(page.size) <= MAX_LONG_SIDE


# ------------------------------------------------------------------------------ PDFs

def test_digital_pdf_uses_its_text_layer_verbatim():
    pages = load_document((DEV / "prescription.pdf").read_bytes())
    assert pages[0].image is None and "TAB. AMLODIPINE 5MG OD x 30 days" in pages[0].text_layer


def test_image_only_pdf_is_rendered_for_ocr_one_page_each_in_order():
    other = Image.open(DEV / "lab_report_scan.png").convert("RGB")
    pages = load_document(image_bytes(SCAN, "PDF", save_all=True, append_images=[other]))
    assert [p.index for p in pages] == [0, 1] and all(p.text_layer is None and p.image is not None for p in pages)


def _pdf(objects: list[bytes]) -> bytes:
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def test_scanned_pdf_with_an_embedded_ocr_text_layer_is_read_by_our_ocr_not_trusted():
    jpeg = image_bytes(SCAN, "JPEG", quality=80)
    content = b"q 595 0 0 842 0 0 cm /Im0 Do Q BT 3 Tr /F1 12 Tf 72 720 Td (HbAlc 8.2 scanner text layer of unknown quality) Tj ET"
    pdf = _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 4 0 R >> "
        b"/Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 "
        b"/Filter /DCTDecode /Length %d >>\nstream\n" % (SCAN.width, SCAN.height, len(jpeg)) + jpeg + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ])
    page = load_document(pdf)[0]
    assert page.text_layer is None and page.image is not None
    assert "embedded text layer" in page.note


def test_pdf_page_with_a_huge_declared_size_is_rendered_within_limits():
    pdf = _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 14400 14400] >>",  # 200 x 200 inches: 40000 px at 200 dpi
    ])
    page = load_document(pdf)[0]
    assert page.image is not None and max(page.image.size) <= MAX_LONG_SIDE


# ------------------------------------------------------------------------------ bad input

@pytest.mark.parametrize("data,code", [
    (b"", "empty_file"),
    (b"definitely not a document", "unsupported_format"),
    (b"%PDF-1.7 truncated garbage", "unsupported_format"),
    (b"%PDF-1.7\n" + bytes(range(256)) * 20, "unsupported_format"),
    (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 200, "unsupported_format"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><text>Tab Dolo 650</text></svg>', "unsupported_format"),
])
def test_bad_input_fails_with_a_code(data, code):
    assert codes(data) == code


def test_truncated_images_fail_cleanly():
    jpg = (DEV / "prescription_photo_handheld.jpg").read_bytes()
    png = (DEV / "prescription_scan.png").read_bytes()
    assert codes(jpg[: len(jpg) // 2]) == "unsupported_format"
    assert codes(png[: len(png) // 2]) == "unsupported_format"


def test_decompression_bomb_is_refused_before_decoding():
    ihdr = struct.pack(">IIBBBBB", 30000, 30000, 8, 0, 0, 0, 0)
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + chunk(b"IEND", b"")
    assert codes(png) == "file_too_large"


@pytest.mark.parametrize("size", [(2, 30000), (3000, 20), (10, 10)])
def test_images_that_are_not_page_shaped_are_refused(size):
    assert codes(image_bytes(Image.new("L", size, 255))) == "unsupported_format"


# ------------------------------------------------------------------------------ blank detection

def test_blank_and_near_blank_pages_are_detected():
    assert is_blank(Image.new("RGB", (1240, 1754), "white"))
    gradient = np.tile(np.linspace(170, 250, 1240, dtype=np.float32), (1754, 1)).astype(np.uint8)
    assert is_blank(Image.fromarray(gradient).convert("RGB"))  # shadowed empty sheet
    assert not is_blank(SCAN)

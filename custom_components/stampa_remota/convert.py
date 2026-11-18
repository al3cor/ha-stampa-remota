"""File -> document the printer understands, without CUPS (runs in an executor thread).

- printer accepts PDF  -> the PDF is sent as is (photos/text become a PDF first)
- printer accepts URF  -> pages rendered with PDFium and encoded as Apple raster (one job, all pages)
- printer accepts JPEG -> one JPEG per page (one job per page)
Photos keep their EXIF rotation; iPhone HEIC photos are read with pillow-heif.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAPER_MM = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
PAPER_IPP = {"A4": "iso_a4_210x297mm", "A5": "iso_a5_148x210mm", "Letter": "na_letter_8.5x11in",
             "Legal": "na_legal_8.5x14in"}
MARGIN_MM = 5.0
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif")
MAX_URF_BYTES = 250 * 1024 * 1024


class ConvertError(Exception):
    """The file cannot be turned into something the printer accepts."""


@dataclass
class Options:
    paper: str = "A4"
    copies: int = 1
    pages: str = ""          # "" = all, else "1-3,5"
    fit: bool = True
    mono: bool = True


@dataclass
class Document:
    fmt: str                 # MIME type sent to the printer
    parts: list[bytes]       # one entry = one IPP job
    pages: int               # pages per copy
    copies_in_data: bool     # copies already repeated inside the data
    selected: list[int] | None = None   # PDF sent as is: 0-based pages to print (page-ranges)


def kind_of(name: str, data: bytes) -> str:
    n = name.lower()
    if data[:5] == b"%PDF-" or n.endswith(".pdf"):
        return "pdf"
    if n.endswith(IMAGE_EXT) or data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" \
            or data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image"
    if n.endswith((".txt", ".log", ".csv", ".md")):
        return "text"
    try:
        data[:4096].decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        raise ConvertError("Formato non supportato: usa PDF, foto (JPG, PNG, HEIC) o testo") from None


def parse_pages(spec: str, total: int) -> list[int]:
    """'1-3,5' -> [0, 1, 2, 4] (0-based, within total)."""
    spec = (spec or "").replace(" ", "")
    if not spec:
        return list(range(total))
    if not re.fullmatch(r"\d+(-\d*)?(,\d+(-\d*)?)*", spec):
        raise ConvertError("Pagine non valide: scrivi per esempio 1-3,5")
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        lo = int(a)
        hi = int(b) if b else (total if "-" in part else lo)
        out += [p - 1 for p in range(lo, min(hi, total) + 1) if 1 <= p <= total and p - 1 not in out]
    if not out:
        raise ConvertError(f"Nessuna pagina valida (il documento ne ha {total})")
    return out


def _px(paper: str, dpi: int) -> tuple[int, int]:
    w, h = PAPER_MM.get(paper, PAPER_MM["A4"])
    return round(w / 25.4 * dpi), round(h / 25.4 * dpi)


def _place(img: Image.Image, paper: str, dpi: int, fit: bool, mono: bool, src_dpi: float | None) -> Image.Image:
    """Put an image on a white page of the chosen paper (rotated if landscape, scaled into the margins)."""
    pw, ph = _px(paper, dpi)
    if (img.width > img.height) != (pw > ph):
        img = img.rotate(90, expand=True)
    m = round(MARGIN_MM / 25.4 * dpi)
    aw, ah = pw - 2 * m, ph - 2 * m
    if src_dpi:                                    # PDF page: real size first
        scale = dpi / src_dpi
        if fit or img.width * scale > pw or img.height * scale > ph:
            scale = min(aw / img.width, ah / img.height) if fit else min(pw / img.width, ph / img.height)
    else:                                          # photo: always fit inside the margins
        scale = min(aw / img.width, ah / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    if size != img.size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    page = Image.new("L" if mono else "RGB", (pw, ph), 255 if mono else (255, 255, 255))
    page.paste(img.convert(page.mode), ((pw - size[0]) // 2, (ph - size[1]) // 2))
    return page


def _open_image(data: bytes) -> Image.Image:
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as err:
            raise ConvertError("Foto HEIC non supportata (manca pillow-heif)") from err
    try:
        src = Image.open(io.BytesIO(data))
        src.draft("RGB", (5000, 5000))
        img = ImageOps.exif_transpose(src)
    except Exception as err:  # noqa: BLE001 - any decoding problem is a bad file for the user
        raise ConvertError(f"Immagine non leggibile ({err.__class__.__name__})") from err
    if img.mode in ("RGBA", "LA", "P", "PA"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    return img.convert("RGB")


def _text_pages(text: str, paper: str, dpi: int) -> list[Image.Image]:
    pw, ph = _px(paper, dpi)
    m = round(15 / 25.4 * dpi)
    size = round(10 / 72 * dpi)                    # 10 pt
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    line_h = round(size * 1.35)
    max_w = pw - 2 * m
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines: list[str] = []
    for raw in text.replace("\t", "    ").splitlines() or [""]:
        cur = ""
        for word in re.split(r"(\s+)", raw):
            if probe.textlength(cur + word, font=font) <= max_w:
                cur += word
            else:
                if cur:
                    lines.append(cur.rstrip())
                cur = word.lstrip()
                while probe.textlength(cur, font=font) > max_w:      # very long word
                    cut = len(cur) - 1
                    while cut > 1 and probe.textlength(cur[:cut], font=font) > max_w:
                        cut -= 1
                    lines.append(cur[:cut])
                    cur = cur[cut:]
        lines.append(cur)
    per_page = max(1, (ph - 2 * m) // line_h)
    pages = []
    for i in range(0, len(lines), per_page):
        page = Image.new("L", (pw, ph), 255)
        d = ImageDraw.Draw(page)
        for j, line in enumerate(lines[i:i + per_page]):
            d.text((m, m + j * line_h), line, fill=0, font=font)
        pages.append(page)
    return pages


# ---------------------------------------------------------------- URF (Apple raster, AirPrint)

def _urf_line(row: np.ndarray, bpp: int) -> bytes:
    """One raster line, PackBits-like: 0..127 = next pixel repeated n+1 times, 129..255 = 257-n literal
    pixels, 128 = rest of the line is white."""
    px = row if bpp == 1 else (row[:, 0].astype(np.uint32) << 16) | (row[:, 1].astype(np.uint32) << 8) | row[:, 2]
    white = 255 if bpp == 1 else 0xFFFFFF
    nz = np.flatnonzero(px != white)
    if nz.size == 0:
        return b"\x80"
    end = int(nz[-1]) + 1
    p = px[:end]
    starts = np.flatnonzero(np.r_[True, p[1:] != p[:-1]])
    tail = b"\x80" if end < row.shape[0] else b""
    raw = row[:end].reshape(end, bpp)
    if starts.size > end // 3:                     # busy line (photo): literal blocks of 128 pixels
        out = bytearray()
        flat = raw.tobytes()
        for s in range(0, end, 128):
            n = min(128, end - s)
            out.append(0 if n == 1 else 257 - n)
            out += flat[s * bpp:(s + n) * bpp]
        return bytes(out) + tail
    lens = np.diff(np.r_[starts, end])
    npk = (lens + 127) // 128
    idx = np.repeat(np.arange(starts.size), npk)
    j = np.arange(idx.size) - np.repeat(np.cumsum(npk) - npk, npk)
    cnt = np.minimum(128, lens[idx] - 128 * j)
    out = np.empty((idx.size, 1 + bpp), dtype=np.uint8)
    out[:, 0] = cnt - 1
    out[:, 1:] = raw[starts[idx]]
    return out.tobytes() + tail


def urf_page(img: Image.Image, dpi: int, quality: int = 4) -> bytes:
    a = np.asarray(img)
    bpp = 1 if img.mode == "L" else 3
    h, w = a.shape[0], a.shape[1]
    header = bytes([8 * bpp, 0 if bpp == 1 else 1, 1, quality]) + b"\x00" * 8
    header += np.array([w, h, dpi, 0, 0], dtype=">u4").tobytes()
    same = np.all((a[1:] == a[:-1]).reshape(h - 1, -1), axis=1)
    out = [header]
    y = 0
    while y < h:
        n = 1
        while y + n < h and n < 256 and same[y + n - 1]:
            n += 1
        out.append(bytes([n - 1]) + _urf_line(a[y], bpp))
        y += n
    return b"".join(out)


def urf_dpi(urf_supported: list[str]) -> int:
    res = [int(x[2:].split("-")[0]) for x in urf_supported if x.startswith("RS") and x[2:].split("-")[0].isdigit()]
    for r in sorted(res):
        if r >= 300:
            return r
    return max(res) if res else 300


# ---------------------------------------------------------------- main entry

class _TooHeavy(Exception):
    """A raster page is too big (photo): switch to JPEG."""


URF_PAGE_LIMIT = 12 * 1024 * 1024


def build(name: str, data: bytes, opt: Options, formats: list[str], urf_supported: list[str],
          _force_urf: bool = False) -> Document:
    kind = kind_of(name, data)
    copies = max(1, min(50, opt.copies))

    if kind == "pdf" and "application/pdf" in formats:
        import pypdfium2 as pdfium
        try:
            total = len(pdfium.PdfDocument(data))
        except Exception as err:  # noqa: BLE001
            raise ConvertError("PDF non leggibile o protetto da password") from err
        sel = parse_pages(opt.pages, total)
        return Document("application/pdf", [data], len(sel), False, sel if len(sel) < total else None)

    if "application/pdf" in formats:               # photo or text -> PDF, printer does the rest
        pdf = image_or_text_to_pdf(name, data, opt.paper, opt.mono)
        return build("documento.pdf", pdf, opt, formats, urf_supported)

    has_jpeg = "image/jpeg" in formats
    # photos: JPEG is ~50 times smaller than raster (one page anyway)
    use_urf = "image/urf" in formats and not (kind == "image" and has_jpeg)
    if not use_urf and not has_jpeg:
        raise ConvertError("La stampante non dichiara PDF, URF o JPEG: non è AirPrint / IPP Everywhere")
    if use_urf and has_jpeg and not _force_urf:
        try:
            return build(name, data, opt, formats, urf_supported, _force_urf=True)
        except _TooHeavy:                          # pages full of photos: JPEG, one job per page
            use_urf = False
    dpi = urf_dpi(urf_supported) if use_urf else 300
    mono = opt.mono

    def pages_iter():
        if kind == "pdf":
            import pypdfium2 as pdfium
            try:
                pdf = pdfium.PdfDocument(data)
            except Exception as err:  # noqa: BLE001
                raise ConvertError("PDF non leggibile o protetto da password") from err
            sel = parse_pages(opt.pages, len(pdf))
            yield len(sel)
            for i in sel:
                pg = pdf[i]
                w, h = pg.get_size()
                pw, ph = _px(opt.paper, dpi)
                scale = dpi / 72
                if (w > h) != (pw > ph):
                    w, h = h, w
                if opt.fit or w * scale > pw or h * scale > ph:   # render straight at the final size
                    m = round(MARGIN_MM / 25.4 * dpi)
                    scale = min((pw - 2 * m) / w, (ph - 2 * m) / h) if opt.fit else min(pw / w, ph / h)
                rot = 90 if (pg.get_size()[0] > pg.get_size()[1]) != (pw > ph) else 0
                # black and white: no anti-aliasing on text/lines -> long runs, raster 3-5 times smaller
                bmp = pg.render(scale=scale, rotation=rot, grayscale=mono, draw_annots=True,
                                no_smoothtext=mono, no_smoothpath=mono)
                img = bmp.to_pil()
                yield _place(img, opt.paper, dpi, False, mono, src_dpi=dpi)
                pg.close()
        elif kind == "image":
            yield 1
            yield _place(_open_image(data), opt.paper, dpi, True, mono, None)
        else:
            text = data.decode("utf-8", errors="replace")
            pages = _text_pages(text, opt.paper, dpi)
            sel = parse_pages(opt.pages, len(pages))
            yield len(sel)
            for i in sel:
                yield pages[i] if mono else pages[i].convert("RGB")

    it = pages_iter()
    n = next(it)
    if use_urf:
        enc, size = [], 0
        for img in it:
            enc.append(urf_page(img, dpi))
            size += len(enc[-1])
            if _force_urf and has_jpeg and len(enc[-1]) > URF_PAGE_LIMIT:
                raise _TooHeavy
            if size * copies > MAX_URF_BYTES:
                raise ConvertError("Documento troppo pesante per la stampante: prova in bianco e nero o meno pagine")
        head = b"UNIRAST\x00" + np.array([n * copies], dtype=">u4").tobytes()
        return Document("image/urf", [head + b"".join(enc) * copies], n, True)
    parts = []
    for img in it:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90, dpi=(dpi, dpi))
        parts.append(buf.getvalue())
    return Document("image/jpeg", parts, n, False)


def image_or_text_to_pdf(name: str, data: bytes, paper: str, mono: bool) -> bytes:
    """For printers that accept PDF: photos and text become a one-file PDF at 300 dpi."""
    kind = kind_of(name, data)
    if kind == "pdf":
        return data
    pages = [_place(_open_image(data), paper, 300, True, mono, None)] if kind == "image" \
        else _text_pages(data.decode("utf-8", errors="replace"), paper, 300)
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=300, save_all=True, append_images=pages[1:])
    return buf.getvalue()

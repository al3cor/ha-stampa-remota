"""File -> document the printer understands, without CUPS (runs in an executor thread).

Every file becomes a list of "source pages" (PDF pages, one photo, or text pages), each with a natural size in
points. Pages are then laid out on the sheet - automatically (fit / real size) or exactly as in the panel preview
(orientation, scale, position) - and sent in the best format the printer declares:

- PDF       -> the original PDF as is (no preview layout), otherwise the laid-out sheets as a PDF
- URF       -> Apple raster (AirPrint), all pages in one job, header like macOS
- PWG       -> PWG raster (IPP Everywhere), all pages in one job
- JPEG      -> one JPEG per sheet (photos always go this way when possible: ~50x lighter than raster)
"""
from __future__ import annotations

import io
import re
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

PAPER_MM = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
PAPER_IPP = {"A4": "iso_a4_210x297mm", "A5": "iso_a5_148x210mm", "Letter": "na_letter_8.5x11in",
             "Legal": "na_legal_8.5x14in"}
DEFAULT_MARGIN_PT = 12.0                     # ~4 mm when the printer does not say
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif")
HEIF_BRANDS = (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc", b"ftypmsf1")
MAX_RASTER_BYTES = 250 * 1024 * 1024
RASTER_PAGE_LIMIT = 12 * 1024 * 1024         # a raster sheet bigger than this is a photo: JPEG instead
MAX_RENDER_PX = 80_000_000                   # zoomed pages are cropped to what is on the sheet


class ConvertError(Exception):
    """The file cannot be turned into something the printer accepts."""


@dataclass
class Layout:
    """Preview layout: sheet orientation, scale of the page, page centre offset from the sheet centre (pt, y up)."""
    o: str = "p"
    s: float = 1.0
    dx: float = 0.0
    dy: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Layout | None:
        if not isinstance(d, dict):
            return None
        try:
            return cls("l" if d.get("o") == "l" else "p", min(max(float(d.get("s", 1)), 0.05), 5.0),
                       min(max(float(d.get("dx", 0)), -3000), 3000), min(max(float(d.get("dy", 0)), -3000), 3000))
        except (TypeError, ValueError):
            return None


@dataclass
class Printer:
    """What the conversion needs to know about the printer."""
    formats: list[str]
    urf: list[str] = field(default_factory=list)
    pwg_res: list[tuple] = field(default_factory=list)
    pwg_types: list[str] = field(default_factory=list)
    margins_pt: float = DEFAULT_MARGIN_PT


@dataclass
class Options:
    paper: str = "A4"
    copies: int = 1
    pages: str = ""          # "" = all, else "1-3,5"
    fit: bool = True
    mono: bool = True
    layout: Layout | None = None


@dataclass
class Document:
    fmt: str                 # MIME type sent to the printer
    parts: list[bytes]       # one entry = one IPP job
    pages: int               # pages per copy
    copies_in_data: bool     # copies already repeated inside the data
    selected: list[int] | None = None   # PDF sent as is: 0-based pages to print (page-ranges)
    original: bool = False              # the user's own PDF, untouched


# ---------------------------------------------------------------- helpers

def kind_of(name: str, data: bytes) -> str:
    n = name.lower()
    if data[:5] == b"%PDF-" or n.endswith(".pdf"):
        return "pdf"
    if n.endswith(IMAGE_EXT) or data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" \
            or data[4:12] in HEIF_BRANDS:
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


def paper_pt(paper: str) -> tuple[float, float]:
    w, h = PAPER_MM.get(paper, PAPER_MM["A4"])
    return w / 25.4 * 72, h / 25.4 * 72


def _open_image(data: bytes) -> Image.Image:
    if data[4:12] in HEIF_BRANDS:
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


def _text_lines(text: str, font: Any, max_w: float) -> list[str]:
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines: list[str] = []
    for raw in text.replace("\t", "    ").splitlines() or [""]:
        cur = ""
        for word in re.split(r"(\s+)", raw):
            if probe.textlength(cur + word, font=font) <= max_w:
                cur += word
                continue
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
    return lines


def _font(px: int) -> Any:
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


# ---------------------------------------------------------------- sources

class Source:
    """Pages of the uploaded file with their natural size in points and a renderer."""

    def __init__(self, name: str, data: bytes, paper: str) -> None:
        self.kind = kind_of(name, data)
        self.data = data
        self.paper = paper
        self.sizes: list[tuple[float, float]] = []
        if self.kind == "pdf":
            import pypdfium2 as pdfium
            try:
                self._pdf = pdfium.PdfDocument(data)
            except Exception as err:  # noqa: BLE001
                raise ConvertError("PDF non leggibile o protetto da password") from err
            for i in range(len(self._pdf)):
                pg = self._pdf[i]
                w, h = pg.get_size()
                if pg.get_rotation() % 180 == 90:
                    w, h = h, w
                self.sizes.append((w, h))
                pg.close()
        elif self.kind == "image":
            self._img = _open_image(data)
            w, h = self._img.size
            # natural size like Remote Print: long side 11 in, short side 7.8 in (fits A4/Letter with margins)
            dpi = max(max(w, h) / 11.0, min(w, h) / 7.8, 1e-6)
            self.sizes.append((w / dpi * 72, h / dpi * 72))
        else:
            W, H = paper_pt(paper)
            self._text = data.decode("utf-8", errors="replace")
            self._margin = 15 / 25.4 * 72
            self._font_pt = 10
            font = _font(100)                       # measure at 10 px/pt, any scale works the same
            self._lines = _text_lines(self._text, font, (W - 2 * self._margin) * 10)
            self._per_page = max(1, int((H - 2 * self._margin) // (self._font_pt * 1.35)))
            n = max(1, -(-len(self._lines) // self._per_page))
            self.sizes = [(W, H)] * n

    def __len__(self) -> int:
        return len(self.sizes)

    def render(self, i: int, k: float, gray: bool, crop: tuple[float, float, float, float] = (0, 0, 0, 0)
               ) -> Image.Image:
        """Page i at k pixels per point; crop = points cut from (left, top, right, bottom)."""
        mode = "L" if gray else "RGB"
        w, h = self.sizes[i]
        if self.kind == "pdf":
            pg = self._pdf[i]
            try:
                # PDFium crop is (left, bottom, right, top); black and white without anti-aliasing on text and lines
                bmp = pg.render(scale=k, grayscale=gray, draw_annots=True, may_draw_forms=True,
                                crop=(crop[0], crop[3], crop[2], crop[1]), no_smoothtext=gray, no_smoothpath=gray)
                return bmp.to_pil().convert(mode)
            finally:
                pg.close()
        if self.kind == "image":
            img = self._img
            sx, sy = img.width / w, img.height / h          # source pixels per point
            box = (round(crop[0] * sx), round(crop[1] * sy), round(img.width - crop[2] * sx),
                   round(img.height - crop[3] * sy))
            part = img.crop(box) if box != (0, 0, img.width, img.height) else img
            size = (max(1, round((w - crop[0] - crop[2]) * k)), max(1, round((h - crop[1] - crop[3]) * k)))
            return part.resize(size, Image.Resampling.LANCZOS).convert(mode)
        page = Image.new("L", (max(1, round(w * k)), max(1, round(h * k))), 255)
        d = ImageDraw.Draw(page)
        font = _font(max(1, round(self._font_pt * k)))
        lh = self._font_pt * 1.35 * k
        lines = self._lines[i * self._per_page:(i + 1) * self._per_page]
        for j, line in enumerate(lines):
            d.text((self._margin * k, self._margin * k + j * lh), line, fill=0, font=font)
        if any(crop):
            page = page.crop((round(crop[0] * k), round(crop[1] * k), page.width - round(crop[2] * k),
                              page.height - round(crop[3] * k)))
        return page.convert(mode)

    def thumbnail_png(self, i: int, width_px: int) -> bytes:
        w, _ = self.sizes[i]
        img = self.render(i, max(0.05, width_px / w), gray=False)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=False, compress_level=3)
        return buf.getvalue()


def auto_layout(size: tuple[float, float], paper: str, fit: bool, margin: float) -> Layout:
    """Layout used without the preview: sheet follows the page orientation; fit into the margins or real size
    (shrunk only if bigger than the sheet)."""
    w, h = size
    o = "l" if w > h else "p"
    W, H = paper_pt(paper)
    if o == "l":
        W, H = H, W
    if fit:
        s = min((W - 2 * margin) / w, (H - 2 * margin) / h)
    else:
        s = min(1.0, W / w, H / h)
    return Layout(o, s, 0.0, 0.0)


def sheet(src: Source, i: int, lay: Layout, paper: str, dpi: float, gray: bool) -> Image.Image:
    """One printed sheet (always portrait, as the paper is fed) with page i placed by the layout."""
    W, H = paper_pt(paper)
    if lay.o == "l":
        W, H = H, W
    k = dpi / 72
    canvas = Image.new("L" if gray else "RGB", (round(W * k), round(H * k)), 255 if gray else (255, 255, 255))
    w, h = src.sizes[i]
    s = lay.s
    x0 = W / 2 + lay.dx - s * w / 2              # page top-left on the sheet, points from the top-left corner
    y0 = H / 2 - lay.dy - s * h / 2
    # what part of the page lands on the sheet (points of the page)
    cl, ct = max(0.0, -x0) / s, max(0.0, -y0) / s
    cr, cb = max(0.0, x0 + s * w - W) / s, max(0.0, y0 + s * h - H) / s
    if cl + cr < w and ct + cb < h:
        crop = (cl, ct, cr, cb) if (w * h * (s * k) ** 2 > MAX_RENDER_PX) else (0.0, 0.0, 0.0, 0.0)
        img = src.render(i, s * k, gray, crop)
        canvas.paste(img, (round((x0 + crop[0] * s) * k), round((y0 + crop[1] * s) * k)))
    if lay.o == "l":
        canvas = canvas.rotate(90, expand=True)   # paper is fed portrait
    return canvas


# ---------------------------------------------------------------- raster encoders (URF and PWG share the packing)

def _pack_line(row: np.ndarray, bpp: int, white_fill: bool) -> bytes:
    """One raster line, PackBits-like: 0..127 = next pixel repeated n+1 times, 129..255 = 257-n literal pixels.
    URF also has 128 = "rest of the line is white" (white_fill); PWG must spell the white out."""
    width = row.shape[0]
    px = row if bpp == 1 else (row[:, 0].astype(np.uint32) << 16) | (row[:, 1].astype(np.uint32) << 8) | row[:, 2]
    white = 255 if bpp == 1 else 0xFFFFFF
    nz = np.flatnonzero(px != white)
    end = int(nz[-1]) + 1 if nz.size else 0
    wpix = b"\xff" * bpp
    if white_fill:
        tail = b"\x80" if end < width else b""
    else:
        rest, chunks = width - end, []
        while rest > 0:
            n = min(128, rest)
            chunks.append(bytes([n - 1]) + wpix)
            rest -= n
        tail = b"".join(chunks)
    if end == 0:
        return tail
    p = px[:end]
    starts = np.flatnonzero(np.r_[True, p[1:] != p[:-1]])
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


def _pack_page(a: np.ndarray, bpp: int, white_fill: bool) -> bytes:
    h = a.shape[0]
    same = np.all((a[1:] == a[:-1]).reshape(h - 1, -1), axis=1) if h > 1 else np.zeros(0, bool)
    out, y = [], 0
    while y < h:
        n = 1
        while y + n < h and n < 256 and same[y + n - 1]:
            n += 1
        out.append(bytes([n - 1]) + _pack_line(a[y], bpp, white_fill))
        y += n
    return b"".join(out)


def urf_page(img: Image.Image, dpi: int, quality: int = 4) -> bytes:
    a = np.asarray(img)
    bpp = 1 if img.mode == "L" else 3
    h, w = a.shape[0], a.shape[1]
    # same bytes macOS / iOS write: one-sided = 0 (CUPS writes 1 and some printers then feed blank or garbage sheets,
    # found by Gapman1980 in Remote Print 1.6.0, issue #2); the file header carries the real page count
    header = bytes([8 * bpp, 0 if bpp == 1 else 1, 0, quality]) + b"\x00" * 8
    header += np.array([w, h, dpi, 0, 0], dtype=">u4").tobytes()
    return header + _pack_page(a, bpp, True)


def urf_dpi(urf_supported: list[str]) -> int:
    res = [int(x[2:].split("-")[0]) for x in urf_supported if x.startswith("RS") and x[2:].split("-")[0].isdigit()]
    for r in sorted(res):
        if r >= 300:
            return r
    return max(res) if res else 300


def pwg_page(img: Image.Image, dpi: int, paper: str, total: int) -> bytes:
    """PWG raster page header (PWG 5102.4, 1796 bytes) + packed lines."""
    a = np.asarray(img)
    bpp = 1 if img.mode == "L" else 3
    h, w = a.shape[0], a.shape[1]
    hd = bytearray(1796)
    hd[0:9] = b"PwgRaster"
    def u32(off: int, v: int) -> None:
        hd[off:off + 4] = struct.pack(">I", v)
    u32(276, dpi)
    u32(280, dpi)
    W, H = paper_pt(paper)
    u32(352, round(W))
    u32(356, round(H))
    u32(372, w)
    u32(376, h)
    u32(384, 8)
    u32(388, 8 * bpp)
    u32(392, w * bpp)
    u32(396, 0)                                   # chunky
    u32(400, 18 if bpp == 1 else 19)              # sGray / sRGB
    u32(420, bpp)
    u32(452, total)
    u32(456, 1)
    u32(460, 1)
    u32(472, w)
    u32(476, h)
    u32(480, 0xFFFFFF)
    u32(484, 4)                                   # normal quality
    name = PAPER_IPP.get(paper, "iso_a4_210x297mm").encode()
    hd[1732:1732 + len(name)] = name
    return bytes(hd) + _pack_page(a, bpp, False)


def pwg_dpi(res: list[tuple]) -> int:
    dpis = sorted({r[0] for r in res if isinstance(r, tuple) and len(r) == 3 and r[2] == 3 and r[0] == r[1]})
    for d in dpis:
        if d >= 300:
            return d
    return dpis[-1] if dpis else 300


# ---------------------------------------------------------------- main entry

class _TooHeavy(Exception):
    """A raster sheet is too big (photo): switch to JPEG."""


def build(name: str, data: bytes, opt: Options, pr: Printer, src: Source | None = None) -> Document:
    fmts = pr.formats
    copies = max(1, min(50, opt.copies))
    src = src or Source(name, data, opt.paper)
    sel = parse_pages(opt.pages, len(src))

    if src.kind == "pdf" and "application/pdf" in fmts and opt.layout is None:
        return Document("application/pdf", [data], len(sel), False, sel if len(sel) < len(src) else None, True)

    def layout_for(i: int) -> Layout:
        return opt.layout or auto_layout(src.sizes[i], opt.paper, opt.fit, pr.margins_pt)

    gray = opt.mono

    if "application/pdf" in fmts:                     # laid-out sheets (preview, photos, text) as a PDF
        sheets = [sheet(src, i, layout_for(i), opt.paper, 300, gray) for i in sel]
        buf = io.BytesIO()
        sheets[0].save(buf, "PDF", resolution=300, save_all=True, append_images=sheets[1:])
        return Document("application/pdf", [buf.getvalue()], len(sel), False)

    has_jpeg = "image/jpeg" in fmts
    raster = "image/urf" if "image/urf" in fmts else "image/pwg-raster" if "image/pwg-raster" in fmts else None
    if raster == "image/pwg-raster" and pr.pwg_types:      # use a colour space the printer declares
        if gray and "sgray_8" not in pr.pwg_types:
            gray = False
        elif not gray and "srgb_8" not in pr.pwg_types and "sgray_8" in pr.pwg_types:
            gray = True
    if raster and not (src.kind == "image" and has_jpeg):
        try:
            return _raster(src, sel, opt, pr, raster, layout_for, gray, copies, jpeg_fallback=has_jpeg)
        except _TooHeavy:                              # pages full of photos: JPEG, one job per sheet
            pass
    if not has_jpeg:
        raise ConvertError("La stampante non dichiara PDF, URF, PWG o JPEG: non è AirPrint / IPP Everywhere")
    parts = []
    for i in sel:
        buf = io.BytesIO()
        sheet(src, i, layout_for(i), opt.paper, 300, gray).save(buf, "JPEG", quality=90, dpi=(300, 300))
        parts.append(buf.getvalue())
    return Document("image/jpeg", parts, len(sel), False)


def _raster(src: Source, sel: list[int], opt: Options, pr: Printer, fmt: str, layout_for: Any, gray: bool,
            copies: int, jpeg_fallback: bool) -> Document:
    n = len(sel)
    urf = fmt == "image/urf"
    dpi = urf_dpi(pr.urf) if urf else pwg_dpi(pr.pwg_res)
    enc, size = [], 0
    for i in sel:
        img = sheet(src, i, layout_for(i), opt.paper, dpi, gray)
        enc.append(urf_page(img, dpi) if urf else pwg_page(img, dpi, opt.paper, n * copies))
        size += len(enc[-1])
        if jpeg_fallback and len(enc[-1]) > RASTER_PAGE_LIMIT:
            raise _TooHeavy
        if size * copies > MAX_RASTER_BYTES:
            raise ConvertError("Documento troppo pesante per la stampante: prova in bianco e nero o meno pagine")
    head = b"UNIRAST\x00" + struct.pack(">I", n * copies) if urf else b"RaS2"
    return Document(fmt, [head + b"".join(enc) * copies], n, True)

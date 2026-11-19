"""Print hub: one or more printers, one shared list of prints, preview cache.

Each printer has its own queue: files are converted in an executor (PDFium is not thread-safe, so one conversion at
a time), sent one job at a time and followed until the printer says it is done. If the printer is busy or off the
job waits and is retried (like CUPS printer-error-policy=retry-job). While a job is stopped, the printer's reasons
(paper, jam, door ...) are written on the job in plain Italian and fired as an event (for notifications).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from . import convert as C
from .const import EVENT
from .ipp import STATUS_BUSY, T_INTEGER, T_KEYWORD, T_RANGE, IppClient, IppError

_LOGGER = logging.getLogger(__name__)

RETRY_BUSY = 10            # s between attempts while the printer works on another job
RETRY_OFFLINE = 60         # s between attempts while the printer is off / asleep
GIVE_UP = 6 * 3600         # after this the job is dropped
FOLLOW_MAX = 2 * 3600      # stop following a sent job after this
KEEP = 30                  # prints in the history
PREVIEW_TTL = 1800         # s an uploaded file stays ready for the preview
PREVIEW_MAX = 6

ACTIVE = ("conversione", "in_coda", "invio", "stampa")

# printer-state-reasons -> words; True = the printer cannot go on until someone fixes it
REASONS: dict[str, tuple[str, bool]] = {
    "media-empty": ("Carta finita: aggiungi fogli", True),
    "media-needed": ("Carta finita: aggiungi fogli", True),
    "media-jam": ("Foglio inceppato", True),
    "media-low": ("Carta quasi finita", False),
    "door-open": ("Sportello aperto", True),
    "cover-open": ("Coperchio aperto", True),
    "interlock-open": ("Sportello aperto", True),
    "input-tray-missing": ("Cassetto della carta mancante", True),
    "output-tray-missing": ("Vassoio d'uscita mancante", True),
    "output-area-full": ("Vassoio d'uscita pieno", True),
    "marker-supply-empty": ("Inchiostro finito", True),
    "marker-supply-missing": ("Cartuccia mancante", True),
    "marker-supply-low": ("Inchiostro in esaurimento", False),
    "marker-waste-full": ("Serbatoio dell'inchiostro di scarto pieno", True),
    "marker-waste-almost-full": ("Serbatoio dell'inchiostro di scarto quasi pieno", False),
    "toner-empty": ("Toner finito", True),
    "toner-low": ("Toner in esaurimento", False),
    "paused": ("Stampante in pausa", True),
    "offline": ("Stampante non in linea", True),
    "shutdown": ("Stampante in spegnimento", True),
    "spool-area-full": ("Memoria della stampante piena", True),
}


def reasons_info(raw: list[str]) -> list[dict[str, Any]]:
    """['media-empty-error', ...] -> [{codice, testo, grave}] (unknown and vendor reasons are left out)."""
    out, seen = [], set()
    for r in raw:
        if r in ("none", "") or r.startswith("cups-"):
            continue
        base, sev = r, ""
        for suf in ("-error", "-warning", "-report"):
            if r.endswith(suf):
                base, sev = r[: -len(suf)], suf[1:]
        if base not in REASONS or base in seen:
            continue
        seen.add(base)
        text, blocking = REASONS[base]
        out.append({"codice": base, "testo": text, "grave": blocking and sev != "warning" and sev != "report"})
    return out


@dataclass
class PrinterConn:
    entry_id: str
    name: str
    client: IppClient
    paper: str
    mono_default: bool
    attrs: dict[str, list[Any]] = field(default_factory=dict)
    attrs_time: float = 0.0
    error: str = ""
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    worker: asyncio.Task | None = None

    def conv_printer(self) -> C.Printer:
        a = self.attrs
        fmts = a.get("document-format-supported", []) or ["image/urf", "image/jpeg"]   # AirPrint baseline
        margins = []
        for k in ("media-left-margin-supported", "media-right-margin-supported", "media-top-margin-supported",
                  "media-bottom-margin-supported"):
            vals = [v for v in a.get(k, []) if isinstance(v, int) and v > 0]
            if vals:
                margins.append(min(vals))
        margin_pt = max(margins) / 2540 * 72 if margins else C.DEFAULT_MARGIN_PT   # hundredths of mm
        return C.Printer(fmts, a.get("urf-supported", ["RS300", "W8", "SRGB24"]),
                         [v for v in a.get("pwg-raster-document-resolution-supported", []) if isinstance(v, tuple)],
                         a.get("pwg-raster-document-type-supported", []), margin_pt)


class PrintHub:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.printers: dict[str, PrinterConn] = {}
        self._store: Store = Store(hass, 1, "stampa_remota.lavori")
        self.jobs: list[dict[str, Any]] = []
        self._payloads: dict[str, tuple[C.Document, C.Options]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._previews: dict[str, dict[str, Any]] = {}
        self._pdfium = threading.Lock()          # PDFium must not run in two threads at once
        self._loaded = False

    # ------------------------------------------------------------ life cycle
    async def async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.jobs = (await self._store.async_load()) or []
        for j in self.jobs:                    # jobs interrupted by a restart
            if j["stato"] in ("conversione", "in_coda", "invio"):
                j.update(stato="errore", errore="Interrotta dal riavvio di Home Assistant: rimandala")

    async def add_printer(self, entry_id: str, name: str, uri: str, paper: str, mono_default: bool) -> PrinterConn:
        conn = PrinterConn(entry_id, name, IppClient(async_get_clientsession(self.hass, verify_ssl=False), uri),
                           paper, mono_default)
        self.printers[entry_id] = conn
        conn.worker = self.hass.async_create_background_task(self._worker(conn), f"stampa_remota_{entry_id}")
        for j in self.jobs:
            if j["stato"] == "stampa" and j.get("job_id") and j.get("stampante_id") == entry_id:
                self._follow(conn, j)
        return conn

    async def remove_printer(self, entry_id: str) -> None:
        conn = self.printers.pop(entry_id, None)
        if conn and conn.worker:
            conn.worker.cancel()
        await self._save()

    async def async_stop(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await self._save()

    async def _save(self) -> None:
        self.jobs = self.jobs[-KEEP:]
        await self._store.async_save(self.jobs)

    def _spawn(self, coro: Any, name: str) -> None:
        t = self.hass.async_create_background_task(coro, name)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def printer(self, key: str | None) -> PrinterConn:
        """By entry id or name; None/'' = the first printer."""
        if not self.printers:
            raise KeyError("nessuna stampante configurata")
        if key:
            if key in self.printers:
                return self.printers[key]
            for p in self.printers.values():
                if p.name.lower() == str(key).lower():
                    return p
            raise KeyError(f"stampante '{key}' non trovata")
        return next(iter(self.printers.values()))

    # ------------------------------------------------------------ printer state
    async def refresh(self, conn: PrinterConn, max_age: float = 10) -> dict[str, list[Any]]:
        async with conn.lock:
            if time.monotonic() - conn.attrs_time > max_age:
                try:
                    conn.attrs = await conn.client.printer_attributes()
                    conn.error = ""
                except IppError as err:
                    conn.error = str(err)
                conn.attrs_time = time.monotonic()
        return conn.attrs

    async def printer_status(self, conn: PrinterConn) -> dict[str, Any]:
        a = await self.refresh(conn)
        names, levels, colors = a.get("marker-names", []), a.get("marker-levels", []), a.get("marker-colors", [])
        pr = conn.conv_printer()
        return {
            "id": conn.entry_id,
            "nome": conn.name,
            "modello": a.get("printer-make-and-model", [""])[0],
            "raggiungibile": not conn.error,
            "errore": conn.error,
            "stato": {3: "idle", 4: "processing", 5: "stopped"}.get(a.get("printer-state", [0])[0], "unknown"),
            "avvisi": reasons_info(a.get("printer-state-reasons", [])) if not conn.error else [],
            "inchiostri": [{"nome": n, "livello": levels[i] if i < len(levels) else None,
                            "colore": colors[i] if i < len(colors) else ""} for i, n in enumerate(names)],
            "colore": ("color" in a.get("print-color-mode-supported", ["color"])
                       or "SRGB24" in a.get("urf-supported", [])
                       or "srgb_8" in a.get("pwg-raster-document-type-supported", [])),
            "carta": conn.paper,
            "foglio_pt": list(C.paper_pt(conn.paper)),
            "margine_pt": round(pr.margins_pt, 2),
            "bianco_nero_predefinito": conn.mono_default,
        }

    async def status(self) -> dict[str, Any]:
        printers = await asyncio.gather(*(self.printer_status(p) for p in self.printers.values()))
        return {"stampanti": list(printers), "lavori": list(reversed(self.jobs[-15:]))}

    # ------------------------------------------------------------ preview
    def _clean_previews(self) -> None:
        now = time.time()
        for k in [k for k, v in self._previews.items() if now - v["ora"] > PREVIEW_TTL]:
            del self._previews[k]
        while len(self._previews) > PREVIEW_MAX:
            del self._previews[min(self._previews, key=lambda k: self._previews[k]["ora"])]

    def _make_source(self, name: str, data: bytes, paper: str) -> C.Source:
        with self._pdfium:
            return C.Source(name, data, paper)

    async def prepare(self, name: str, data: bytes, conn: PrinterConn) -> dict[str, Any]:
        """Keep the file for the preview; returns token, pages and page sizes (points)."""
        self._clean_previews()
        src = await self.hass.async_add_executor_job(self._make_source, name, data, conn.paper)
        token = uuid.uuid4().hex
        self._previews[token] = {"nome": name, "data": data, "src": src, "ora": time.time(), "carta": conn.paper}
        return {"token": token, "nome": name, "pagine": len(src),
                "misure": [[round(w, 2), round(h, 2)] for w, h in src.sizes[:500]]}

    def _thumb(self, src: C.Source, page: int, width: int) -> bytes:
        with self._pdfium:
            return src.thumbnail_png(page, width)

    async def thumbnail(self, token: str, page: int, width: int) -> bytes | None:
        p = self._previews.get(token)
        if not p or not 0 <= page < len(p["src"]):
            return None
        p["ora"] = time.time()
        return await self.hass.async_add_executor_job(self._thumb, p["src"], page, max(60, min(width, 1600)))

    def preview_file(self, token: str) -> tuple[str, bytes, C.Source] | None:
        p = self._previews.get(token)
        return (p["nome"], p["data"], p["src"]) if p else None

    # ------------------------------------------------------------ submit
    def _build(self, name: str, data: bytes, opt: C.Options, pr: C.Printer, src: C.Source | None) -> C.Document:
        with self._pdfium:
            if src is not None and src.paper != opt.paper:
                src = None
            return C.build(name, data, opt, pr, src)

    async def submit(self, name: str, data: bytes, opt: C.Options, user: str = "", printer: str | None = None,
                     src: C.Source | None = None) -> dict[str, Any]:
        conn = self.printer(printer)
        opt.paper = conn.paper
        job = {"id": uuid.uuid4().hex[:10], "nome": name[:120], "copie": opt.copies, "pagine": None,
               "bianco_nero": opt.mono, "utente": user, "ora": time.time(), "stato": "conversione",
               "errore": "", "avviso": "", "job_id": None, "formato": "", "stampante": conn.name,
               "stampante_id": conn.entry_id, "anteprima": opt.layout is not None}
        self.jobs.append(job)
        self._fire(job)
        if not conn.attrs:
            await self.refresh(conn, max_age=0)
        try:
            doc = await self.hass.async_add_executor_job(self._build, name, data, opt, conn.conv_printer(), src)
        except C.ConvertError as err:
            job.update(stato="errore", errore=str(err))
            self._fire(job)
            await self._save()
            return job
        except Exception as err:  # noqa: BLE001 - never leave a job stuck in "conversione"
            _LOGGER.exception("Conversione fallita per %s", name)
            job.update(stato="errore", errore=f"Conversione fallita: {err}")
            self._fire(job)
            await self._save()
            return job
        job.update(pagine=doc.pages, formato=doc.fmt, stato="in_coda")
        self._payloads[job["id"]] = (doc, opt)
        await conn.queue.put(job["id"])
        await self._save()
        self._fire(job)
        return job

    def _find(self, jid: str) -> dict[str, Any] | None:
        return next((j for j in self.jobs if j["id"] == jid), None)

    async def cancel(self, jid: str) -> bool:
        job = self._find(jid)
        if not job or job["stato"] not in ACTIVE:
            return False
        conn = self.printers.get(job.get("stampante_id", ""))
        if job.get("job_id") and conn:
            for one in job.get("job_ids") or [job["job_id"]]:
                try:
                    await conn.client.cancel(one)
                except IppError as err:
                    _LOGGER.debug("Cancel-Job %s: %s", one, err)
        self._payloads.pop(jid, None)
        job.update(stato="annullato", avviso="")
        self._fire(job)
        await self._save()
        return True

    async def forget(self, jid: str) -> bool:
        """Remove a finished print from the list."""
        job = self._find(jid)
        if not job or job["stato"] in ACTIVE:
            return False
        self.jobs.remove(job)
        await self._save()
        return True

    async def clear(self) -> int:
        """Remove every finished print; queued and printing ones stay."""
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["stato"] in ACTIVE]
        await self._save()
        return before - len(self.jobs)

    # ------------------------------------------------------------ sending
    def _attrs(self, conn: PrinterConn, doc: C.Document, opt: C.Options) -> list:
        attrs: list = [(T_KEYWORD, "media", C.PAPER_IPP.get(conn.paper, "iso_a4_210x297mm")),
                       (T_KEYWORD, "sides", "one-sided")]
        if opt.mono:
            attrs.append((T_KEYWORD, "print-color-mode", "monochrome"))
        if doc.fmt == "application/pdf" and opt.copies > 1:
            attrs.append((T_INTEGER, "copies", opt.copies))
        if doc.original:                       # the user's PDF as is: the printer picks pages and scales it
            if doc.selected:
                ranges, start, prev = [], doc.selected[0], doc.selected[0]
                for p in doc.selected[1:] + [None]:
                    if p is not None and p == prev + 1:
                        prev = p
                        continue
                    ranges.append((start + 1, prev + 1))
                    if p is not None:
                        start = prev = p
                attrs.append((T_RANGE, "page-ranges", ranges))
            attrs.append((T_KEYWORD, "print-scaling", "fit" if opt.fit else "none"))
        else:                                  # sheets already laid out at the paper size
            attrs.append((T_KEYWORD, "print-scaling", "none"))
        return attrs

    async def _send(self, conn: PrinterConn, job: dict[str, Any], name: str, fmt: str, attrs: list,
                    data: bytes) -> int | None:
        """Print-Job with retries. Returns the printer job id, None if the job was cancelled meanwhile."""
        start = time.time()
        drop_attrs = False
        while True:
            if job["stato"] == "annullato":
                return None
            try:
                use = [a for a in attrs if a[1] in ("media", "copies")] if drop_attrs else attrs
                return await conn.client.print_job(name, fmt, use, data)
            except IppError as err:
                if err.status == STATUS_BUSY:
                    wait, why = RETRY_BUSY, "Stampante occupata, riprovo"
                elif err.status is None:
                    wait, why = RETRY_OFFLINE, "Stampante spenta o non raggiungibile, riprovo da sola"
                elif not drop_attrs and err.status in (0x040B, 0x0400):   # attributes not supported: plain job
                    drop_attrs = True
                    continue
                else:
                    raise
                if time.time() - start > GIVE_UP:
                    raise IppError("la stampante non ha risposto per 6 ore") from err
                if job.get("errore") != why:
                    job["errore"] = why
                    self._fire(job)
                await asyncio.sleep(wait)

    async def _worker(self, conn: PrinterConn) -> None:
        while True:
            jid = await conn.queue.get()
            job = self._find(jid)
            item = self._payloads.pop(jid, None)
            if not job or not item or job["stato"] == "annullato":
                continue
            doc, opt = item
            job.update(stato="invio", errore="")
            self._fire(job)
            attrs = self._attrs(conn, doc, opt)
            try:
                ids: list[int] = []
                rounds = 1 if (doc.copies_in_data or doc.fmt == "application/pdf") else opt.copies
                n = len(doc.parts)
                for _ in range(rounds):
                    for k, part in enumerate(doc.parts):
                        label = job["nome"] if n == 1 else f"{job['nome']} ({k + 1}/{n})"
                        jid_p = await self._send(conn, job, label, doc.fmt, attrs, part)
                        if jid_p is None:
                            break
                        ids.append(jid_p)
                        job.update(job_id=jid_p, job_ids=ids, stato="stampa",
                                   errore="" if n * rounds == 1 else f"Inviata parte {len(ids)} di {n * rounds}")
                        self._fire(job)
                        if len(ids) < n * rounds:             # JPEG printers take one job at a time
                            await self._wait_done(conn, job, jid_p)
                if job["stato"] == "stampa":
                    job["errore"] = ""
                    self._follow(conn, job)
            except IppError as err:
                job.update(stato="errore", errore=str(err)[:1].upper() + str(err)[1:])
                self._fire(job)
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Invio fallito")
                job.update(stato="errore", errore=str(err))
                self._fire(job)
            await self._save()

    async def _blocking_reason(self, conn: PrinterConn) -> str:
        a = await self.refresh(conn, max_age=8)
        return " · ".join(r["testo"] for r in reasons_info(a.get("printer-state-reasons", [])) if r["grave"])

    async def _set_warning(self, conn: PrinterConn, job: dict[str, Any]) -> None:
        text = await self._blocking_reason(conn)
        if text != job.get("avviso", ""):
            job["avviso"] = text
            self._fire(job)

    async def _wait_done(self, conn: PrinterConn, job: dict[str, Any], job_id: int, limit: float = 1800) -> None:
        start = time.time()
        while time.time() - start < limit:
            try:
                state, _ = await conn.client.job_state(job_id)
            except IppError:
                state = "unknown"
            if state in ("completed", "canceled", "aborted", "unknown"):
                return
            await self._set_warning(conn, job)
            await asyncio.sleep(4)

    def _follow(self, conn: PrinterConn, job: dict[str, Any]) -> None:
        async def run() -> None:
            start = time.time()
            while job["stato"] == "stampa" and time.time() - start < FOLLOW_MAX:
                await asyncio.sleep(4)
                try:
                    state, reasons = await conn.client.job_state(job["job_id"])
                except IppError as err:
                    if err.status is not None:     # job unknown to the printer: it is gone, so it printed
                        state, reasons = "completed", []
                    else:
                        continue
                if state == "completed":
                    job.update(stato="fatto", errore="", avviso="")
                elif state in ("canceled", "aborted"):
                    why = " · ".join(r["testo"] for r in reasons_info(reasons))
                    job.update(stato="annullato" if state == "canceled" else "errore", avviso="",
                               errore="" if state == "canceled" else
                               "La stampante ha interrotto la stampa" + (f": {why}" if why else ""))
                else:                               # pending / processing / stopped: tell why it waits
                    await self._set_warning(conn, job)
                    continue
                self._fire(job)
                await self._save()
                return
            if job["stato"] == "stampa":
                job.update(stato="fatto", errore="", avviso="")
                self._fire(job)
                await self._save()
        self._spawn(run(), f"stampa_remota_{job['id']}")

    def _fire(self, job: dict[str, Any]) -> None:
        self.hass.bus.async_fire(EVENT, {k: job.get(k) for k in
                                         ("id", "nome", "stato", "errore", "avviso", "pagine", "copie", "utente",
                                          "stampante")})

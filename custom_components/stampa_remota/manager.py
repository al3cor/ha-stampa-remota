"""Print queue: convert in an executor, send to the printer one job at a time, follow the job state.

Jobs survive in memory only until they are sent; the list of recent prints is kept in .storage.
If the printer is busy or off, the job waits and is retried (like CUPS printer-error-policy=retry-job).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
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

ACTIVE = ("conversione", "in_coda", "invio", "stampa")


class PrintManager:
    def __init__(self, hass: HomeAssistant, uri: str, paper: str, mono_default: bool) -> None:
        self.hass = hass
        self.paper = paper
        self.mono_default = mono_default
        self.client = IppClient(async_get_clientsession(hass, verify_ssl=False), uri)
        self._store: Store = Store(hass, 1, "stampa_remota.lavori")
        self.jobs: list[dict[str, Any]] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._payloads: dict[str, tuple[C.Document, C.Options]] = {}
        self._tasks: list[asyncio.Task] = []
        self._printer: dict[str, list[Any]] = {}
        self._printer_time = 0.0
        self._printer_error = ""
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ life cycle
    async def async_start(self) -> None:
        self.jobs = (await self._store.async_load()) or []
        for j in self.jobs:                    # jobs interrupted by a restart
            if j["stato"] in ("conversione", "in_coda", "invio"):
                j.update(stato="errore", errore="Interrotto dal riavvio di Home Assistant: rimandalo")
        self._tasks.append(self.hass.async_create_background_task(self._worker(), "stampa_remota_worker"))
        for j in self.jobs:
            if j["stato"] == "stampa" and j.get("job_id"):
                self._follow(j)

    async def async_stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await self._save()

    async def _save(self) -> None:
        self.jobs = self.jobs[-KEEP:]
        await self._store.async_save(self.jobs)

    # ------------------------------------------------------------ printer
    async def printer(self, max_age: float = 10) -> dict[str, list[Any]]:
        async with self._lock:
            if time.monotonic() - self._printer_time > max_age:
                try:
                    self._printer = await self.client.printer_attributes()
                    self._printer_error = ""
                except IppError as err:
                    self._printer_error = str(err)
                self._printer_time = time.monotonic()
        return self._printer

    async def status(self) -> dict[str, Any]:
        p = await self.printer()
        reasons = [r for r in p.get("printer-state-reasons", []) if r != "none"]
        names, levels = p.get("marker-names", []), p.get("marker-levels", [])
        colors = p.get("marker-colors", [])
        return {
            "stampante": p.get("printer-make-and-model", [""])[0],
            "raggiungibile": not self._printer_error,
            "errore": self._printer_error,
            "stato": {3: "idle", 4: "processing", 5: "stopped"}.get(p.get("printer-state", [0])[0], "unknown"),
            "avvisi": reasons,
            "inchiostri": [{"nome": n, "livello": levels[i] if i < len(levels) else None,
                            "colore": colors[i] if i < len(colors) else ""} for i, n in enumerate(names)],
            "fronte_retro": any(s.startswith("two-sided") for s in p.get("sides-supported", [])),
            "colore": "color" in p.get("print-color-mode-supported", ["color"]) or "SRGB24" in p.get("urf-supported", []),
            "carta": self.paper,
            "bianco_nero_predefinito": self.mono_default,
            "lavori": list(reversed(self.jobs[-15:])),
        }

    # ------------------------------------------------------------ submit
    async def submit(self, name: str, data: bytes, opt: C.Options, user: str = "") -> dict[str, Any]:
        job = {"id": uuid.uuid4().hex[:10], "nome": name[:120], "copie": opt.copies, "pagine": None,
               "bianco_nero": opt.mono, "utente": user, "ora": time.time(), "stato": "conversione",
               "errore": "", "job_id": None, "formato": ""}
        self.jobs.append(job)
        self._fire(job)
        p = await self.printer(max_age=600)
        if not p:
            p = await self.printer(max_age=0)
        formats = p.get("document-format-supported", [])
        if not formats:                        # printer never seen since start: be optimistic, AirPrint baseline
            formats, urf = ["image/urf", "image/jpeg"], ["RS300", "W8", "SRGB24"]
        else:
            urf = p.get("urf-supported", [])
        try:
            doc = await self.hass.async_add_executor_job(C.build, name, data, opt, formats, urf)
        except C.ConvertError as err:
            job.update(stato="errore", errore=str(err))
            self._fire(job)
            await self._save()
            return job
        except Exception as err:  # noqa: BLE001 - never leave a job stuck in "conversione"
            _LOGGER.exception("Conversione fallita per %s", name)
            job.update(stato="errore", errore=f"Conversione fallita: {err}")
            await self._save()
            return job
        job.update(pagine=doc.pages, formato=doc.fmt, stato="in_coda")
        self._payloads[job["id"]] = (doc, opt)
        await self._queue.put(job["id"])
        await self._save()
        self._fire(job)
        return job

    def _find(self, jid: str) -> dict[str, Any] | None:
        return next((j for j in self.jobs if j["id"] == jid), None)

    async def cancel(self, jid: str) -> bool:
        job = self._find(jid)
        if not job or job["stato"] not in ACTIVE:
            return False
        if job.get("job_id"):
            for one in job.get("job_ids") or [job["job_id"]]:
                try:
                    await self.client.cancel(one)
                except IppError as err:
                    _LOGGER.debug("Cancel-Job %s: %s", one, err)
        self._payloads.pop(jid, None)
        job.update(stato="annullato")
        self._fire(job)
        await self._save()
        return True

    # ------------------------------------------------------------ sending
    def _attrs(self, doc: C.Document, opt: C.Options) -> list:
        attrs: list = [(T_KEYWORD, "media", C.PAPER_IPP.get(self.paper, "iso_a4_210x297mm")),
                       (T_KEYWORD, "sides", "one-sided")]
        if opt.mono:
            attrs.append((T_KEYWORD, "print-color-mode", "monochrome"))
        if doc.fmt == "application/pdf":
            if opt.copies > 1:
                attrs.append((T_INTEGER, "copies", opt.copies))
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
        else:
            attrs.append((T_KEYWORD, "print-scaling", "none"))   # pages are already at the paper size
        return attrs

    async def _send(self, job: dict[str, Any], name: str, fmt: str, attrs: list, data: bytes) -> int | None:
        """Print-Job with retries. Returns the printer job id, None if the job was cancelled meanwhile."""
        start = time.time()
        drop_attrs = False
        while True:
            if job["stato"] == "annullato":
                return None
            try:
                use = [a for a in attrs if a[1] == "media"] if drop_attrs else attrs
                return await self.client.print_job(name, fmt, use, data)
            except IppError as err:
                if err.status == STATUS_BUSY:
                    wait, why = RETRY_BUSY, "stampante occupata, riprovo"
                elif err.status is None:
                    wait, why = RETRY_OFFLINE, "stampante spenta o non raggiungibile, riprovo"
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

    async def _worker(self) -> None:
        while True:
            jid = await self._queue.get()
            job = self._find(jid)
            item = self._payloads.pop(jid, None)
            if not job or not item or job["stato"] == "annullato":
                continue
            doc, opt = item
            job.update(stato="invio", errore="")
            self._fire(job)
            attrs = self._attrs(doc, opt)
            try:
                ids: list[int] = []
                rounds = 1 if (doc.copies_in_data or doc.fmt == "application/pdf") else opt.copies
                n = len(doc.parts)
                for _ in range(rounds):
                    for k, part in enumerate(doc.parts):
                        label = job["nome"] if n == 1 else f"{job['nome']} ({k + 1}/{n})"
                        jid_p = await self._send(job, label, doc.fmt, attrs, part)
                        if jid_p is None:
                            break
                        ids.append(jid_p)
                        job.update(job_id=jid_p, job_ids=ids, stato="stampa",
                                   errore="" if n * rounds == 1 else f"inviata parte {len(ids)} di {n * rounds}")
                        self._fire(job)
                        if len(ids) < n * rounds:             # JPEG printers take one job at a time
                            await self._wait_done(jid_p)
                if job["stato"] == "stampa":
                    job["errore"] = ""
                    self._follow(job)
            except IppError as err:
                job.update(stato="errore", errore=str(err))
                self._fire(job)
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Invio fallito")
                job.update(stato="errore", errore=str(err))
            await self._save()

    async def _wait_done(self, job_id: int, limit: float = 900) -> None:
        start = time.time()
        while time.time() - start < limit:
            try:
                state, _ = await self.client.job_state(job_id)
            except IppError:
                state = "unknown"
            if state in ("completed", "canceled", "aborted", "unknown"):
                return
            await asyncio.sleep(3)

    def _follow(self, job: dict[str, Any]) -> None:
        async def run() -> None:
            start = time.time()
            while job["stato"] == "stampa" and time.time() - start < FOLLOW_MAX:
                await asyncio.sleep(4)
                try:
                    state, reasons = await self.client.job_state(job["job_id"])
                except IppError as err:
                    if err.status is not None:     # job unknown to the printer: it is gone, so it printed
                        state, reasons = "completed", []
                    else:
                        continue
                if state == "completed":
                    job.update(stato="fatto", errore="")
                elif state in ("canceled", "aborted"):
                    job.update(stato="annullato" if state == "canceled" else "errore",
                               errore="" if state == "canceled" else "la stampante ha interrotto la stampa "
                               + " ".join(r for r in reasons if r != "none"))
                elif state == "stopped":
                    job["errore"] = "ferma: " + " ".join(r for r in reasons if r != "none")
                    self._fire(job)
                    continue
                else:
                    continue
                self._fire(job)
                await self._save()
                return
            if job["stato"] == "stampa":
                job.update(stato="fatto", errore="")
                await self._save()
        self._tasks.append(self.hass.async_create_background_task(run(), f"stampa_remota_{job['id']}"))
        self._tasks = [t for t in self._tasks if not t.done()]

    def _fire(self, job: dict[str, Any]) -> None:
        self.hass.bus.async_fire(EVENT, {k: job.get(k) for k in
                                         ("id", "nome", "stato", "errore", "pagine", "copie", "utente")})

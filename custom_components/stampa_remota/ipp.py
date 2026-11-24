"""Minimal IPP/1.1 client (RFC 8010/8011) on aiohttp: only what a driverless print needs.

Operations: Get-Printer-Attributes, Print-Job, Validate-Job, Get-Job-Attributes, Get-Jobs, Cancel-Job.
No CUPS: the document is sent straight to the printer in a format it declares (PDF, URF or JPEG).
"""
from __future__ import annotations

import socket
import ssl
import struct
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# operations
OP_PRINT_JOB = 0x0002
OP_VALIDATE_JOB = 0x0004
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRIBUTES = 0x0009
OP_GET_JOBS = 0x000A
OP_GET_PRINTER_ATTRIBUTES = 0x000B

# delimiter tags
TAG_OPERATION = 0x01
TAG_JOB = 0x02
TAG_END = 0x03
TAG_PRINTER = 0x04

# value tags
T_INTEGER = 0x21
T_BOOLEAN = 0x22
T_ENUM = 0x23
T_RANGE = 0x33
T_TEXT = 0x41
T_NAME = 0x42
T_KEYWORD = 0x44
T_URI = 0x45
T_CHARSET = 0x47
T_LANGUAGE = 0x48
T_MIME = 0x49

STATUS_BUSY = 0x0507  # server-error-busy: the printer is still working on the previous job

JOB_STATES = {3: "pending", 4: "held", 5: "processing", 6: "stopped", 7: "canceled", 8: "aborted", 9: "completed"}

PRINTER_ATTRS = [
    "printer-make-and-model", "printer-state", "printer-state-reasons", "document-format-supported",
    "urf-supported", "sides-supported", "media-supported", "print-color-mode-supported",
    "marker-names", "marker-levels", "marker-colors", "marker-types", "copies-supported",
    "pwg-raster-document-resolution-supported", "pwg-raster-document-type-supported",
    "media-left-margin-supported", "media-right-margin-supported", "media-top-margin-supported",
    "media-bottom-margin-supported",
]

T_RESOLUTION = 0x32

# IPP status -> plain words (Italian), for the setup form and the panel
STATUS_HINTS = {
    0x0400: "la stampante non capisce la richiesta: prova un altro percorso (/ipp/print, /ipp, /ipp/printer)",
    0x0401: "la stampante rifiuta di descriversi: nella sua pagina web consenti le operazioni IPP",
    0x0402: "l'IPP chiede utente e password: disattiva l'autenticazione IPP nella pagina web della stampante",
    0x0403: "accesso IPP limitato: nella pagina web della stampante consenti l'IPP dall'indirizzo di Home Assistant",
    0x0406: "percorso sbagliato: prova /ipp/print, /ipp oppure /ipp/printer",
    0x0501: "IPP spento o limitato sulla stampante: attivalo nella sua pagina web",
    0x0503: "la stampante parla solo una versione vecchia di IPP",
}


class IppError(Exception):
    """The printer answered with an error status or could not be reached.

    sent = the connection was made, so the printer may have received the request even if no answer came back.
    """

    def __init__(self, message: str, status: int | None = None, sent: bool = True) -> None:
        super().__init__(message)
        self.status = status
        self.sent = sent


@dataclass
class IppResponse:
    status: int
    groups: list[tuple[int, dict[str, list[Any]]]] = field(default_factory=list)

    def group(self, tag: int) -> dict[str, list[Any]]:
        for t, attrs in self.groups:
            if t == tag:
                return attrs
        return {}


def _attr(tag: int, name: str, value: Any) -> bytes:
    if tag in (T_INTEGER, T_ENUM):
        raw = struct.pack(">i", int(value))
    elif tag == T_BOOLEAN:
        raw = b"\x01" if value else b"\x00"
    elif tag == T_RANGE:
        raw = struct.pack(">ii", *value)
    else:
        raw = str(value).encode()
    nm = name.encode()
    return bytes([tag]) + struct.pack(">H", len(nm)) + nm + struct.pack(">H", len(raw)) + raw


def _attrs(tag: int, name: str, values: list[Any]) -> bytes:
    out = _attr(tag, name, values[0])
    for v in values[1:]:          # additional values: empty name
        out += _attr(tag, "", v)
    return out


def encode_request(op: int, request_id: int, operation: list[tuple[int, str, Any]],
                   job: list[tuple[int, str, Any]] | None = None) -> bytes:
    out = struct.pack(">HHI", 0x0101, op, request_id) + bytes([TAG_OPERATION])
    out += _attr(T_CHARSET, "attributes-charset", "utf-8")
    out += _attr(T_LANGUAGE, "attributes-natural-language", "en")
    for tag, name, value in operation:
        out += _attrs(tag, name, value if isinstance(value, list) else [value])
    if job:
        out += bytes([TAG_JOB])
        for tag, name, value in job:
            out += _attrs(tag, name, value if isinstance(value, list) else [value])
    return out + bytes([TAG_END])


def decode_response(data: bytes) -> IppResponse:
    if len(data) < 8:
        raise IppError("risposta IPP troppo corta")
    _version, status, _rid = struct.unpack(">HHI", data[:8])
    resp = IppResponse(status)
    i, name, current, depth = 8, "", None, 0
    while i < len(data):
        tag = data[i]
        i += 1
        if tag < 0x10:                         # delimiter
            if tag == TAG_END:
                break
            current = {}
            resp.groups.append((tag, current))
            name = ""
            continue
        nl = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        nm = data[i:i + nl].decode(errors="replace")
        i += nl
        vl = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        raw = data[i:i + vl]
        i += vl
        # collections (begCollection/memberAttrName/endCollection) are skipped: not needed here
        if tag == 0x34:
            depth += 1
            if nm:
                name = nm
            continue
        if tag == 0x37:
            depth -= 1
            continue
        if depth > 0 or current is None:
            continue
        if nm:
            name = nm
        if tag in (T_INTEGER, T_ENUM) and vl == 4:
            value: Any = struct.unpack(">i", raw)[0]
        elif tag == T_BOOLEAN:
            value = raw == b"\x01"
        elif tag == T_RANGE and vl == 8:
            value = struct.unpack(">ii", raw)
        elif tag == T_RESOLUTION and vl == 9:
            value = struct.unpack(">iib", raw)   # x, y, units (3 = dpi)
        else:
            value = raw.decode(errors="replace")
        current.setdefault(name, []).append(value)
    return resp


def explain_connection_error(err: BaseException, uri: str) -> str:
    """Why the printer cannot be reached, in plain words (like Remote Print's ippcheck, without printing)."""
    secure = uri.lower().startswith("ipps://")
    if isinstance(err, aiohttp.ClientSSLError) or isinstance(getattr(err, "os_error", None), ssl.SSLError):
        return ("la connessione cifrata (ipps) non riesce: controlla SSL/TLS nella pagina web della stampante "
                "oppure usa ipp:// al posto di ipps://")
    if isinstance(err, aiohttp.ServerDisconnectedError):
        return ("la stampante ha chiuso la connessione" + (": con ipps:// di solito sono le impostazioni SSL/TLS, "
                "prova ipp://" if secure else ""))
    if isinstance(err, aiohttp.ClientConnectorError):
        os_err = getattr(err, "os_error", None)
        if isinstance(os_err, ConnectionRefusedError):
            return "nessuno risponde su quella porta: IPP spento sulla stampante o porta sbagliata (IPP usa 631)"
        if isinstance(os_err, socket.gaierror):
            return "nome della stampante sconosciuto: usa il suo indirizzo IP"
        return "stampante non raggiungibile: è accesa? L'indirizzo IP è giusto?"
    if isinstance(err, TimeoutError):
        return "nessuna risposta: stampante spenta, in risparmio energetico o indirizzo IP sbagliato"
    return f"stampante non raggiungibile ({err.__class__.__name__})"


def check_uri(uri: str) -> str | None:
    """Mistakes that need no network to spot."""
    scheme = uri.split("://", 1)[0].lower() if "://" in uri else ""
    if scheme not in ("ipp", "ipps"):
        return f"'{uri}' non è un indirizzo IPP: scrivi ipp://IP-STAMPANTE/ipp/print (oppure ipps://)"
    hostport = uri.split("://", 1)[1].split("/", 1)[0]
    if hostport.rsplit(":", 1)[-1] in ("9100", "515"):
        return f"la porta {hostport.rsplit(':', 1)[-1]} è stampa diretta/LPD, non IPP: toglila (IPP usa 631)"
    if not hostport.split(":")[0]:
        return "manca l'indirizzo della stampante"
    return None


class IppClient:
    def __init__(self, session: aiohttp.ClientSession, uri: str, user: str = "Home Assistant") -> None:
        self._session = session
        self.uri = uri.strip()
        self.user = user
        self._rid = 0
        scheme, rest = self.uri.split("://", 1)
        hostport, _, path = rest.partition("/")
        if ":" not in hostport.rsplit("]", 1)[-1]:
            hostport += ":631" if scheme == "ipp" else ":443"
        self._url = ("https" if scheme == "ipps" else "http") + f"://{hostport}/{path}"

    async def _call(self, op: int, operation: list, job: list | None = None, document: bytes = b"",
                    timeout: float = 30) -> IppResponse:
        self._rid += 1
        body = encode_request(op, self._rid, [(T_URI, "printer-uri", self.uri)] + operation, job) + document
        try:
            async with self._session.post(
                self._url, data=body, headers={"Content-Type": "application/ipp"},
                timeout=aiohttp.ClientTimeout(total=timeout, connect=15), ssl=False,
            ) as r:
                if r.status == 401:
                    raise IppError("la stampante chiede utente e password per l'IPP: disattiva l'autenticazione IPP "
                                   "nella sua pagina web")
                if r.status != 200:
                    raise IppError(f"HTTP {r.status}: percorso sbagliato? Prova /ipp/print, /ipp oppure /ipp/printer")
                data = await r.read()
                if len(data) < 8:
                    raise IppError("risposta vuota: percorso sbagliato? Prova /ipp/print, /ipp oppure /ipp/printer")
                resp = decode_response(data)
        except IppError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            # no connection at all: nothing was sent. Any other failure: the printer may have the document
            not_sent = isinstance(err, (aiohttp.ClientConnectorError, aiohttp.ConnectionTimeoutError))
            raise IppError(explain_connection_error(err, self.uri), sent=not not_sent) from err
        if resp.status >= 0x0400:
            msg = resp.group(TAG_OPERATION).get("status-message", [""])[0]
            hint = STATUS_HINTS.get(resp.status, msg or "la stampante ha rifiutato la richiesta")
            raise IppError(f"{hint} (IPP 0x{resp.status:04x})", resp.status)
        return resp

    async def printer_attributes(self) -> dict[str, list[Any]]:
        r = await self._call(OP_GET_PRINTER_ATTRIBUTES, [(T_KEYWORD, "requested-attributes", PRINTER_ATTRS)], timeout=15)
        return r.group(TAG_PRINTER)

    def _job_ops(self, name: str, fmt: str) -> list:
        return [(T_NAME, "requesting-user-name", self.user), (T_NAME, "job-name", name[:100]),
                (T_MIME, "document-format", fmt)]

    async def validate(self, name: str, fmt: str, job_attrs: list) -> None:
        await self._call(OP_VALIDATE_JOB, self._job_ops(name, fmt), job_attrs, timeout=15)

    async def print_job(self, name: str, fmt: str, job_attrs: list, document: bytes) -> int:
        # generous timeout: the whole document travels in this request (Wi-Fi printers are slow)
        r = await self._call(OP_PRINT_JOB, self._job_ops(name, fmt), job_attrs, document,
                             timeout=120 + len(document) / 200_000)
        return int(r.group(TAG_JOB).get("job-id", [0])[0])

    async def job_state(self, job_id: int) -> tuple[str, list[str]]:
        r = await self._call(OP_GET_JOB_ATTRIBUTES, [
            (T_INTEGER, "job-id", job_id), (T_NAME, "requesting-user-name", self.user),
            (T_KEYWORD, "requested-attributes", ["job-state", "job-state-reasons"])], timeout=15)
        g = r.group(TAG_JOB)
        return JOB_STATES.get(g.get("job-state", [0])[0], "unknown"), g.get("job-state-reasons", [])

    async def jobs(self, which: str) -> list[tuple[int, str]]:
        """(job-id, job-name) of the jobs the printer knows; which = completed / not-completed."""
        r = await self._call(OP_GET_JOBS, [
            (T_NAME, "requesting-user-name", self.user), (T_KEYWORD, "which-jobs", which),
            (T_KEYWORD, "requested-attributes", ["job-id", "job-name"])], timeout=15)
        return [(int(g["job-id"][0]), str(g.get("job-name", [""])[0])) for t, g in r.groups
                if t == TAG_JOB and g.get("job-id")]

    async def cancel(self, job_id: int) -> None:
        await self._call(OP_CANCEL_JOB, [(T_INTEGER, "job-id", job_id),
                                         (T_NAME, "requesting-user-name", self.user)], timeout=15)

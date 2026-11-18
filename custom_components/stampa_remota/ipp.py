"""Minimal IPP/1.1 client (RFC 8010/8011) on aiohttp: only what a driverless print needs.

Operations: Get-Printer-Attributes, Print-Job, Validate-Job, Get-Job-Attributes, Cancel-Job.
No CUPS: the document is sent straight to the printer in a format it declares (PDF, URF or JPEG).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# operations
OP_PRINT_JOB = 0x0002
OP_VALIDATE_JOB = 0x0004
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRIBUTES = 0x0009
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
]


class IppError(Exception):
    """The printer answered with an error status or could not be reached."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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
        else:
            value = raw.decode(errors="replace")
        current.setdefault(name, []).append(value)
    return resp


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
                timeout=aiohttp.ClientTimeout(total=timeout), ssl=False,
            ) as r:
                if r.status != 200:
                    raise IppError(f"HTTP {r.status} dalla stampante")
                resp = decode_response(await r.read())
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise IppError(f"stampante non raggiungibile ({err.__class__.__name__})") from err
        if resp.status >= 0x0400:
            msg = resp.group(TAG_OPERATION).get("status-message", [""])[0]
            raise IppError(f"errore IPP 0x{resp.status:04x} {msg}".strip(), resp.status)
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

    async def cancel(self, job_id: int) -> None:
        await self._call(OP_CANCEL_JOB, [(T_INTEGER, "job-id", job_id),
                                         (T_NAME, "requesting-user-name", self.user)], timeout=15)

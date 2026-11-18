"""Stampa remota: print a file from the phone on the home printer, through Home Assistant.

Integration (HACS) version of the "Remote Print" app by Gapman1980 (MIT), without CUPS and without the
Supervisor: works on Home Assistant Container/Core too. A sidebar panel (also for non-admin users if wanted)
uploads the file to an authenticated API; the file is converted in Python (PDFium, Pillow) and sent over IPP.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import aiohttp
import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import convert as C
from .const import (CONF_ADMIN_ONLY, CONF_MONO, CONF_PAPER, CONF_URI, DOMAIN, MAX_UPLOAD, PANEL_URL,
                    STATIC_URL, VERSION)
from .manager import PrintManager

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema({
    vol.Exclusive("file", "sorgente"): cv.string,
    vol.Exclusive("url", "sorgente"): cv.url,
    vol.Exclusive("testo", "sorgente"): cv.string,
    vol.Optional("nome"): cv.string,
    vol.Optional("copie", default=1): vol.All(vol.Coerce(int), vol.Range(1, 50)),
    vol.Optional("pagine", default=""): cv.string,
    vol.Optional("adatta", default=True): cv.boolean,
    vol.Optional("bianco_nero"): cv.boolean,
})


def _opts(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    o = _opts(entry)
    mgr = PrintManager(hass, o[CONF_URI], o.get(CONF_PAPER, "A4"), o.get(CONF_MONO, False))
    await mgr.async_start()
    entry.runtime_data = mgr
    hass.data[DOMAIN] = mgr

    if not hass.data.get(f"{DOMAIN}_http"):          # static files and views cannot be removed: once only
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)])
        hass.http.register_view(PrintView)
        hass.http.register_view(StatusView)
        hass.http.register_view(CancelView)
        hass.data[f"{DOMAIN}_http"] = True

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="stampa-remota-panel",
        sidebar_title="Stampa",
        sidebar_icon="mdi:printer-wireless",
        module_url=f"{STATIC_URL}/stampa-remota-panel.js?v={VERSION}",
        require_admin=o.get(CONF_ADMIN_ONLY, False),
        config={},
    )

    async def print_service(call: ServiceCall) -> ServiceResponse:
        d = call.data
        if "file" in d:
            path = d["file"]
            if not hass.config.is_allowed_path(path):
                raise HomeAssistantError(f"Percorso non permesso: {path} (aggiungilo a allowlist_external_dirs)")
            if not await hass.async_add_executor_job(os.path.isfile, path):
                raise HomeAssistantError(f"File non trovato: {path}")
            data = await hass.async_add_executor_job(Path(path).read_bytes)
            name = d.get("nome") or os.path.basename(path)
        elif "url" in d:
            try:
                async with async_get_clientsession(hass).get(d["url"], timeout=aiohttp.ClientTimeout(total=60)) as r:
                    r.raise_for_status()
                    data = await r.content.read(MAX_UPLOAD + 1)
                    cd = r.headers.get("Content-Disposition", "")
            except aiohttp.ClientError as err:
                raise HomeAssistantError(f"Download fallito: {err}") from err
            if len(data) > MAX_UPLOAD:
                raise HomeAssistantError("File troppo grande (massimo 60 MB)")
            m = re.search(r'filename="?([^";]+)', cd)
            name = d.get("nome") or (m.group(1) if m else d["url"].split("?")[0].rsplit("/", 1)[-1] or "file")
        elif "testo" in d:
            data = d["testo"].encode()
            name = d.get("nome") or "testo.txt"
            if not name.lower().endswith(".txt"):
                name += ".txt"
        else:
            raise HomeAssistantError("Indica file, url o testo")
        job = await mgr.submit(name, data, C.Options(
            paper=mgr.paper, copies=d["copie"], pages=d["pagine"], fit=d["adatta"],
            mono=d.get("bianco_nero", mgr.mono_default)), user="automazione")
        if job["stato"] == "errore":
            raise HomeAssistantError(job["errore"])
        return {"id": job["id"], "stato": job["stato"], "pagine": job["pagine"]}

    hass.services.async_register(DOMAIN, "stampa", print_service, SERVICE_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    frontend.async_remove_panel(hass, PANEL_URL)
    hass.services.async_remove(DOMAIN, "stampa")
    hass.data.pop(DOMAIN, None)
    return True


def _mgr(request: web.Request) -> PrintManager:
    mgr = request.app["hass"].data.get(DOMAIN)
    if mgr is None:
        raise web.HTTPServiceUnavailable(text="Stampa remota non configurata")
    return mgr


class PrintView(HomeAssistantView):
    """Multipart upload: file + copie, pagine, adatta, bianco_nero. Read as a stream (no 16 MB limit)."""
    url = "/api/stampa_remota/stampa"
    name = "api:stampa_remota:stampa"

    async def post(self, request: web.Request) -> web.Response:
        mgr = _mgr(request)
        reader = await request.multipart()
        fields: dict[str, str] = {}
        name, buf = None, bytearray()
        async for part in reader:
            if part.name == "file" and part.filename:
                name = os.path.basename(part.filename) or "file"
                ctype = (part.headers.get("Content-Type") or "").split(";")[0].lower()
                if "." not in name:            # Android pickers: name without extension
                    name += {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
                             "image/heic": ".heic", "image/heif": ".heif", "text/plain": ".txt"}.get(ctype, "")
                while chunk := await part.read_chunk(1 << 16):
                    buf += chunk
                    if len(buf) > MAX_UPLOAD:
                        return self.json({"ok": False, "errore": "File troppo grande (massimo 60 MB)"})
            elif part.name:
                fields[part.name] = (await part.text()).strip()
        if not name:
            return self.json({"ok": False, "errore": "Nessun file ricevuto"})
        try:
            copies = max(1, min(50, int(fields.get("copie") or 1)))
        except ValueError:
            copies = 1
        user = request.get("hass_user")
        job = await mgr.submit(name, bytes(buf), C.Options(
            paper=mgr.paper, copies=copies, pages=fields.get("pagine", ""),
            fit=fields.get("adatta", "1") == "1", mono=fields.get("bianco_nero", "0") == "1"),
            user=user.name if user else "")
        return self.json({"ok": job["stato"] != "errore", "errore": job["errore"], "id": job["id"]})


class StatusView(HomeAssistantView):
    url = "/api/stampa_remota/stato"
    name = "api:stampa_remota:stato"

    async def get(self, request: web.Request) -> web.Response:
        return self.json(await _mgr(request).status())


class CancelView(HomeAssistantView):
    url = "/api/stampa_remota/annulla"
    name = "api:stampa_remota:annulla"

    async def post(self, request: web.Request) -> web.Response:
        data = await request.json()
        return self.json({"ok": await _mgr(request).cancel(str(data.get("id", "")))})

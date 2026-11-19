"""Stampa remota: print a file from the phone on the home printer, through Home Assistant.

Integration (HACS) version of the "Remote Print" app by Gapman1980 (MIT), without CUPS and without the
Supervisor: works on Home Assistant Container/Core too. One config entry per printer; one sidebar panel for all of
them. The panel uploads to authenticated APIs; files are converted in Python (PDFium, Pillow) and sent over IPP.
"""
from __future__ import annotations

import json
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
from .const import (CONF_ADMIN_ONLY, CONF_MONO, CONF_NAME, CONF_PAPER, CONF_URI, DOMAIN, MAX_UPLOAD, PANEL_URL,
                    STATIC_URL, VERSION)
from .manager import PrintHub

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema({
    vol.Exclusive("file", "sorgente"): cv.string,
    vol.Exclusive("url", "sorgente"): cv.url,
    vol.Exclusive("testo", "sorgente"): cv.string,
    vol.Optional("stampante"): cv.string,
    vol.Optional("nome"): cv.string,
    vol.Optional("copie", default=1): vol.All(vol.Coerce(int), vol.Range(1, 50)),
    vol.Optional("pagine", default=""): cv.string,
    vol.Optional("adatta", default=True): cv.boolean,
    vol.Optional("bianco_nero"): cv.boolean,
})

EXT_BY_TYPE = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic",
               "image/heif": ".heif", "text/plain": ".txt"}


def _opts(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


def _panel_mtime() -> float:
    return (Path(__file__).parent / "frontend" / "stampa-remota-panel.js").stat().st_mtime


def _hub(hass: HomeAssistant) -> PrintHub:
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = PrintHub(hass)
    return hass.data[DOMAIN]


async def _register_panel(hass: HomeAssistant) -> None:
    """One panel for all printers; only for administrators if any printer asks so."""
    admin_only = any(_opts(e).get(CONF_ADMIN_ONLY, False) for e in hass.config_entries.async_entries(DOMAIN)
                     if not e.disabled_by)
    mtime = int(await hass.async_add_executor_job(_panel_mtime))   # file access off the event loop
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="stampa-remota-panel",
        sidebar_title="Stampa",
        sidebar_icon="mdi:printer-wireless",
        # version = file date: a new panel reaches the browsers even without a new VERSION
        module_url=f"{STATIC_URL}/stampa-remota-panel.js?v={VERSION}-{mtime}",
        require_admin=admin_only,
        config={},
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    o = _opts(entry)
    hub = _hub(hass)
    await hub.async_load()
    name = o.get(CONF_NAME) or entry.title
    await hub.add_printer(entry.entry_id, name, o[CONF_URI], o.get(CONF_PAPER, "A4"), o.get(CONF_MONO, False))
    entry.runtime_data = hub

    if not hass.data.get(f"{DOMAIN}_http"):          # static files and views cannot be removed: once only
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)])
        for view in (PrintView, StatusView, PrepareView, ThumbView, CancelView, ForgetView, ClearView):
            hass.http.register_view(view)
        hass.data[f"{DOMAIN}_http"] = True
    await _register_panel(hass)

    if not hass.services.has_service(DOMAIN, "stampa"):
        async def print_service(call: ServiceCall) -> ServiceResponse:
            return await _print_service(hass, call)
        hass.services.async_register(DOMAIN, "stampa", print_service, SERVICE_SCHEMA,
                                     supports_response=SupportsResponse.OPTIONAL)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _print_service(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    hub = _hub(hass)
    d = call.data
    try:
        conn = hub.printer(d.get("stampante"))
    except KeyError as err:
        raise HomeAssistantError(err.args[0]) from err
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
    job = await hub.submit(name, data, C.Options(
        copies=d["copie"], pages=d["pagine"], fit=d["adatta"], mono=d.get("bianco_nero", conn.mono_default)),
        user="automazione", printer=conn.entry_id)
    if job["stato"] == "errore":
        raise HomeAssistantError(job["errore"])
    return {"id": job["id"], "stato": job["stato"], "pagine": job["pagine"], "stampante": job["stampante"]}


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = _hub(hass)
    await hub.remove_printer(entry.entry_id)
    if not hub.printers:                       # last printer gone: panel and action go too
        await hub.async_stop()
        frontend.async_remove_panel(hass, PANEL_URL)
        hass.services.async_remove(DOMAIN, "stampa")
        hass.data.pop(DOMAIN, None)
    else:
        await _register_panel(hass)
    return True


# ---------------------------------------------------------------- HTTP API (all with Home Assistant login)

def _hub_of(request: web.Request) -> PrintHub:
    hub = request.app["hass"].data.get(DOMAIN)
    if hub is None or not hub.printers:
        raise web.HTTPServiceUnavailable(text="Stampa remota non configurata")
    return hub


async def _read_upload(request: web.Request) -> tuple[dict[str, str], str | None, bytes, str]:
    """Multipart form read as a stream (no 16 MB limit). -> fields, file name, data, error."""
    reader = await request.multipart()
    fields: dict[str, str] = {}
    name, buf = None, bytearray()
    async for part in reader:
        if part.name == "file" and part.filename:
            name = os.path.basename(part.filename) or "file"
            ctype = (part.headers.get("Content-Type") or "").split(";")[0].lower()
            if "." not in name:            # Android pickers: name without extension
                name += EXT_BY_TYPE.get(ctype, "")
            while chunk := await part.read_chunk(1 << 16):
                buf += chunk
                if len(buf) > MAX_UPLOAD:
                    return fields, None, b"", "File troppo grande (massimo 60 MB)"
        elif part.name:
            fields[part.name] = (await part.text()).strip()
    return fields, name, bytes(buf), ""


class PrintView(HomeAssistantView):
    """file (or token from the preview) + stampante, copie, pagine, adatta, bianco_nero, layout."""
    url = "/api/stampa_remota/stampa"
    name = "api:stampa_remota:stampa"

    async def post(self, request: web.Request) -> web.Response:
        hub = _hub_of(request)
        fields, name, data, err = await _read_upload(request)
        if err:
            return self.json({"ok": False, "errore": err})
        src = None
        if not name and fields.get("token"):
            kept = hub.preview_file(fields["token"])
            if not kept:
                return self.json({"ok": False, "errore": "Anteprima scaduta: scegli di nuovo il file"})
            name, data, src = kept
        if not name:
            return self.json({"ok": False, "errore": "Nessun file ricevuto"})
        try:
            copies = max(1, min(50, int(fields.get("copie") or 1)))
        except ValueError:
            copies = 1
        layout = None
        if fields.get("layout"):
            try:
                layout = C.Layout.from_dict(json.loads(fields["layout"]))
            except ValueError:
                layout = None
        user = request.get("hass_user")
        try:
            job = await hub.submit(name, data, C.Options(
                copies=copies, pages=fields.get("pagine", ""), fit=fields.get("adatta", "1") == "1",
                mono=fields.get("bianco_nero", "0") == "1", layout=layout),
                user=user.name if user else "", printer=fields.get("stampante"), src=src)
        except KeyError as e:
            return self.json({"ok": False, "errore": e.args[0]})
        return self.json({"ok": job["stato"] != "errore", "errore": job["errore"], "id": job["id"]})


class PrepareView(HomeAssistantView):
    """Upload once for the preview: token, pages, page sizes."""
    url = "/api/stampa_remota/prepara"
    name = "api:stampa_remota:prepara"

    async def post(self, request: web.Request) -> web.Response:
        hub = _hub_of(request)
        fields, name, data, err = await _read_upload(request)
        if err or not name:
            return self.json({"ok": False, "errore": err or "Nessun file ricevuto"})
        try:
            conn = hub.printer(fields.get("stampante"))
            info = await hub.prepare(name, data, conn)
        except (C.ConvertError, KeyError) as e:
            return self.json({"ok": False, "errore": e.args[0]})
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Anteprima non riuscita per %s", name)
            return self.json({"ok": False, "errore": "Anteprima non disponibile per questo file: puoi comunque stamparlo"})
        return self.json({"ok": True, **info})


class ThumbView(HomeAssistantView):
    """PNG of one page of a prepared file: ?token=&pagina=1&w=600"""
    url = "/api/stampa_remota/anteprima"
    name = "api:stampa_remota:anteprima"

    async def get(self, request: web.Request) -> web.Response:
        hub = _hub_of(request)
        try:
            page = int(request.query.get("pagina", "1")) - 1
            width = int(float(request.query.get("w", "600")))
        except ValueError:
            return web.Response(status=400)
        png = await hub.thumbnail(request.query.get("token", ""), page, width)
        if png is None:
            return web.Response(status=404, text="anteprima scaduta")
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "private, max-age=600"})


class StatusView(HomeAssistantView):
    url = "/api/stampa_remota/stato"
    name = "api:stampa_remota:stato"

    async def get(self, request: web.Request) -> web.Response:
        return self.json(await _hub_of(request).status())


class CancelView(HomeAssistantView):
    url = "/api/stampa_remota/annulla"
    name = "api:stampa_remota:annulla"

    async def post(self, request: web.Request) -> web.Response:
        data = await request.json()
        return self.json({"ok": await _hub_of(request).cancel(str(data.get("id", "")))})


class ForgetView(HomeAssistantView):
    url = "/api/stampa_remota/togli"
    name = "api:stampa_remota:togli"

    async def post(self, request: web.Request) -> web.Response:
        data = await request.json()
        return self.json({"ok": await _hub_of(request).forget(str(data.get("id", "")))})


class ClearView(HomeAssistantView):
    url = "/api/stampa_remota/svuota"
    name = "api:stampa_remota:svuota"

    async def post(self, request: web.Request) -> web.Response:
        return self.json({"ok": True, "tolte": await _hub_of(request).clear()})

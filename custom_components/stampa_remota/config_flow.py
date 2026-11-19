"""Config flow: one entry per printer. The address is checked over IPP (read-only, nothing is printed) and,
if it does not work, the form says why in plain words (like Remote Print's ippcheck)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .const import CONF_ADMIN_ONLY, CONF_MONO, CONF_NAME, CONF_PAPER, CONF_URI, DOMAIN, PAPERS
from .ipp import IppClient, IppError, check_uri

DRIVERLESS = ("application/pdf", "image/urf", "image/pwg-raster", "image/jpeg")


def _normalize(uri: str) -> str:
    uri = uri.strip().strip("\"'")
    if "://" not in uri:                     # only an IP / host name: AirPrint standard path
        uri = f"ipp://{uri}/ipp/print"
    return uri


async def _probe(hass, uri: str) -> tuple[str | None, str]:
    """-> (problem in plain words or None, printer model)."""
    if bad := check_uri(uri):
        return bad, ""
    try:
        attrs = await IppClient(async_get_clientsession(hass, verify_ssl=False), uri).printer_attributes()
    except IppError as err:
        return str(err), ""
    fmts = attrs.get("document-format-supported", [])
    if not any(f in fmts for f in DRIVERLESS):
        return ("la stampante risponde ma non offre nessun formato senza driver (PDF, URF, PWG o JPEG): "
                f"formati dichiarati {', '.join(fmts) or 'nessuno'}"), ""
    return None, attrs.get("printer-make-and-model", ["Stampante"])[0]


def _options_schema(d: dict[str, Any]) -> dict:
    return {
        vol.Required(CONF_PAPER, default=d.get(CONF_PAPER, "A4")): SelectSelector(
            SelectSelectorConfig(options=PAPERS, mode=SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_MONO, default=d.get(CONF_MONO, False)): bool,
        vol.Required(CONF_ADMIN_ONLY, default=d.get(CONF_ADMIN_ONLY, False)): bool,
    }


class StampaRemotaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"dettaglio": ""}
        if user_input is not None:
            uri = _normalize(user_input[CONF_URI])
            self._async_abort_entries_match({CONF_URI: uri})
            problem, model = await _probe(self.hass, uri)
            if problem:
                errors["base"] = "diagnosi"
                placeholders["dettaglio"] = problem
            else:
                name = (user_input.get(CONF_NAME) or "").strip() or model
                return self.async_create_entry(title=name, data={**user_input, CONF_URI: uri, CONF_NAME: name})
        d = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URI, default=d.get(CONF_URI, "")): str,
                vol.Optional(CONF_NAME, default=d.get(CONF_NAME, "")): str,
                **_options_schema(d)}),
            errors=errors, description_placeholders=placeholders,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders = {"dettaglio": ""}
        if user_input is not None:
            uri = _normalize(user_input[CONF_URI])
            problem, _ = await _probe(self.hass, uri)
            if problem:
                errors["base"] = "diagnosi"
                placeholders["dettaglio"] = problem
            else:
                name = (user_input.get(CONF_NAME) or "").strip() or entry.title
                return self.async_update_reload_and_abort(entry, title=name,
                                                          data_updates={CONF_URI: uri, CONF_NAME: name})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_URI, default=entry.data[CONF_URI]): str,
                vol.Optional(CONF_NAME, default=entry.data.get(CONF_NAME, entry.title)): str}),
            errors=errors, description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StampaRemotaOptionsFlow()


class StampaRemotaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        cur = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(_options_schema(cur)))

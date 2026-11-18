"""Config flow: printer address (checked over IPP), paper, defaults."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .const import CONF_ADMIN_ONLY, CONF_MONO, CONF_PAPER, CONF_URI, DOMAIN, PAPERS
from .ipp import IppClient, IppError


def _normalize(uri: str) -> str:
    uri = uri.strip().strip("\"'")
    if "://" not in uri:                     # only an IP / host name: AirPrint standard path
        uri = f"ipp://{uri}/ipp/print"
    return uri


async def _probe(hass, uri: str) -> tuple[str | None, str]:
    try:
        attrs = await IppClient(async_get_clientsession(hass, verify_ssl=False), uri).printer_attributes()
    except IppError:
        return "cannot_connect", ""
    fmts = attrs.get("document-format-supported", [])
    if not any(f in fmts for f in ("application/pdf", "image/urf", "image/jpeg")):
        return "no_driverless", ""
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
        if user_input is not None:
            uri = _normalize(user_input[CONF_URI])
            err, model = await _probe(self.hass, uri)
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=model, data={**user_input, CONF_URI: uri})
        d = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URI, default=d.get(CONF_URI, "")): str, **_options_schema(d)}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            uri = _normalize(user_input[CONF_URI])
            err, model = await _probe(self.hass, uri)
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(entry, title=model, data_updates={CONF_URI: uri})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_URI, default=entry.data[CONF_URI]): str}),
            errors=errors,
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

"""Config flow for TMD WRF Forecast."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TmdApi, TmdApiError
from .const import DOMAIN, NAME

# rough outline of the WRF domain over Thailand and its neighbours
LAT_RANGE = (4.0, 22.5)
LON_RANGE = (95.5, 107.5)


class TmdWrfConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            lat, lon = float(user_input[CONF_LATITUDE]), float(user_input[CONF_LONGITUDE])
            await self.async_set_unique_id(f"{lat:.3f}_{lon:.3f}")
            self._abort_if_unique_id_configured()
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                errors["base"] = "outside_domain"
            else:
                try:
                    points = await TmdApi(async_get_clientsession(self.hass), lat, lon).meteogram()
                    if not points:
                        errors["base"] = "outside_domain"
                except TmdApiError:
                    errors["base"] = "cannot_connect"
            if not errors:
                name = user_input[CONF_NAME].strip() or NAME
                return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_LATITUDE: lat, CONF_LONGITUDE: lon})

        defaults = user_input or {
            CONF_NAME: f"TMD {self.hass.config.location_name}".strip(),
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
        }
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=defaults[CONF_NAME]): selector.TextSelector(),
            vol.Required(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-90, max=90, step="any", mode=selector.NumberSelectorMode.BOX)),
            vol.Required(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-180, max=180, step="any", mode=selector.NumberSelectorMode.BOX)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

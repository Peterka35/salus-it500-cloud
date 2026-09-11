"""Config flow for Salus iT500 integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .pyit500.auth import Auth
from .pyit500.exceptions import InvalidAuth, SalusError
from .pyit500.pyit500 import PyIt500

_LOGGER = logging.getLogger(__name__)


class NoDevices(Exception):
    """Error to indicate no devices found."""


async def validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    auth = Auth(async_get_clientsession(hass), data[CONF_USERNAME], data[CONF_PASSWORD])
    await auth.refresh_token()

    api = PyIt500(auth)
    device_list = await api.async_get_device_list()
    if not device_list:
        raise NoDevices

    try:
        device = await api.async_get_device(device_list[0].device_id)
        title = device.description or f"Salus iT500 ({device_list[0].name})"
    except SalusError as err:
        _LOGGER.warning("Failed to get device details, using fallback title: %s", err)
        title = f"Salus iT500 ({device_list[0].name})"

    return {
        "title": title,
        "device_count": len(device_list),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Salus iT500."""

    VERSION = 1

    async def _async_validate(self, data: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Return account info when the credentials work, otherwise form errors."""
        try:
            return await validate_input(self.hass, data), {}
        except InvalidAuth:
            return None, {"base": "invalid_auth"}
        except NoDevices:
            return None, {"base": "no_devices"}
        except SalusError as err:
            _LOGGER.warning("Cannot connect to Salus API: %s", err)
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected exception during config flow")
            return None, {"base": "unknown"}

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            info, errors = await self._async_validate(user_input)
            if info is not None:
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> config_entries.ConfigFlowResult:
        """Handle rejected credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Ask for the current password of the account."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            info, errors = await self._async_validate({**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]})
            if info is not None:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): cv.string}),
            description_placeholders={"username": reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )

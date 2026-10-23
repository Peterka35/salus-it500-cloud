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

from .const import CONF_DEVICE_ID, DOMAIN
from .pyit500.auth import Auth
from .pyit500.exceptions import InvalidAuth, SalusError
from .pyit500.pyit500 import PyIt500

_LOGGER = logging.getLogger(__name__)


class NoDevices(Exception):
    """Error to indicate no devices found."""


async def validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect and return the account's thermostats.

    Thermostat names are keyed by device id, in the order of the account's device list.
    """
    auth = Auth(async_get_clientsession(hass), data[CONF_USERNAME], data[CONF_PASSWORD])
    await auth.refresh_token()

    api = PyIt500(auth)
    device_list = await api.async_get_device_list()
    if not device_list:
        raise NoDevices

    devices: dict[str, str] = {}
    for item in device_list:
        try:
            device = await api.async_get_device(item.device_id)
            title = device.description or f"Salus iT500 ({item.name})"
        except SalusError as err:
            _LOGGER.warning("Failed to get device details, using fallback title: %s", err)
            title = f"Salus iT500 ({item.name})"
        devices[str(item.device_id)] = title
    return devices


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Salus iT500."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, Any] = {}
        self._devices: dict[str, str] = {}

    async def _async_validate(self, data: Mapping[str, Any]) -> tuple[dict[str, str] | None, dict[str, str]]:
        """Return the account's thermostats when the credentials work, otherwise form errors."""
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
            # Entries made before 1.4.0 are keyed by the account until their next setup ties them to a thermostat
            if user_input[CONF_USERNAME].lower() in self._async_current_ids():
                return self.async_abort(reason="already_configured")

            devices, errors = await self._async_validate(user_input)
            if devices is not None:
                self._credentials = user_input
                self._devices = devices
                if len(devices) == 1:
                    return await self._async_create(next(iter(devices)))
                return await self.async_step_device()

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

    async def async_step_device(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Let the user pick one of the account's thermostats that has no entry yet."""
        if user_input is not None:
            return await self._async_create(user_input[CONF_DEVICE_ID])

        configured = self._async_current_ids()
        offered = {device_id: title for device_id, title in self._devices.items() if device_id not in configured}
        if not offered:
            return self.async_abort(reason="already_configured")

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(offered)}),
        )

    async def _async_create(self, device_id: str) -> config_entries.ConfigFlowResult:
        """Add an entry for one thermostat of the account."""
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._devices[device_id],
            data={**self._credentials, CONF_DEVICE_ID: device_id},
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

"""Config flow for Salus iT500 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .pyit500.auth import Auth
from .pyit500.pyit500 import PyIt500

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class NoDevices(Exception):
    """Error to indicate no devices found."""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    _LOGGER.info("Starting Salus iT500 configuration validation for user: %s", data[CONF_USERNAME])

    session = async_get_clientsession(hass)
    auth = Auth(session, data[CONF_USERNAME], data[CONF_PASSWORD])

    # Step 1: Authenticate
    _LOGGER.debug("Step 1: Attempting authentication...")
    try:
        await auth.refresh_token()
        _LOGGER.info("Authentication successful for user: %s", data[CONF_USERNAME])
    except Exception as err:
        _LOGGER.error(
            "Authentication failed for user %s: %s (%s)",
            data[CONF_USERNAME], err, type(err).__name__
        )
        raise InvalidAuth from err

    api = PyIt500(auth)

    # Step 2: Get device list
    _LOGGER.debug("Step 2: Fetching device list...")
    try:
        device_list = await api.async_get_device_list()
        _LOGGER.info("Found %d device(s)", len(device_list) if device_list else 0)
        if device_list:
            for idx, dev in enumerate(device_list):
                _LOGGER.debug("Device %d: id=%s, name=%s", idx, dev.device_id, dev.name)
    except Exception as err:
        _LOGGER.error(
            "Failed to get device list: %s (%s)",
            err, type(err).__name__
        )
        raise CannotConnect from err

    if not device_list:
        _LOGGER.error("No devices found for user %s", data[CONF_USERNAME])
        raise NoDevices

    # Step 3: Get device details
    _LOGGER.debug("Step 3: Fetching device details for device_id=%s...", device_list[0].device_id)
    try:
        device = await api.async_get_device(device_list[0].device_id)
        title = device.description or f"Salus iT500 ({device_list[0].name})"
        _LOGGER.info("Device details retrieved: %s", title)
    except Exception as err:
        _LOGGER.warning("Failed to get device details: %s, using fallback title", err)
        title = f"Salus iT500 ({device_list[0].name})"

    _LOGGER.info("Configuration validation completed successfully")
    return {
        "title": title,
        "device_count": len(device_list),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Salus iT500."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            _LOGGER.debug("Config flow: user submitted credentials for %s", user_input.get(CONF_USERNAME))
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                _LOGGER.warning("Config flow: cannot connect to Salus API")
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                _LOGGER.warning("Config flow: invalid authentication for user %s", user_input.get(CONF_USERNAME))
                errors["base"] = "invalid_auth"
            except NoDevices:
                _LOGGER.warning("Config flow: no devices found for user %s", user_input.get(CONF_USERNAME))
                errors["base"] = "no_devices"
            except Exception as err:
                _LOGGER.exception("Unexpected exception during config flow: %s", err)
                errors["base"] = "unknown"
            else:
                _LOGGER.info("Config flow: successfully validated, creating entry for %s", info["title"])
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

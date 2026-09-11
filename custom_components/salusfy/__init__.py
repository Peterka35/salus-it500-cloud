"""The Salus iT500 integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import SalusConfigEntry, SalusDataCoordinator
from .pyit500.auth import Auth
from .pyit500.device import Device
from .pyit500.exceptions import InvalidAuth, SalusError
from .pyit500.pyit500 import PyIt500

PLATFORMS = [Platform.CLIMATE, Platform.WATER_HEATER]


async def async_setup_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    """Set up Salus from a config entry."""
    auth = Auth(async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    try:
        await auth.refresh_token()
        device_list = await PyIt500(auth).async_get_device_list()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed("Salus rejected the credentials") from err
    except SalusError as err:
        raise ConfigEntryNotReady(f"Salus API is not available: {err}") from err

    if not device_list:
        raise ConfigEntryNotReady("No Salus iT500 device found on the account")

    # Use the first device (most users have only one thermostat)
    coordinator = SalusDataCoordinator(hass, entry, Device(device_list[0].device_id, None, auth))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

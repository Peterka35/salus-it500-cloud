"""The Salus iT500 integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession

from .const import CONF_DEVICE_ID
from .coordinator import SalusConfigEntry, SalusDataCoordinator
from .portal import SalusPortal
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

    device_id = entry.data.get(CONF_DEVICE_ID)
    if device_id is None:
        # Entries made before 1.4.0 always showed the first thermostat of the account
        device_id = str(device_list[0].device_id)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_DEVICE_ID: device_id}, unique_id=device_id
        )
    item = next((item for item in device_list if str(item.device_id) == device_id), None)
    if item is None:
        raise ConfigEntryError(f"Salus iT500 thermostat {device_id} is no longer on the account")

    # The portal signs in with a cookie and on a different host, so it needs a session of its own
    portal_session = async_create_clientsession(hass)
    entry.async_on_unload(portal_session.close)
    portal = SalusPortal(portal_session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], device_id=device_id)

    coordinator = SalusDataCoordinator(hass, entry, Device(item.device_id, None, auth), portal=portal)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

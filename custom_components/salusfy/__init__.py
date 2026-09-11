"""The Salus iT500 integration."""
import logging
from asyncio import sleep
from aiohttp import ServerDisconnectedError, ClientResponseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
from .pyit500.auth import Auth
from .pyit500.device import Device
from .pyit500.pyit500 import PyIt500

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.WATER_HEATER]


class QuietLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that suppresses debug messages."""

    def debug(self, msg, *args, **kwargs):
        """Suppress debug messages."""
        pass  # Don't forward debug messages


class SalusDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for Salus devices."""

    def __init__(self, hass: HomeAssistant, api: PyIt500, device: Device) -> None:
        """Initialize the coordinator."""
        # Use QuietLoggerAdapter to suppress debug messages
        quiet_logger = QuietLoggerAdapter(_LOGGER, {})
        super().__init__(
            hass,
            quiet_logger,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.device = device

    async def _async_update_data(self):
        """Fetch data from API."""
        max_retries = 2
        retry_delay = 2

        for attempt in range(max_retries + 1):
            try:
                await self.device.async_update()
                return self.device
            except (ServerDisconnectedError, ClientResponseError) as err:
                # Handle connection and auth errors with retry
                if attempt < max_retries:
                    error_type = "Auth" if isinstance(err, ClientResponseError) and err.status in (401, 403) else "Connection"
                    _LOGGER.warning(
                        "%s error (attempt %d/%d), retrying in %d seconds... Error: %s",
                        error_type,
                        attempt + 1,
                        max_retries + 1,
                        retry_delay,
                        err,
                    )
                    await sleep(retry_delay)
                    # Try to refresh auth token on retry (auth.request already does this, but as fallback)
                    try:
                        await self.device.auth.refresh_token()
                    except Exception as refresh_err:
                        _LOGGER.debug("Token refresh failed: %s", refresh_err)
                    continue
                else:
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Error communicating with API: {err}") from err


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Salus component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Salus from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    _LOGGER.info("Setting up Salus iT500 integration for user: %s", username)

    session = async_get_clientsession(hass)
    auth = Auth(session, username, password)

    # Step 1: Authenticate
    _LOGGER.debug("Setup step 1: Authenticating...")
    try:
        await auth.refresh_token()
        _LOGGER.debug("Authentication successful")
    except Exception as err:
        _LOGGER.error(
            "Failed to authenticate with Salus API for user %s: %s (%s)",
            username, err, type(err).__name__
        )
        return False

    api = PyIt500(auth)

    # Step 2: Get device list
    _LOGGER.debug("Setup step 2: Fetching device list...")
    try:
        device_list = await api.async_get_device_list()
        _LOGGER.debug("Retrieved %d device(s)", len(device_list) if device_list else 0)
    except Exception as err:
        _LOGGER.error("Failed to get device list: %s (%s)", err, type(err).__name__)
        return False

    if not device_list:
        _LOGGER.error("No devices found for account: %s", username)
        return False

    # Use the first device (most users have only one thermostat)
    device_id = device_list[0].device_id
    _LOGGER.debug("Setup step 3: Loading device details for device_id=%s...", device_id)

    try:
        device = await api.async_get_device(device_id)
        _LOGGER.info("Loaded device: %s (id=%s)", device.description or device_list[0].name, device_id)
    except Exception as err:
        _LOGGER.error("Failed to load device %s: %s (%s)", device_id, err, type(err).__name__)
        return False

    # Step 4: Create coordinator
    _LOGGER.debug("Setup step 4: Creating data coordinator...")
    coordinator = SalusDataCoordinator(hass, api, device)

    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("Initial data refresh completed")
    except Exception as err:
        _LOGGER.error("Failed to perform initial data refresh: %s (%s)", err, type(err).__name__)
        return False

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Step 5: Setup platforms
    _LOGGER.debug("Setup step 5: Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Salus iT500 integration setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

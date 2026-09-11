"""Tests for Salus iT500 integration setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.salusfy import PLATFORMS, async_setup_entry

from . import fixtures
from .ha_helpers import create_entry
from .helpers import FakeResponse, FakeSession, attributes_response, login_response

CLIENT_SESSION = "custom_components.salusfy.async_get_clientsession"


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    return hass


async def test_setup_loads_first_device_of_account() -> None:
    """The first device of the account is loaded and its platforms are set up."""

    session = FakeSession()
    session.add("sessions", login_response())
    session.add("getDeviceList", FakeResponse(200, text=fixtures.device_list_xml()))
    session.add("getDeviceAttributesWithValues", attributes_response())
    hass, entry = _hass(), create_entry()

    with patch(CLIENT_SESSION, return_value=session):
        assert await async_setup_entry(hass, entry)

    assert (entry.runtime_data.device.device_id, entry.runtime_data.device.description) == (
        fixtures.DEVICE_ID,
        "Apartmán A",
    )
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)


async def test_rejected_credentials_start_reauth() -> None:
    """Rejected credentials ask the user for new ones instead of failing the setup for good."""

    session = FakeSession()
    session.add("sessions", FakeResponse(403))

    with patch(CLIENT_SESSION, return_value=session), pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(_hass(), create_entry())


async def test_unavailable_api_retries_setup() -> None:
    """Setup is retried later when Salus API is not available."""

    session = FakeSession()
    session.add("sessions", FakeResponse(503))

    with patch(CLIENT_SESSION, return_value=session), pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(_hass(), create_entry())

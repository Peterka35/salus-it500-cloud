"""Tests for Salus iT500 integration setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady

from custom_components.salusfy import PLATFORMS, async_setup_entry
from custom_components.salusfy.const import CONF_DEVICE_ID

from . import fixtures
from .ha_helpers import create_entry
from .helpers import FakeResponse, FakeSession, attributes_response, login_response

CLIENT_SESSION = "custom_components.salusfy.async_get_clientsession"


@pytest.fixture(autouse=True)
def portal_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the portal's session: a second real one needs the running core for its resolver."""

    monkeypatch.setattr("custom_components.salusfy.async_create_clientsession", lambda _hass: MagicMock())


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


def _two_thermostats_session() -> FakeSession:
    session = FakeSession()
    session.add("sessions", login_response())
    session.add(
        "getDeviceList", FakeResponse(200, text=fixtures.device_list_xml(fixtures.DEVICE_ID, fixtures.SECOND_DEVICE_ID))
    )
    session.add("getDeviceAttributesWithValues", attributes_response(desc="Chata"))
    return session


async def test_setup_loads_the_chosen_thermostat() -> None:
    """The entry loads the thermostat chosen when it was added, not the first one of the account."""

    session = _two_thermostats_session()
    hass, entry = _hass(), create_entry(device_id=str(fixtures.SECOND_DEVICE_ID))

    with patch(CLIENT_SESSION, return_value=session):
        assert await async_setup_entry(hass, entry)

    assert str(entry.runtime_data.device.device_id) == str(fixtures.SECOND_DEVICE_ID)
    assert str(session.endpoint_calls("getDeviceAttributesWithValues")[0]["data"]["devId"]) == str(
        fixtures.SECOND_DEVICE_ID
    )
    hass.config_entries.async_update_entry.assert_not_called()


async def test_entry_of_an_older_version_is_tied_to_the_first_thermostat() -> None:
    """An entry made before the thermostat choice stores the thermostat it has always shown."""

    hass, entry = _hass(), create_entry()

    with patch(CLIENT_SESSION, return_value=_two_thermostats_session()):
        assert await async_setup_entry(hass, entry)

    hass.config_entries.async_update_entry.assert_called_once_with(
        entry,
        data={**entry.data, CONF_DEVICE_ID: str(fixtures.DEVICE_ID)},
        unique_id=str(fixtures.DEVICE_ID),
    )


async def test_thermostat_gone_from_the_account_fails_setup() -> None:
    """A thermostat no longer on the account is reported instead of loading another one."""

    with patch(CLIENT_SESSION, return_value=_two_thermostats_session()), pytest.raises(ConfigEntryError):
        await async_setup_entry(_hass(), create_entry(device_id="201399999"))


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

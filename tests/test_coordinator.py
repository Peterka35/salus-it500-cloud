"""Tests for Salus iT500 data coordinator."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.salusfy.pyit500.hotwaterzone import Mode

from . import fixtures
from .ha_helpers import CALL_LATER, create_coordinator
from .helpers import FakeResponse, FakeSession


async def test_short_api_outage_keeps_last_state() -> None:
    """Salus API failing for a few minutes does not make the entities unavailable."""

    session = FakeSession()
    coordinator, clock = await create_coordinator(session)
    session.add("getDeviceAttributesWithValues", FakeResponse(500))
    clock[0] = 540

    assert await coordinator._async_update_data() is coordinator.device


async def test_long_api_outage_fails_update() -> None:
    """Salus API failing for more than ten minutes since the last successful update fails the update."""

    session = FakeSession()
    coordinator, clock = await create_coordinator(session)
    session.add("getDeviceAttributesWithValues", FakeResponse(500))
    clock[0] = 601

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_rejected_credentials_during_update_start_reauth() -> None:
    """Credentials rejected while renewing the security token ask the user for new credentials."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    session.add("getDeviceAttributesWithValues", FakeResponse(401))
    session.add("sessions", FakeResponse(403))

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_command_is_shown_at_once_and_confirmed_later() -> None:
    """Entities show the commanded state right away; the API state is fetched 5 and 20 seconds later."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    with patch(CALL_LATER) as call_later:
        await coordinator.async_send_command(lambda: coordinator.device.hw.async_set_mode(Mode.AUTO))

    listener.assert_called_once()
    assert coordinator.device.hw.mode == Mode.AUTO
    assert [call.args[1] for call in call_later.call_args_list] == [5, 20]


async def test_failed_command_raises_home_assistant_error() -> None:
    """A command Salus does not accept is reported to the user."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(3)))

    with patch(CALL_LATER), pytest.raises(HomeAssistantError):
        await coordinator.async_send_command(lambda: coordinator.device.hw.async_set_mode(Mode.AUTO))

    assert coordinator.device.hw.mode == Mode.ON


async def test_command_with_rejected_credentials_starts_reauth() -> None:
    """Credentials rejected during a command ask the user for new credentials."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(403))
    session.add("sessions", FakeResponse(403))

    with patch(CALL_LATER), pytest.raises(HomeAssistantError):
        await coordinator.async_send_command(lambda: coordinator.device.hw.async_set_mode(Mode.AUTO))

    coordinator.config_entry.async_start_reauth.assert_called_once_with(coordinator.hass)


async def test_shutdown_cancels_confirmation_refreshes() -> None:
    """Unloading the integration cancels scheduled confirmation refreshes."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    with patch(CALL_LATER) as call_later:
        await coordinator.async_send_command(lambda: coordinator.device.hw.async_set_mode(Mode.AUTO))

    await coordinator.async_shutdown()

    assert call_later.return_value.call_count == 2


# The gateway uploads an attribute only when it changes, so a thermostat sitting steady at its setpoint
# can stay quiet for many hours (fourteen in one zone, 2026-10-02). Whether it is still connected is what
# the cloud's `presenceInfo` says; an offline thermostat keeps answering with the values it last had.
NOW = 1_790_240_000.0


async def test_connected_device_that_has_nothing_new_to_report_is_online() -> None:
    """A steady thermostat uploads nothing for hours; that silence alone is not an outage."""

    coordinator, _ = await create_coordinator(FakeSession(), reported_at=NOW - 14 * 3600, presence="1", now=NOW)

    assert not coordinator.device_offline


async def test_disconnected_device_with_old_values_is_offline() -> None:
    """Values last uploaded long ago by a gateway the cloud has lost are not the thermostat's state."""

    coordinator, _ = await create_coordinator(FakeSession(), reported_at=NOW - 31 * 60, presence="0", now=NOW)

    assert coordinator.device_offline


async def test_device_uploading_now_is_online_whatever_presence_says() -> None:
    """`presenceInfo` read 0 on gateways uploading normally (2026-09-24); a fresh upload outweighs it."""

    coordinator, _ = await create_coordinator(FakeSession(), reported_at=NOW - 6 * 60, presence="0", now=NOW)

    assert not coordinator.device_offline


async def test_device_without_presence_is_not_called_offline() -> None:
    """Without presence there is no evidence either way: old values alone mean nothing."""

    coordinator, _ = await create_coordinator(FakeSession(), reported_at=NOW - 6 * 24 * 3600, now=NOW)

    assert not coordinator.device_offline


async def test_device_without_upload_times_is_not_called_offline() -> None:
    """Without upload times there is no evidence either way, so the entities stay as they were."""

    coordinator, _ = await create_coordinator(FakeSession(), presence="0", now=NOW)

    assert not coordinator.device_offline


async def test_entities_of_an_offline_device_are_unavailable() -> None:
    """An offline thermostat must not look controllable: its values are days old and commands fail."""

    from custom_components.salusfy.climate import SalusThermostat
    from custom_components.salusfy.pyit500.zone import Prefix
    from custom_components.salusfy.water_heater import SalusWaterHeater

    online, _ = await create_coordinator(FakeSession(), reported_at=NOW - 6 * 24 * 3600, presence="1", now=NOW)
    offline, _ = await create_coordinator(FakeSession(), reported_at=NOW - 6 * 24 * 3600, presence="0", now=NOW)

    assert SalusThermostat(online, Prefix.CH1).available
    assert SalusWaterHeater(online).available
    assert not SalusThermostat(offline, Prefix.CH1).available
    assert not SalusWaterHeater(offline).available

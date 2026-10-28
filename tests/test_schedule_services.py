"""Tests of the weekly program services on the climate platform."""

from datetime import time
from unittest.mock import MagicMock

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from custom_components.salusfy import climate
from custom_components.salusfy.climate import SERVICE_GET_SCHEDULE, SERVICE_SET_SCHEDULE, SalusThermostat
from custom_components.salusfy.program import ProgramError, SalusProgram, Slot
from custom_components.salusfy.pyit500.exceptions import InvalidAuth
from custom_components.salusfy.pyit500.zone import Prefix

from . import fixtures
from .ha_helpers import create_coordinator
from .helpers import FakeSession
from .test_program import PLAN

SLOTS = [{"time": time(5, 30), "temperature": 22.0}, {"time": time(9, 0), "temperature": 18.0}]


async def _thermostat(zone: Prefix = Prefix.CH1, *, with_program: bool = True) -> SalusThermostat:
    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    coordinator.program = SalusProgram(coordinator.device.auth, fixtures.DEVICE_ID) if with_program else None
    return SalusThermostat(coordinator, zone)


async def test_both_services_are_registered_on_the_platform(entity_platform: MagicMock) -> None:
    coordinator, _ = await create_coordinator(FakeSession())
    entry = MagicMock()
    entry.runtime_data = coordinator

    await climate.async_setup_entry(MagicMock(), entry, MagicMock())

    registered = entity_platform.async_register_entity_service.call_args_list
    assert [call.args[0] for call in registered] == [SERVICE_GET_SCHEDULE, SERVICE_SET_SCHEDULE]
    assert registered[0].kwargs["supports_response"] is SupportsResponse.ONLY
    assert [call.args[2] for call in registered] == ["async_get_schedule", "async_set_schedule"]


async def test_reading_returns_the_documented_response_shape() -> None:
    thermostat = await _thermostat()

    response = await thermostat.async_get_schedule()

    assert response["device_id"] == str(fixtures.DEVICE_ID)
    assert response["schedule_type"] == "all"
    assert response["writable"] is True
    assert set(response["days"]) == {"mon", "tus", "wed", "thu", "fri", "sat", "sun"}
    assert response["days"]["mon"][0] == {"time": "05:30", "temperature": 22.0}
    assert len(response["days"]["sun"]) == len(PLAN)


async def test_writing_sends_the_requested_steps() -> None:
    session = FakeSession()
    coordinator, _ = await create_coordinator(FakeSession())
    written: list[list[Slot]] = []

    async def _capture(slots):
        written.append(list(slots))

    coordinator.program = MagicMock(spec=SalusProgram)
    coordinator.program.async_write = _capture
    thermostat = SalusThermostat(coordinator, Prefix.CH1)

    await thermostat.async_set_schedule(SLOTS)

    assert written == [[Slot("05:30", 22.0), Slot("09:00", 18.0)]]
    assert session.calls == []


async def test_a_write_the_thermostat_did_not_take_is_an_error() -> None:
    coordinator, _ = await create_coordinator(FakeSession())

    async def _refuse(_slots):
        raise ProgramError("Salus accepted the program but mon did not change")

    coordinator.program = MagicMock(spec=SalusProgram)
    coordinator.program.async_write = _refuse
    thermostat = SalusThermostat(coordinator, Prefix.CH1)

    with pytest.raises(HomeAssistantError) as error:
        await thermostat.async_set_schedule(SLOTS)

    assert error.value.translation_key == "command_failed"


async def test_rejected_credentials_start_a_reauth() -> None:
    coordinator, _ = await create_coordinator(FakeSession())

    async def _reject():
        raise InvalidAuth("rejected")

    coordinator.program = MagicMock(spec=SalusProgram)
    coordinator.program.async_read = _reject
    thermostat = SalusThermostat(coordinator, Prefix.CH1)

    with pytest.raises(HomeAssistantError) as error:
        await thermostat.async_get_schedule()

    assert error.value.translation_key == "invalid_auth"
    coordinator.config_entry.async_start_reauth.assert_called_once()


async def test_the_second_heating_zone_is_refused() -> None:
    """The second zone's day attributes were never seen holding a program, so they are not written blind."""

    thermostat = await _thermostat(Prefix.CH2)

    for call in (thermostat.async_get_schedule(), thermostat.async_set_schedule(SLOTS)):
        with pytest.raises(HomeAssistantError) as error:
            await call
        assert error.value.translation_key == "schedule_zone_unsupported"


async def test_a_missing_program_client_is_reported_rather_than_crashing() -> None:
    thermostat = await _thermostat(with_program=False)

    with pytest.raises(HomeAssistantError) as error:
        await thermostat.async_get_schedule()

    assert error.value.translation_key == "schedule_unavailable"


async def test_a_short_program_is_refused_as_an_error_not_a_schema_rejection() -> None:
    """A caller must get a HomeAssistantError it can catch, not a raw voluptuous failure."""

    thermostat = await _thermostat()

    with pytest.raises(HomeAssistantError) as error:
        await thermostat.async_set_schedule(SLOTS)

    assert error.value.translation_key == "command_failed"

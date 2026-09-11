"""Tests for Salus iT500 thermostat entity."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.salusfy import climate
from custom_components.salusfy.climate import SalusThermostat
from custom_components.salusfy.const import DOMAIN
from custom_components.salusfy.pyit500.zone import Prefix

from . import fixtures
from .ha_helpers import CALL_LATER, attach, create_coordinator
from .helpers import FakeResponse, FakeSession


async def test_setup_creates_heating_zone() -> None:
    """Thermostat with hot water has one heating zone with unchanged unique id."""

    coordinator, _ = await create_coordinator(FakeSession())
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await climate.async_setup_entry(MagicMock(), entry, add_entities)

    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [f"{fixtures.DEVICE_ID}_A_climate"]


async def test_friendly_name_is_unchanged() -> None:
    """Device name and entity name form the existing friendly name "<description> Heating Zone 1"."""

    coordinator, _ = await create_coordinator(FakeSession())
    entity = SalusThermostat(coordinator, Prefix.CH1)

    assert entity.has_entity_name
    assert (entity.device_info["name"], entity.name) == ("Apartmán A", "Heating Zone 1")
    assert entity.device_info["identifiers"] == {(DOMAIN, str(fixtures.DEVICE_ID))}


async def test_turn_on_off_and_half_degree_steps_are_supported() -> None:
    """Thermostat can be turned on and off and set in half degree steps like on its display."""

    coordinator, _ = await create_coordinator(FakeSession())
    entity = SalusThermostat(coordinator, Prefix.CH1)

    assert entity.supported_features & ClimateEntityFeature.TURN_ON
    assert entity.supported_features & ClimateEntityFeature.TURN_OFF
    assert entity.target_temperature_step == 0.5


async def test_turn_on_from_off_follows_schedule() -> None:
    """Turned off thermostat is turned on in auto (schedule) mode."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    entity = attach(SalusThermostat(coordinator, Prefix.CH1))

    with patch(CALL_LATER):
        await entity.async_turn_on()

    assert session.attribute_sets() == [("A89", "0")]
    assert (entity.hvac_mode, entity.preset_mode) == (HVACMode.HEAT, "auto")


async def test_turn_on_keeps_active_heating_mode() -> None:
    """Turning on a thermostat already heating in manual mode does not switch it to schedule."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session, A89="0", A92="1")
    entity = attach(SalusThermostat(coordinator, Prefix.CH1))

    with patch(CALL_LATER):
        await entity.async_turn_on()

    assert session.attribute_sets() == []


async def test_failed_command_raises_home_assistant_error() -> None:
    """Command Salus does not accept is reported to the user and not shown as applied."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(3)))
    entity = attach(SalusThermostat(coordinator, Prefix.CH1))

    with patch(CALL_LATER), pytest.raises(HomeAssistantError):
        await entity.async_set_temperature(temperature=22.5)

    assert entity.target_temperature == 21.0

"""Tests for Salus iT500 hot water entity."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.salusfy import water_heater
from custom_components.salusfy.const import DOMAIN
from custom_components.salusfy.water_heater import SalusWaterHeater

from . import fixtures
from .ha_helpers import CALL_LATER, attach, create_coordinator
from .helpers import FakeResponse, FakeSession


async def test_setup_creates_hot_water() -> None:
    """Thermostat with hot water gets hot water entity with unchanged unique id."""

    coordinator, _ = await create_coordinator(FakeSession())
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await water_heater.async_setup_entry(MagicMock(), entry, add_entities)

    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [f"{fixtures.DEVICE_ID}_hw_water_heater"]


async def test_friendly_name_is_unchanged() -> None:
    """Device name and entity name form the existing friendly name "<description> Teplá voda"."""

    coordinator, _ = await create_coordinator(FakeSession())
    entity = SalusWaterHeater(coordinator)

    assert entity.has_entity_name
    assert (entity.device_info["name"], entity.name) == ("Apartmán A", "Teplá voda")
    assert entity.device_info["identifiers"] == {(DOMAIN, str(fixtures.DEVICE_ID))}


async def test_operation_mode_is_shown_at_once() -> None:
    """Selected hot water mode is shown before Salus API reports it."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    entity = attach(SalusWaterHeater(coordinator))

    with patch(CALL_LATER):
        await entity.async_set_operation_mode("auto")

    assert session.attribute_sets() == [("C42", "0")]
    assert entity.current_operation == "auto"


async def test_failed_command_raises_home_assistant_error() -> None:
    """Command Salus does not accept is reported to the user and not shown as applied."""

    session = FakeSession()
    coordinator, _ = await create_coordinator(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(3)))
    entity = attach(SalusWaterHeater(coordinator))

    with patch(CALL_LATER), pytest.raises(HomeAssistantError):
        await entity.async_set_operation_mode("off")

    assert entity.current_operation == "on"

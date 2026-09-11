"""Test helpers for the Home Assistant part of the integration."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.salusfy.coordinator import SalusDataCoordinator

from . import fixtures
from .helpers import FakeSession, create_device

CALL_LATER = "custom_components.salusfy.coordinator.async_call_later"


def create_entry() -> MagicMock:
    """Return config entry being set up."""

    entry = MagicMock()
    entry.entry_id = "salusfy-entry"
    entry.data = {CONF_USERNAME: fixtures.USERNAME, CONF_PASSWORD: fixtures.PASSWORD}
    entry.state = ConfigEntryState.SETUP_IN_PROGRESS
    return entry


async def create_coordinator(
    session: FakeSession, **attribute_changes: Any
) -> tuple[SalusDataCoordinator, list[float]]:
    """Return coordinator after its first update and the clock shared with its device."""

    clock = [0.0]
    device = await create_device(session, clock=lambda: clock[0], **attribute_changes)
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    coordinator = SalusDataCoordinator(hass, create_entry(), device, clock=lambda: clock[0])
    coordinator.data = await coordinator._async_update_data()
    return coordinator, clock


def attach[EntityT](entity: EntityT) -> EntityT:
    """Return entity able to write its state without running Home Assistant."""

    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity

"""Support for Salus iT500 water heater devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SalusConfigEntry, SalusDataCoordinator
from .entity import SalusEntity
from .pyit500.device import SystemType
from .pyit500.hotwaterzone import HotWaterZone
from .pyit500.hotwaterzone import Mode as HotWaterMode

# Operation modes
OPERATION_AUTO = "auto"
OPERATION_ONCE = "boost"
OPERATION_ON = "on"
OPERATION_OFF = "off"

OPERATION_LIST = [OPERATION_AUTO, OPERATION_ONCE, OPERATION_ON, OPERATION_OFF]

# Mapping between HA operation modes and Salus modes
OPERATION_TO_SALUS = {
    OPERATION_AUTO: HotWaterMode.AUTO,
    OPERATION_ONCE: HotWaterMode.ONCE,
    OPERATION_ON: HotWaterMode.ON,
    OPERATION_OFF: HotWaterMode.OFF,
}

SALUS_TO_OPERATION = {
    HotWaterMode.AUTO: OPERATION_AUTO,
    HotWaterMode.ONCE: OPERATION_ONCE,
    HotWaterMode.ON: OPERATION_ON,
    HotWaterMode.OFF: OPERATION_OFF,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Salus water heater entities from a config entry."""
    coordinator = entry.runtime_data

    # Only add hot water if system supports it
    if coordinator.device.system_type == SystemType.CH1_HOT_WATER:
        async_add_entities([SalusWaterHeater(coordinator)])


class SalusWaterHeater(SalusEntity, WaterHeaterEntity):
    """Representation of a Salus hot water heater."""

    _attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE
    _attr_temperature_unit = None  # Water heater doesn't use temperature
    _attr_operation_list = OPERATION_LIST
    _attr_min_temp = None
    _attr_max_temp = None
    _attr_name = "Teplá voda"
    _attr_translation_key = "hot_water"

    def __init__(self, coordinator: SalusDataCoordinator) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}_hw_water_heater"

    @property
    def _zone(self) -> HotWaterZone:
        """Return the hot water zone."""
        return self.coordinator.device.hw

    @property
    def current_operation(self) -> str | None:
        """Return current operation mode."""
        mode = self._zone.mode
        return SALUS_TO_OPERATION.get(mode)

    @property
    def state(self) -> str:
        """Return the current state based on operation mode."""
        # State should reflect operation mode, not just on/off status
        # This fixes the issue where "auto" mode shows as "on"
        operation = self.current_operation
        if operation == OPERATION_OFF:
            return STATE_OFF
        # For all other modes (auto, boost, on), return on
        return STATE_ON

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        salus_mode = OPERATION_TO_SALUS[operation_mode]
        await self.coordinator.async_send_command(lambda: self._zone.async_set_mode(salus_mode))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the water heater."""
        await self.async_set_operation_mode(OPERATION_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the water heater."""
        await self.async_set_operation_mode(OPERATION_OFF)

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        attrs = {
            "schedule_type": self._zone.schedule_type.friendly_name,
            "running_mode": self._zone.running_mode.friendly_name,
        }

        # Add boost remaining hours if in boost mode
        if self._zone.mode == HotWaterMode.ONCE:
            attrs["boost_remaining_hours"] = self._zone.boost_remaining_hours

        return attrs

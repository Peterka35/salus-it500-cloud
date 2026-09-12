"""Support for Salus iT500 climate devices."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import SalusConfigEntry, SalusDataCoordinator
from .entity import SalusEntity
from .portal import PortalSchedule, SalusPortal, Slot
from .pyit500.device import SystemType, TemperatureUnit
from .pyit500.heatingzone import ConsolidatedMode, HeatingZone
from .pyit500.zone import OnOffStatus, Prefix

# Preset modes mapping to ConsolidatedMode
PRESET_AUTO = "auto"
PRESET_MANUAL = "manual"
PRESET_TEMP_HOLD = "temp_hold"

PRESET_MODES = [PRESET_AUTO, PRESET_MANUAL, PRESET_TEMP_HOLD]

# Mapping between HA HVAC modes and Salus modes
HVAC_MODE_TO_SALUS = {
    HVACMode.OFF: ConsolidatedMode.OFF,
    HVACMode.HEAT: ConsolidatedMode.AUTO,
}

SALUS_MODE_TO_HVAC = {
    ConsolidatedMode.OFF: HVACMode.OFF,
    ConsolidatedMode.AUTO: HVACMode.HEAT,
    ConsolidatedMode.MANUAL: HVACMode.HEAT,
    ConsolidatedMode.TEMP_HOLD: HVACMode.HEAT,
}

SALUS_MODE_TO_PRESET = {
    ConsolidatedMode.AUTO: PRESET_AUTO,
    ConsolidatedMode.MANUAL: PRESET_MANUAL,
    ConsolidatedMode.TEMP_HOLD: PRESET_TEMP_HOLD,
}

PRESET_TO_SALUS_MODE = {
    PRESET_AUTO: ConsolidatedMode.AUTO,
    PRESET_MANUAL: ConsolidatedMode.MANUAL,
    PRESET_TEMP_HOLD: ConsolidatedMode.TEMP_HOLD,
}

ZONE_NAMES = {
    Prefix.CH1: "Heating Zone 1",
    Prefix.CH2: "Heating Zone 2",
}


SERVICE_GET_SCHEDULE = "get_schedule"
SERVICE_SET_SCHEDULE = "set_schedule"
ATTR_SLOTS = "slots"

SLOT_SCHEMA = vol.Schema(
    {
        vol.Required("time"): cv.time,
        vol.Required("temperature"): vol.All(vol.Coerce(float), vol.Range(min=5, max=35)),
    }
)
# One to six, matching every other slot-count contract in this system. The portal's own limit - it
# keeps steps it does not overwrite, so only a full day can be verified - is enforced in portal.py,
# where it belongs, and arrives as a HomeAssistantError rather than a schema rejection.
SET_SCHEDULE_SCHEMA = {vol.Required(ATTR_SLOTS): vol.All(cv.ensure_list, vol.Length(min=1, max=6), [SLOT_SCHEMA])}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SalusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Salus climate entities from a config entry."""
    coordinator = entry.runtime_data

    # Always add CH1 (primary heating zone)
    entities = [SalusThermostat(coordinator, Prefix.CH1)]

    # Add CH2 if system supports it
    if coordinator.device.system_type == SystemType.CH1_CH2:
        entities.append(SalusThermostat(coordinator, Prefix.CH2))

    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_GET_SCHEDULE, None, "async_get_schedule", supports_response=SupportsResponse.ONLY
    )
    platform.async_register_entity_service(SERVICE_SET_SCHEDULE, SET_SCHEDULE_SCHEMA, "async_set_schedule")


class SalusThermostat(SalusEntity, ClimateEntity):
    """Representation of a Salus thermostat."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = PRESET_MODES
    _attr_target_temperature_step = 0.5
    _attr_translation_key = "thermostat"

    def __init__(self, coordinator: SalusDataCoordinator, zone_prefix: Prefix) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._zone_prefix = zone_prefix

        # Set temperature unit based on device configuration
        if coordinator.device.temperature_unit == TemperatureUnit.FAHRENHEIT:
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        self._attr_name = ZONE_NAMES[zone_prefix]
        self._attr_unique_id = f"{coordinator.device.device_id}_{zone_prefix.value}_climate"

    @property
    def _zone(self) -> HeatingZone:
        """Return the heating zone for this thermostat."""
        if self._zone_prefix == Prefix.CH1:
            return self.coordinator.device.ch1
        return self.coordinator.device.ch2

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._zone.current_room_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._zone.current_setpoint

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation mode."""
        mode = self._zone.consolidated_mode
        return SALUS_MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        if self._zone.relay_status == OnOffStatus.ON:
            return HVACAction.HEATING
        if self._zone.consolidated_mode == ConsolidatedMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        mode = self._zone.consolidated_mode
        return SALUS_MODE_TO_PRESET.get(mode)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 41.0  # 5°C in Fahrenheit
        return 5.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 94.0  # 34.5°C ≈ 94°F
        return 34.5

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.async_send_command(lambda: self._zone.async_set_current_setpoint(temperature))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        salus_mode = HVAC_MODE_TO_SALUS[hvac_mode]
        await self.coordinator.async_send_command(lambda: self._zone.async_set_consolidated_mode(salus_mode))

    async def async_turn_on(self) -> None:
        """Turn on following the schedule; a thermostat already heating keeps its mode."""
        if self.hvac_mode == HVACMode.OFF:
            await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        salus_mode = PRESET_TO_SALUS_MODE[preset_mode]
        await self.coordinator.async_send_command(lambda: self._zone.async_set_consolidated_mode(salus_mode))

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "frost_active": self._zone.frost_active.friendly_name,
            "schedule_type": self._zone.schedule_type.friendly_name,
        }

    # Weekly program -------------------------------------------------------

    def _require_portal(self) -> SalusPortal:
        """Return the portal client, refusing zones whose program cannot be reached.

        Only the first heating zone is covered: the portal's second-zone and hot-water blocks were
        never observed, and writing an unverified block shape into an occupied apartment is not a
        guess worth making.
        """

        if self._zone_prefix != Prefix.CH1:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="schedule_zone_unsupported")
        if self.coordinator.portal is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="schedule_unavailable")
        return self.coordinator.portal

    async def async_get_schedule(self) -> ServiceResponse:
        """Return the weekly program the thermostat is running."""

        schedule = await self.coordinator.async_run(self._require_portal().async_read)
        return _response(schedule)

    async def async_set_schedule(self, slots: list[dict[str, Any]]) -> None:
        """Write one daily program to the whole week and confirm the thermostat took it."""

        portal = self._require_portal()
        program = [Slot(str(slot["time"])[:5], float(slot["temperature"])) for slot in slots]
        await self.coordinator.async_run(lambda: portal.async_write(program))


def _response(schedule: PortalSchedule) -> ServiceResponse:
    return {
        "device_id": schedule.device_id,
        "schedule_type": schedule.schedule_type,
        "writable": schedule.writable,
        "days": {
            day: [{"time": slot.time, "temperature": slot.temperature} for slot in slots]
            for day, slots in schedule.days.items()
        },
    }

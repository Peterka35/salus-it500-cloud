"""Base entity for the Salus iT500 integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SalusDataCoordinator


class SalusEntity(CoordinatorEntity[SalusDataCoordinator]):
    """Entity of a Salus iT500 thermostat."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SalusDataCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device.device_id))},
            manufacturer="Salus",
            model="iT500",
            name=device.description or "Salus iT500",
        )

    @property
    def available(self) -> bool:
        """Unavailable while the thermostat is offline: the API keeps serving its last values."""
        return super().available and not self.coordinator.device_offline

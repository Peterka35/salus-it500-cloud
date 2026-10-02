"""Module to provide the Device class"""

import time
from collections.abc import Callable
from typing import Any

from .auth import Auth
from .enumfriendly import EnumFriendly, IntEnumFriendly
from .exceptions import SalusCommandError, SalusConnectionError
from .heatingzone import HeatingZone
from .hotwaterzone import HotWaterZone
from .parsing import parse_response
from .zone import OnOffStatus, Prefix

# Salus API reports commanded values after 10-30 seconds
PENDING_VALUE_SECONDS = 60


class SystemAttribute(EnumFriendly):
    """Enum for system wide (rather than Zone) Device attribute names."""

    OTA_STATUS = "S00"
    ENERGY_SAVE_STATUS = "S01"
    UPGRADE_AVAILABLE = "S02"
    BATTERY_STATUS = "S03"
    TIME_ZONE = "S04"
    SYSTEM_MODE = "S05"
    SYSTEM_TYPE = "S06"
    TEMPERATURE_UNIT = "S07"
    HOUR_FORMAT = "S08"
    FROST_TEMPERATURE = "S09"
    HOLIDAY_OPTION = "S10"
    HOLIDAY_START = "S11"
    HOLIDAY_END = "S12"
    THERMOSTAT_MICROPROCESSOR_VERSION = "S13"
    DAYLIGHT_SAVING_TIME = "S14"
    SPAN = "S15"
    DISPLAY_TOLERANCE = "S16"
    DISPLAY_OFFSET = "S17"
    CH2_DISPLAY_OFFSET = "S18"
    DELAY_START_ENABLE = "S19"
    DESCRIPTION = "desc"


class SystemType(IntEnumFriendly):
    """Enum for Device System Type."""

    CH1 = 0
    CH1_CH2 = 1
    CH1_HOT_WATER = 2


class TemperatureUnit(IntEnumFriendly):
    """Enum for Temperature Unit."""

    CELSIUS = 0
    FAHRENHEIT = 1


def _api_value(value: Any) -> str:
    """Return attribute value as sent to and reported by the API."""
    return str(int(value)) if isinstance(value, int) else str(value)


class Device:
    """Class that represents a Device object in the Salus iT500 API."""

    # Constructor
    def __init__(
        self,
        device_id: int,
        raw_data: dict,
        auth: Auth,
        clock: Callable[[], float] = time.monotonic,
    ):
        """Initialise a device object."""
        self._device_id = int(device_id)
        self.raw_data = raw_data
        self.auth = auth
        self._clock = clock
        # Commanded attribute values the API does not report yet: name -> (value, expiry)
        self._pending: dict[str, tuple[str, float]] = {}
        self.ch1 = HeatingZone(self, Prefix.CH1)
        self.ch2 = HeatingZone(self, Prefix.CH2)
        self.hw = HotWaterZone(self, Prefix.HW)

    # Device Class Methods
    @classmethod
    async def async_get_device(cls, auth, device_id) -> "Device":
        """Return a device."""
        device = Device(device_id, None, auth)
        await device.async_update()
        return device

    # Properties
    @property
    def device_id(self) -> int:
        """Return the ID of the device."""
        return self._device_id

    @property
    def system_type(self) -> SystemType:
        """Return the system type.
        (0 = CH1, 1 = CH1+CH2, 2 = CH1 + Hot Water)"""
        return SystemType(int(self.get_attr(SystemAttribute.SYSTEM_TYPE)))

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Return the temperature unit.
        (0 = Celsius, 1 = Fahrenheit)"""
        return TemperatureUnit(int(self.get_attr(SystemAttribute.TEMPERATURE_UNIT)))

    @property
    def frost_temperature(self) -> float:
        """Return the set frost temperature, in C."""
        return int(self.get_attr(SystemAttribute.FROST_TEMPERATURE)) / 100

    @property
    def holiday_option(self) -> OnOffStatus:
        """Return the Holiday option status."""
        return OnOffStatus(int(self.get_attr(SystemAttribute.HOLIDAY_OPTION)))

    async def async_set_holiday_option(self, value: OnOffStatus):
        """Set the Holiday option status."""
        return await self.async_set_attr(SystemAttribute.HOLIDAY_OPTION, value)

    @property
    def holiday_start(self) -> str:
        """Return the Holiday start date & time, as string (YYYYMMDDHHMM)."""
        return str(self.get_attr(SystemAttribute.HOLIDAY_START))

    async def async_set_holiday_start(self, value: str):
        """Set the Holiday start date & time, as string (YYYYMMDDHHMM)."""
        return await self.async_set_attr(SystemAttribute.HOLIDAY_START, value)

    @property
    def holiday_end(self) -> str:
        """Return the Holiday end date & time, as string."""
        return str(self.get_attr(SystemAttribute.HOLIDAY_END))

    async def async_set_holiday_end(self, value: str):
        """Set the Holiday end date & time, as string (YYYYMMDDHHMM)."""
        return await self.async_set_attr(SystemAttribute.HOLIDAY_END, value)

    @property
    def description(self) -> str:
        """Return the description of the system."""
        return str(self.get_attr(SystemAttribute.DESCRIPTION))

    def get_attr(self, attr: SystemAttribute) -> Any:
        """Return the value of an attribute in the System, based on the Device raw data."""
        return self.get_raw_attr(attr.value)

    async def async_set_attr(
        self,
        attr: SystemAttribute,
        attr_value: Any,
    ) -> int:
        """Sets an attribute for the system."""
        return await self.async_control(attr.value, attr_value)

    def get_raw_attr(self, attr) -> Any:
        """Return the value of an attribute in the Device raw data.
        A recently commanded value is returned until the API reports it."""
        pending = self._pending.get(attr)
        if pending is not None and self._clock() < pending[1]:
            return pending[0]
        return self.raw_data["attrList:" + attr]["value"]

    async def async_control(
        self,
        attr1_name: str,
        attr1_value: Any,
        attr2_name: str | None = None,
        attr2_value: Any = None,
        attr3_name: str | None = None,
        attr3_value: Any = None,
    ) -> int:
        """Control the device.
        Raises SalusCommandError when the API does not accept the command."""
        values = {attr1_name: _api_value(attr1_value)}
        if attr2_name is not None:
            values[attr2_name] = _api_value(attr2_value)
        if attr3_name is not None:
            values[attr3_name] = _api_value(attr3_value)

        params = {"devId": self.device_id}
        for index, (name, value) in enumerate(values.items(), start=1):
            params[f"name{index}"] = name
            params[f"value{index}"] = value

        response = parse_response(
            await self.auth.request("get", "setMultiDeviceAttributes2", params=params),
            "ns1:setMultiDeviceAttributes2Response",
        )
        try:
            ret_code = int(response["retCode"])
        except (KeyError, TypeError, ValueError) as err:
            raise SalusConnectionError("Unexpected Salus API response to a command") from err
        if ret_code != 0:
            raise SalusCommandError(f"Salus API rejected the command (retCode {ret_code})")

        expiry = self._clock() + PENDING_VALUE_SECONDS
        self._pending.update({name: (value, expiry) for name, value in values.items()})
        return ret_code

    async def async_update(self):
        """Update the device data."""
        raw_data = parse_response(
            await self.auth.request("post", "getDeviceAttributesWithValues", data={"devId": self.device_id}),
            "ns1:getDeviceAttributesWithValuesResponse",
            postprocessor=Device.xml_postprocessor,
        )
        if not isinstance(raw_data, dict):
            raise SalusConnectionError("Salus API returned no device attributes")
        self.raw_data = raw_data

        now = self._clock()
        self._pending = {
            name: (value, expiry)
            for name, (value, expiry) in self._pending.items()
            if now < expiry and (raw_data.get("attrList:" + name) or {}).get("value") != value
        }

    @property
    def reported_at(self) -> float | None:
        """When the device last uploaded its values, in epoch seconds, or None if the API did not say.

        The API stamps every attribute with `updTime` in milliseconds when the gateway uploads it, and
        the gateway uploads an attribute only when it changes."""
        times = [
            int(item["updTime"])
            for key, item in (self.raw_data or {}).items()
            if key.startswith("attrList:") and isinstance(item, dict) and str(item.get("updTime", "")).isdigit()
        ]
        return max(times) / 1000 if times else None

    @property
    def connected(self) -> bool | None:
        """Whether the cloud says the gateway is connected (`presenceInfo`), or None if it did not say."""
        presence = str((self.raw_data or {}).get("presenceInfo", ""))
        return {"1": True, "0": False}.get(presence)

    @staticmethod
    def xml_postprocessor(_path, key, value) -> tuple:
        """Called by xmltodict. Extracts the configurations and attrList key/value pairs."""
        if key == "configurations":
            return "configurations:" + value["property"], value
        if key == "attrList":
            return "attrList:" + value["name"], value
        return key, value

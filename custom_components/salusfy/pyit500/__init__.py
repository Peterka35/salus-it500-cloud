"""PyIt500 library for Salus iT500 API."""

from .auth import Auth
from .device import Device, SystemAttribute, SystemType
from .devicelistitem import DeviceListItem
from .exceptions import InvalidAuth, SalusCommandError, SalusConnectionError, SalusError
from .heatingzone import AutoTempHoldMode, ConsolidatedMode, HeatingZone
from .hotwaterzone import HotWaterZone
from .hotwaterzone import Mode as HotWaterMode
from .hotwaterzone import RunningMode as HotWaterRunningMode
from .pyit500 import PyIt500
from .user import User
from .zone import ActiveStatus, OnOffStatus, Prefix, ScheduleType, ZoneAttribute

__all__ = [
    "ActiveStatus",
    "Auth",
    "AutoTempHoldMode",
    "ConsolidatedMode",
    "Device",
    "DeviceListItem",
    "HeatingZone",
    "HotWaterMode",
    "HotWaterRunningMode",
    "HotWaterZone",
    "InvalidAuth",
    "OnOffStatus",
    "Prefix",
    "PyIt500",
    "SalusCommandError",
    "SalusConnectionError",
    "SalusError",
    "ScheduleType",
    "SystemAttribute",
    "SystemType",
    "User",
    "ZoneAttribute",
]

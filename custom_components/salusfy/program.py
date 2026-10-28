"""Weekly heating programs through the Salus iT500 mobile API.

The program of the first heating zone is the day attributes A00 (Monday) to A06 (Sunday), each six
steps of four characters; a character carries a number as `chr(48 + n)`: hour, minute, whole
degrees and the tenth. `5NF0` is 05:30 at 22.0 °C. A86 is the schedule type the thermostat runs.
Decoded on 2026-10-28 from all six thermostats against the programs the web portal had shown, after
Salus switched the portal (salus-it500.com) off on 2026-10-22.

The cloud keeps every day separately, also on a thermostat set to 5/2: writing Monday left Tuesday
as it was. So a program is always written to all seven days, which is what "one program for the
whole week" means whatever the thermostat's schedule type, and every day is read back.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from aiohttp import ClientTimeout

from .pyit500.auth import Auth
from .pyit500.device import Device
from .pyit500.exceptions import SalusConnectionError, SalusError
from .pyit500.parsing import parse_response

_LOGGER = logging.getLogger(__name__)

DAYS = ("mon", "tus", "wed", "thu", "fri", "sat", "sun")
DAY_ATTRIBUTES = tuple(f"A0{index}" for index in range(len(DAYS)))
SCHEDULE_TYPE_ATTRIBUTE = "A86"

SCHEDULE_ALL = "all"
SCHEDULE_WEEKDAY_WEEKEND = "weekday_weekend"
SCHEDULE_PER_DAY = "per_day"
SCHEDULE_TYPES = {"0": SCHEDULE_ALL, "1": SCHEDULE_WEEKDAY_WEEKEND, "2": SCHEDULE_PER_DAY}

SLOTS_PER_DAY = 6
CHARACTER_OFFSET = 48
# A command that changes the program is answered only after the thermostat took it: on 2026-10-28
# both rewrites outlasted the usual 20 s and still landed. Waiting longer, and then reading back
# rather than sending again, is what tells a slow success from a failure.
WRITE_TIMEOUT = ClientTimeout(total=60)
# The cloud showed a write within 10 s; reading back until it matches costs nothing when it is quick
SETTLE_SECONDS = 6
CONFIRM_ATTEMPTS = 10


class ProgramError(SalusError):
    """The weekly program could not be read or written."""


@dataclass(frozen=True, slots=True)
class Slot:
    """One step of a daily program."""

    time: str
    temperature: float


@dataclass(frozen=True, slots=True)
class WeeklyProgram:
    """The weekly program of one thermostat."""

    device_id: str
    schedule_type: str
    days: dict[str, tuple[Slot, ...]]

    @property
    def writable(self) -> bool:
        # All seven days are written, so the program lands whatever the schedule type
        return True


def decode_day(value: str | None) -> tuple[Slot, ...]:
    """Return the steps of one day attribute."""

    text = value or ""
    if len(text) != SLOTS_PER_DAY * 4:
        raise ProgramError(f"Unreadable daily program of {len(text)} characters")
    numbers = [ord(character) - CHARACTER_OFFSET for character in text]
    slots = []
    for index in range(0, len(numbers), 4):
        hour, minute, degrees, tenth = numbers[index : index + 4]
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= degrees <= 99 and 0 <= tenth <= 9):
            raise ProgramError("Unreadable daily program")
        slots.append(Slot(f"{hour:02d}:{minute:02d}", degrees + tenth / 10))
    return tuple(slots)


def encode_day(slots: Sequence[Slot]) -> str:
    """Return the day attribute value of a full day's steps."""

    if len(slots) != SLOTS_PER_DAY:
        # The thermostat always runs six steps a day; a shorter program has no encoding
        raise ProgramError(f"A daily program takes {SLOTS_PER_DAY} steps, got {len(slots)}")
    text = ""
    for slot in slots:
        hour, minute = (int(part) for part in slot.time.split(":")[:2])
        tenths = round(slot.temperature * 10)
        if tenths % 5:
            raise ProgramError(f"{slot.temperature} °C is not a step of the thermostat (0.5 °C)")
        degrees, tenth = divmod(tenths, 10)
        text += "".join(chr(CHARACTER_OFFSET + number) for number in (hour, minute, degrees, tenth))
    return text


class SalusProgram:
    """Reads and writes the weekly program of one thermostat."""

    def __init__(
        self, auth: Auth, device_id: int | str, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    ) -> None:
        self._auth = auth
        self._device_id = str(device_id)
        self._sleep = sleep

    async def async_read(self) -> WeeklyProgram:
        """Return the weekly program the thermostat is running."""

        raw = parse_response(
            await self._auth.request("post", "getDeviceAttributesWithValues", data={"devId": self._device_id}),
            "ns1:getDeviceAttributesWithValuesResponse",
            postprocessor=Device.xml_postprocessor,
        )
        if not isinstance(raw, dict):
            raise ProgramError("Salus API returned no device attributes")

        def value(name: str) -> str | None:
            item = raw.get("attrList:" + name)
            return item.get("value") if isinstance(item, dict) else None

        days = {day: decode_day(value(attribute)) for day, attribute in zip(DAYS, DAY_ATTRIBUTES, strict=True)}
        schedule_type = SCHEDULE_TYPES.get(str(value(SCHEDULE_TYPE_ATTRIBUTE)), "")
        return WeeklyProgram(self._device_id, schedule_type, days)

    async def async_write(self, slots: Sequence[Slot]) -> WeeklyProgram:
        """Write one program to every day of the week and prove the thermostat took it."""

        encoded = encode_day(slots)
        params: dict[str, str] = {"devId": self._device_id}
        for index, attribute in enumerate(DAY_ATTRIBUTES, start=1):
            params[f"name{index}"] = attribute
            params[f"value{index}"] = encoded
        try:
            text = await self._auth.request(
                "get", "setMultiDeviceAttributes2", params=params, client_timeout=WRITE_TIMEOUT, retry=False
            )
        except SalusConnectionError as err:
            # No answer is not a refusal: the program is read back below and that decides
            _LOGGER.debug("Salus API did not answer the program command (%s), reading it back", err)
        else:
            response = parse_response(text, "ns1:setMultiDeviceAttributes2Response")
            if str((response or {}).get("retCode")) != "0":
                raise ProgramError(f"Salus API rejected the program (retCode {(response or {}).get('retCode')})")

        expected = tuple(slots)
        differing: list[str] = []
        for _ in range(CONFIRM_ATTEMPTS):
            await self._sleep(SETTLE_SECONDS)
            written = await self.async_read()
            differing = [day for day, actual in written.days.items() if actual != expected]
            if not differing:
                return written
        waited = CONFIRM_ATTEMPTS * SETTLE_SECONDS
        raise ProgramError(f"Salus accepted the program but {', '.join(differing)} did not change within {waited} s")

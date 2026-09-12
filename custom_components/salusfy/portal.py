"""Weekly heating programs through the salus-it500.com web portal.

The mobile API the rest of this integration speaks has no notion of a weekly program: it carries the
day attributes A00..A06 as an undocumented proprietary string that nothing here can decode. The web
portal serves the same program as plain JSON and accepts it back, using the very credentials the
config entry already holds, so this is a second API surface rather than a second integration.

Endpoints and payload shapes observed from real traffic on 2026-09-12:

    login   POST /public/login.php?lang=cs        IDemail, password, login, keep_logged_in
    devices GET  /public/devices.php              devId of every thermostat on the account
    token   GET  /public/control.php?devId=..     a per-page token every other call needs
    read    GET  /public/ajax_device_values.php   JSON, z1p<Day><n>Time / ..Temp, CH1schedType
    write   POST /includes/program.php            token, tempUnit, devId, <block>set, <block><n>time/temp

Credentials and tokens are never logged, and no request body is ever logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .pyit500.exceptions import InvalidAuth, SalusConnectionError, SalusError

_LOGGER = logging.getLogger(__name__)

BASE = "https://salus-it500.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
)
READ_TIMEOUT = 60
WRITE_TIMEOUT = 90
# The portal applies a write asynchronously, so the program is read back until it matches rather
# than once after a fixed wait. An iT600 thermostat was seen taking 25 s to report a write it had
# applied, and reporting that success as a failure invites an operator to write it all over again.
SETTLE_SECONDS = 6
CONFIRM_ATTEMPTS = 10
# A device set to 5/2 or to single days needs its blocks written separately, with a pause between
BLOCK_PAUSE_SECONDS = 2
SLOTS_PER_DAY = 6

# The portal's own spelling of the days, "Tus" included
DAYS = ("Mon", "Tus", "Wed", "Thu", "Fri", "Sat", "Sun")

SCHEDULE_ALL = "all"
SCHEDULE_WEEKDAY_WEEKEND = "weekday_weekend"
SCHEDULE_PER_DAY = "per_day"
# CH1schedType as the portal reports it
SCHEDULE_TYPES = {"0": SCHEDULE_ALL, "1": SCHEDULE_WEEKDAY_WEEKEND, "2": SCHEDULE_PER_DAY}
WRITE_BLOCKS = {
    SCHEDULE_ALL: ("z1pAll",),
    SCHEDULE_WEEKDAY_WEEKEND: ("z1pMon_fri", "z1pSat_sun"),
    SCHEDULE_PER_DAY: tuple(f"z1p{day.lower()}" for day in DAYS),
}

TOKEN_PATTERN = re.compile(r'(?:id|name)="token"[^>]*value="([^"]+)"')
DEVICE_PATTERN = re.compile(r"devId=(\d+)")


class PortalError(SalusError):
    """The Salus web portal could not be used."""


@dataclass(frozen=True, slots=True)
class Slot:
    """One step of a daily program."""

    time: str
    temperature: float


@dataclass(frozen=True, slots=True)
class PortalSchedule:
    """The weekly program of one thermostat as the portal reports it."""

    device_id: str
    schedule_type: str
    days: dict[str, tuple[Slot, ...]]

    @property
    def writable(self) -> bool:
        return self.schedule_type in WRITE_BLOCKS


def parse_temperature(value: Any) -> float | None:
    """Return the temperature of a portal field, which arrives as '22.0 °C' and sometimes as '?'."""

    text = str(value).replace("°C", "").replace(",", ".").strip()
    try:
        return float(text)
    except ValueError:
        return None


def parse_time(value: Any) -> str | None:
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", text):
        return None
    hours, minutes = text.split(":")
    return f"{int(hours):02d}:{minutes}"


class SalusPortal:
    """One signed-in portal session for one account, which owns exactly one thermostat."""

    def __init__(
        self,
        session: Any,
        username: str,
        password: str,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._sleep = sleep
        self._device_id: str | None = None

    # Requests ------------------------------------------------------------

    async def _async_request(self, method: str, path: str, headers: dict[str, str] | None = None, **kwargs: Any) -> str:
        url = f"{BASE}{path}"
        try:
            response = await self._session.request(
                method, url, headers={"User-Agent": USER_AGENT, **(headers or {})}, **kwargs
            )
        except Exception as err:  # aiohttp raises several unrelated error types
            raise SalusConnectionError(f"Salus portal could not be reached: {type(err).__name__}") from err
        if response.status != 200:
            raise SalusConnectionError(f"Salus portal answered {response.status} for {path}")
        return await response.text()

    async def _async_login(self) -> None:
        """Sign in; the session cookie the portal sets carries every later request."""

        page = await self._async_request(
            "post",
            "/public/login.php",
            params={"lang": "cs"},
            data={
                "IDemail": self._username,
                "password": self._password,
                "login": "Přihlásit",
                "keep_logged_in": "1",
            },
            timeout=READ_TIMEOUT,
        )
        if "login_form" in page and "devices.php" not in page:
            raise InvalidAuth("Salus portal rejected the stored credentials")

    async def _async_discover(self) -> str:
        """Return the account's thermostat.

        The config entry stores only a username and a password, so there is no device id to pass
        through from the mobile API and the portal's own listing is the only source.
        """

        page = await self._async_request("get", "/public/devices.php", timeout=READ_TIMEOUT)
        found = list(dict.fromkeys(DEVICE_PATTERN.findall(page)))
        if not found:
            raise PortalError("Salus portal lists no thermostat on this account")
        if len(found) > 1:
            _LOGGER.warning("Salus portal lists %d thermostats, using the first", len(found))
        return found[0]

    async def _async_token(self, device_id: str) -> str | None:
        page = await self._async_request(
            "get", "/public/control.php", params={"devId": device_id}, timeout=READ_TIMEOUT
        )
        match = TOKEN_PATTERN.search(page)
        return match.group(1) if match else None

    async def _async_prepare(self) -> tuple[str, str]:
        """Return the device and a fresh token, signing in again once if the session has expired."""

        for attempt in (1, 2):
            if self._device_id is None:
                await self._async_login()
                self._device_id = await self._async_discover()
            token = await self._async_token(self._device_id)
            if token is not None:
                return self._device_id, token
            # No token on the control page means the portal signed us out
            self._device_id = None
            if attempt == 2:
                raise PortalError("Salus portal did not return a token after signing in again")
        raise PortalError("Salus portal did not return a token")

    async def _async_values(self, device_id: str, token: str) -> dict[str, Any]:
        text = await self._async_request(
            "get",
            "/public/ajax_device_values.php",
            params={"devId": device_id, "token": token, "_": int(time.time() * 1000)},
            timeout=READ_TIMEOUT,
        )
        try:
            values = json.loads(text)
        except ValueError as err:
            raise PortalError("Salus portal returned an unreadable program") from err
        if not isinstance(values, dict):
            raise PortalError("Salus portal returned an unreadable program")
        return values

    # Reading and writing --------------------------------------------------

    async def async_read(self) -> PortalSchedule:
        """Return the weekly program the thermostat is running."""

        device_id, token = await self._async_prepare()
        return self._schedule(device_id, await self._async_values(device_id, token))

    @staticmethod
    def _schedule(device_id: str, values: dict[str, Any]) -> PortalSchedule:
        days: dict[str, tuple[Slot, ...]] = {}
        for day in DAYS:
            block = values.get(f"z1p{day}") or {}
            slots = []
            for index in range(1, SLOTS_PER_DAY + 1):
                moment = parse_time(block.get(f"z1p{day}{index}Time", ""))
                temperature = parse_temperature(block.get(f"z1p{day}{index}Temp", ""))
                if moment is not None and temperature is not None:
                    slots.append(Slot(moment, temperature))
            days[day.lower()] = tuple(slots)
        # Not defaulted to "all days": posting the all-days block to a device in 5/2 mode is the
        # HTTP-200 no-op that changes nothing, and refusing beats a best-effort write
        schedule_type = SCHEDULE_TYPES.get(str(values.get("CH1schedType", "")), "")
        return PortalSchedule(device_id, schedule_type, days)

    async def async_write(self, slots: Sequence[Slot]) -> PortalSchedule:
        """Write one program to every day of the week and prove the thermostat took it.

        A write that does not match the mode the thermostat is actually in comes back HTTP 200 and
        changes nothing, so reading the program back is the only way to know it landed.
        """

        if len(slots) != SLOTS_PER_DAY:
            # The portal keeps whatever steps are not overwritten, and there is no observed way to
            # clear one, so a shorter program would leave the old tail behind and never verify.
            # Refusing up front beats failing after the write with a confusing mismatch.
            raise PortalError(f"The portal only takes a full program of {SLOTS_PER_DAY} steps, got {len(slots)}")
        device_id, token = await self._async_prepare()
        current = self._schedule(device_id, await self._async_values(device_id, token))
        blocks = WRITE_BLOCKS.get(current.schedule_type)
        if blocks is None:
            raise PortalError(f"Unknown schedule type of {device_id}, refusing to write")

        for index, block in enumerate(blocks):
            if index:
                await self._sleep(BLOCK_PAUSE_SECONDS)
            await self._async_write_block(device_id, token, block, slots)

        expected = tuple(slots)
        differing: list[str] = []
        for _ in range(CONFIRM_ATTEMPTS):
            await self._sleep(SETTLE_SECONDS)
            written = self._schedule(device_id, await self._async_values(device_id, token))
            differing = [day for day, actual in written.days.items() if actual != expected]
            if not differing:
                return written
        waited = CONFIRM_ATTEMPTS * SETTLE_SECONDS
        raise PortalError(
            f"Salus portal accepted the program but {', '.join(differing)} did not change within {waited} s"
        )

    async def _async_write_block(self, device_id: str, token: str, block: str, slots: Sequence[Slot]) -> None:
        body: dict[str, Any] = {"token": token, "tempUnit": "0", "devId": device_id, f"{block}set": "1"}
        for index, slot in enumerate(slots, start=1):
            body[f"{block}{index}time"] = slot.time
            body[f"{block}{index}temp"] = f"{slot.temperature:.1f} °C"
        await self._async_request(
            "post",
            "/includes/program.php",
            data=body,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/public/control.php?devId={device_id}"},
            timeout=WRITE_TIMEOUT,
        )

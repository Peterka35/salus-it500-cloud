"""Tests of the weekly program client for the salus-it500.com web portal."""

import json
import logging
from typing import Any

import pytest

from custom_components.salusfy.portal import (
    DAYS,
    SCHEDULE_ALL,
    SCHEDULE_PER_DAY,
    SCHEDULE_WEEKDAY_WEEKEND,
    PortalError,
    SalusPortal,
    Slot,
)
from custom_components.salusfy.pyit500.exceptions import InvalidAuth, SalusConnectionError

from . import fixtures
from .helpers import FakeResponse, FakeSession

DEVICE_ID = "201300001"
TOKEN = "portal-token-0001"
PLAN = (
    Slot("05:30", 22.0),
    Slot("09:00", 18.0),
    Slot("14:00", 21.0),
    Slot("16:00", 22.0),
    Slot("22:00", 20.0),
    Slot("23:00", 19.0),
)
OTHER = (Slot("07:00", 18.0), Slot("22:00", 16.0))

LOGGED_IN = FakeResponse(200, text="<html><a href='devices.php'>Zařízení</a></html>")
REJECTED = FakeResponse(200, text="<html><form id='login_form'></form></html>")
DEVICES = FakeResponse(200, text=f"<a href='control.php?devId={DEVICE_ID}'>Apartmán A</a>")
CONTROL = FakeResponse(200, text=f'<input id="token" value="{TOKEN}">')
SIGNED_OUT = FakeResponse(200, text="<html><form id='login_form'></form></html>")
WRITTEN = FakeResponse(200, text="OK")


def values(slots: tuple[Slot, ...] = PLAN, sched_type: str = "0", **changes: Any) -> FakeResponse:
    """Portal values payload with the same program on every day, shaped like the real response."""

    payload: dict[str, Any] = {"CH1schedType": sched_type, "CH1currentRoomTemp": "21.5"}
    for day in DAYS:
        block = {}
        for index in range(1, 7):
            slot = slots[index - 1] if index <= len(slots) else None
            block[f"z1p{day}{index}Time"] = slot.time if slot else "?"
            block[f"z1p{day}{index}Temp"] = f"{slot.temperature} °C" if slot else "?"
        payload[f"z1p{day}"] = block
    payload.update(changes)
    return FakeResponse(200, text=json.dumps(payload))


def portal(session: FakeSession) -> SalusPortal:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return SalusPortal(session, fixtures.USERNAME, fixtures.PASSWORD, sleep=_no_sleep)


def _ready(session: FakeSession, *value_responses: FakeResponse) -> None:
    session.add("login.php", LOGGED_IN)
    session.add("devices.php", DEVICES)
    session.add("control.php", CONTROL)
    session.add("ajax_device_values.php", *(value_responses or (values(),)))
    session.add("program.php", WRITTEN)


async def test_signing_in_posts_the_portal_login_form() -> None:
    session = FakeSession()
    _ready(session)

    await portal(session).async_read()

    (login,) = session.endpoint_calls("login.php")
    assert login["data"]["IDemail"] == fixtures.USERNAME
    assert login["params"] == {"lang": "cs"}
    assert login["data"]["keep_logged_in"] == "1"


async def test_rejected_credentials_raise_invalid_auth() -> None:
    session = FakeSession()
    _ready(session)
    session.add("login.php", REJECTED)

    with pytest.raises(InvalidAuth):
        await portal(session).async_read()


async def test_the_thermostat_is_discovered_from_the_portal_listing() -> None:
    """The config entry holds only a username and a password, so the listing is the only source."""

    session = FakeSession()
    _ready(session)

    schedule = await portal(session).async_read()

    assert schedule.device_id == DEVICE_ID
    assert session.endpoint_calls("control.php")[0]["params"] == {"devId": DEVICE_ID}


async def test_an_account_without_a_thermostat_is_reported() -> None:
    session = FakeSession()
    _ready(session)
    session.add("devices.php", FakeResponse(200, text="<html>žádná zařízení</html>"))

    with pytest.raises(PortalError):
        await portal(session).async_read()


async def test_a_second_thermostat_is_noted_and_the_first_used(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeSession()
    _ready(session)
    session.add("devices.php", FakeResponse(200, text="control.php?devId=111 control.php?devId=222"))

    with caplog.at_level(logging.WARNING):
        schedule = await portal(session).async_read()

    assert schedule.device_id == "111"
    assert "2 thermostats" in caplog.text


async def test_the_weekly_program_is_read_for_every_day() -> None:
    session = FakeSession()
    _ready(session)

    schedule = await portal(session).async_read()

    assert schedule.schedule_type == SCHEDULE_ALL
    assert schedule.writable is True
    assert set(schedule.days) == {day.lower() for day in DAYS}
    assert schedule.days["mon"] == PLAN
    assert schedule.days["sun"] == PLAN


async def test_unset_steps_are_dropped_rather_than_guessed() -> None:
    session = FakeSession()
    _ready(session, values(OTHER))

    schedule = await portal(session).async_read()

    assert schedule.days["mon"] == OTHER


async def test_the_schedule_type_is_reported() -> None:
    for reported, expected in (("0", SCHEDULE_ALL), ("1", SCHEDULE_WEEKDAY_WEEKEND), ("2", SCHEDULE_PER_DAY)):
        session = FakeSession()
        _ready(session, values(sched_type=reported))

        assert (await portal(session).async_read()).schedule_type == expected


async def test_an_unknown_schedule_type_is_not_writable() -> None:
    session = FakeSession()
    _ready(session, values(sched_type="9"))

    schedule = await portal(session).async_read()

    assert (schedule.schedule_type, schedule.writable) == ("", False)


async def test_an_unreadable_program_is_reported() -> None:
    session = FakeSession()
    _ready(session, FakeResponse(200, text="<html>chyba</html>"))

    with pytest.raises(PortalError):
        await portal(session).async_read()


async def test_a_portal_error_is_a_connection_error() -> None:
    session = FakeSession()
    _ready(session)
    session.add("devices.php", FakeResponse(503, text=""))

    with pytest.raises(SalusConnectionError):
        await portal(session).async_read()


# Writing -------------------------------------------------------------------


async def test_writing_all_days_posts_the_single_block() -> None:
    session = FakeSession()
    _ready(session, values(OTHER), values(PLAN))

    await portal(session).async_write(PLAN)

    (write,) = session.endpoint_calls("program.php")
    body = write["data"]
    assert body["z1pAllset"] == "1"
    assert body["devId"] == DEVICE_ID
    assert (body["z1pAll1time"], body["z1pAll1temp"]) == ("05:30", "22.0 °C")
    assert (body["z1pAll6time"], body["z1pAll6temp"]) == ("23:00", "19.0 °C")


async def test_a_five_two_thermostat_gets_both_of_its_blocks() -> None:
    """The all-days block is silently ignored by a device in 5/2 mode, so the mode decides the write."""

    session = FakeSession()
    _ready(session, values(OTHER, sched_type="1"), values(PLAN, sched_type="1"))

    await portal(session).async_write(PLAN)

    blocks = [set(call["data"]) for call in session.endpoint_calls("program.php")]
    assert [next(key for key in block if key.endswith("set")) for block in blocks] == [
        "z1pMon_friset",
        "z1pSat_sunset",
    ]


async def test_a_per_day_thermostat_gets_a_block_for_each_day() -> None:
    session = FakeSession()
    _ready(session, values(OTHER, sched_type="2"), values(PLAN, sched_type="2"))

    await portal(session).async_write(PLAN)

    assert len(session.endpoint_calls("program.php")) == 7


async def test_a_write_that_changes_nothing_is_not_taken_for_success() -> None:
    """A write that does not match the device's mode comes back HTTP 200 and does nothing at all."""

    session = FakeSession()
    _ready(session, values(OTHER))

    with pytest.raises(PortalError, match="did not change"):
        await portal(session).async_write(PLAN)


async def test_a_write_to_an_unknown_schedule_type_is_refused() -> None:
    session = FakeSession()
    _ready(session, values(OTHER, sched_type="9"))

    with pytest.raises(PortalError, match="Unknown schedule type"):
        await portal(session).async_write(PLAN)

    assert session.endpoint_calls("program.php") == []


async def test_a_program_with_too_many_steps_is_refused() -> None:
    session = FakeSession()
    _ready(session)

    with pytest.raises(PortalError):
        await portal(session).async_write((*PLAN, Slot("23:30", 18.0)))
    with pytest.raises(PortalError):
        await portal(session).async_write(())


# Session handling ----------------------------------------------------------


async def test_an_expired_session_is_signed_in_again_once() -> None:
    session = FakeSession()
    _ready(session)
    session.add("control.php", SIGNED_OUT, CONTROL)

    schedule = await portal(session).async_read()

    assert schedule.device_id == DEVICE_ID
    assert len(session.endpoint_calls("login.php")) == 2


async def test_a_session_that_cannot_be_restored_gives_up() -> None:
    session = FakeSession()
    _ready(session)
    session.add("control.php", SIGNED_OUT)

    with pytest.raises(PortalError):
        await portal(session).async_read()

    assert len(session.endpoint_calls("login.php")) == 2


async def test_the_second_read_reuses_the_signed_in_session() -> None:
    session = FakeSession()
    _ready(session)
    client = portal(session)

    await client.async_read()
    await client.async_read()

    assert len(session.endpoint_calls("login.php")) == 1
    assert len(session.endpoint_calls("devices.php")) == 1


async def test_no_credential_or_token_is_ever_logged(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeSession()
    _ready(session, values(OTHER), values(PLAN))

    with caplog.at_level(logging.DEBUG):
        await portal(session).async_write(PLAN)

    assert fixtures.PASSWORD not in caplog.text
    assert fixtures.USERNAME not in caplog.text
    assert TOKEN not in caplog.text


async def test_an_unreachable_portal_does_not_leak_the_request(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeSession()
    _ready(session)
    session.add("login.php", TimeoutError("timed out"))

    with pytest.raises(SalusConnectionError) as error:
        await portal(session).async_read()

    assert fixtures.PASSWORD not in str(error.value)

"""Tests of the weekly program read and written through the mobile API's day attributes."""

import pytest

from custom_components.salusfy.program import (
    CONFIRM_ATTEMPTS,
    SETTLE_SECONDS,
    WRITE_TIMEOUT,
    ProgramError,
    SalusProgram,
    Slot,
    decode_day,
    encode_day,
)
from custom_components.salusfy.pyit500.exceptions import SalusError

from . import fixtures
from .helpers import FakeResponse, FakeSession, attributes_response, create_auth

PLAN = (
    Slot("05:30", 22.0),
    Slot("09:00", 20.0),
    Slot("12:00", 21.0),
    Slot("14:00", 22.0),
    Slot("22:00", 20.0),
    Slot("23:00", 19.0),
)
DAYS = ("mon", "tus", "wed", "thu", "fri", "sat", "sun")


def _days(value: str) -> dict[str, str]:
    return {f"A0{day}": value for day in range(7)}


async def _program(session: FakeSession, *reads: FakeResponse) -> tuple[SalusProgram, list[float]]:
    session.add("getDeviceAttributesWithValues", *(reads or (attributes_response(),)))
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(0)))
    slept: list[float] = []

    async def _sleep(seconds: float) -> None:
        slept.append(seconds)

    return SalusProgram(await create_auth(session), fixtures.DEVICE_ID, sleep=_sleep), slept


# Format -----------------------------------------------------------------


def test_a_day_decodes_as_the_live_thermostats_showed_it() -> None:
    assert decode_day(fixtures.DAY_PROGRAM) == PLAN


def test_odd_minutes_decode() -> None:
    """3/12 held six 10-minute steps at 18.0 °C, read as nonsense until the format was known."""

    assert [slot.time for slot in decode_day("30B03:B03DB03NB03XB03bB0")] == [
        "03:00",
        "03:10",
        "03:20",
        "03:30",
        "03:40",
        "03:50",
    ]


def test_half_degrees_round_trip() -> None:
    """A thermostat took `C5` as 19.5 °C on 2026-10-28."""

    slots = (*PLAN[:5], Slot("23:00", 19.5))

    assert encode_day(slots).endswith("G0C5")
    assert decode_day(encode_day(slots)) == slots


def test_encoding_is_the_inverse_of_decoding() -> None:
    assert encode_day(PLAN) == fixtures.DAY_PROGRAM


@pytest.mark.parametrize("value", [None, "", "5NF090D0", fixtures.DAY_PROGRAM + "0000", "5NF0" * 5 + "/000"])
def test_an_unreadable_day_is_an_error_not_a_guess(value: str | None) -> None:
    with pytest.raises(ProgramError):
        decode_day(value)


def test_a_temperature_off_the_thermostats_step_is_refused() -> None:
    with pytest.raises(ProgramError, match=r"0.5"):
        encode_day((*PLAN[:5], Slot("23:00", 19.3)))


def test_a_program_shorter_than_the_day_is_refused() -> None:
    with pytest.raises(ProgramError, match="6 steps"):
        encode_day(PLAN[:2])


def test_a_program_error_is_a_salus_error() -> None:
    """The services turn SalusError into a HomeAssistantError a caller can catch."""

    assert issubclass(ProgramError, SalusError)


# Reading ----------------------------------------------------------------


async def test_the_weekly_program_is_read_for_every_day() -> None:
    session = FakeSession()
    program, _ = await _program(session, attributes_response(A06="5NF090D0<0E0>0F0F0D0G0C5"))

    schedule = await program.async_read()

    assert schedule.device_id == str(fixtures.DEVICE_ID)
    assert set(schedule.days) == set(DAYS)
    assert schedule.days["mon"] == PLAN
    assert schedule.days["sun"][-1] == Slot("23:00", 19.5)
    assert session.endpoint_calls("getDeviceAttributesWithValues")[-1]["data"]["devId"] == str(fixtures.DEVICE_ID)


@pytest.mark.parametrize(("value", "expected"), [("0", "all"), ("1", "weekday_weekend"), ("2", "per_day"), ("7", "")])
async def test_the_schedule_type_is_reported(value: str, expected: str) -> None:
    program, _ = await _program(FakeSession(), attributes_response(A86=value))

    schedule = await program.async_read()

    assert schedule.schedule_type == expected
    assert schedule.writable is True


async def test_a_thermostat_without_a_program_is_reported() -> None:
    program, _ = await _program(FakeSession(), attributes_response(A03=""))

    with pytest.raises(ProgramError):
        await program.async_read()


# Writing ----------------------------------------------------------------


async def test_writing_sends_the_program_to_every_day_in_one_command() -> None:
    session = FakeSession()
    program, _ = await _program(session)

    written = await program.async_write(PLAN)

    (call,) = session.endpoint_calls("setMultiDeviceAttributes2")
    params = call["params"]
    assert params["devId"] == str(fixtures.DEVICE_ID)
    assert [(params[f"name{index}"], params[f"value{index}"]) for index in range(1, 8)] == [
        (f"A0{day}", fixtures.DAY_PROGRAM) for day in range(7)
    ]
    assert all(slots == PLAN for slots in written.days.values())


async def test_a_five_two_thermostat_gets_all_seven_days_too() -> None:
    """The cloud keeps each day apart even in 5/2 mode, so the weekend is written as well."""

    session = FakeSession()
    program, _ = await _program(session, attributes_response(A86="1"))

    await program.async_write(PLAN)

    params = session.endpoint_calls("setMultiDeviceAttributes2")[0]["params"]
    assert {params[f"name{index}"] for index in range(1, 8)} == {f"A0{day}" for day in range(7)}


async def test_a_program_that_lands_slowly_is_still_a_success() -> None:
    old = attributes_response(**_days("30B03:B03DB03NB03XB03bB0"))
    session = FakeSession()
    program, slept = await _program(session, old, old, attributes_response())

    await program.async_write(PLAN)

    assert slept == [SETTLE_SECONDS] * 3


async def test_a_program_that_never_lands_says_how_long_it_waited() -> None:
    session = FakeSession()
    program, slept = await _program(session, attributes_response(A05="30B03:B03DB03NB03XB03bB0"))

    with pytest.raises(ProgramError, match=f"sat did not change within {CONFIRM_ATTEMPTS * SETTLE_SECONDS} s"):
        await program.async_write(PLAN)

    assert len(slept) == CONFIRM_ATTEMPTS


async def test_a_rejected_command_is_an_error_without_reading_back() -> None:
    session = FakeSession()
    program, slept = await _program(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(5)))

    with pytest.raises(ProgramError, match="retCode 5"):
        await program.async_write(PLAN)

    assert slept == []


async def test_nothing_is_sent_for_a_program_that_cannot_be_encoded() -> None:
    session = FakeSession()
    program, _ = await _program(session)

    with pytest.raises(ProgramError):
        await program.async_write(PLAN[:2])

    assert session.endpoint_calls("setMultiDeviceAttributes2") == []


async def test_a_command_left_unanswered_that_landed_is_a_success() -> None:
    """On 2026-10-28 both rewrites outlasted the request timeout and still landed; the read-back decides."""

    session = FakeSession()
    program, _ = await _program(session)
    session.add("setMultiDeviceAttributes2", TimeoutError())

    written = await program.async_write(PLAN)

    assert all(slots == PLAN for slots in written.days.values())
    (call,) = session.endpoint_calls("setMultiDeviceAttributes2")
    assert call["timeout"] == WRITE_TIMEOUT


async def test_a_command_left_unanswered_that_did_not_land_is_an_error() -> None:
    session = FakeSession()
    program, _ = await _program(session, attributes_response(**_days("30B03:B03DB03NB03XB03bB0")))
    session.add("setMultiDeviceAttributes2", TimeoutError())

    with pytest.raises(ProgramError, match="did not change"):
        await program.async_write(PLAN)

    assert len(session.endpoint_calls("setMultiDeviceAttributes2")) == 1

"""Tests for Salus iT500 device commands and state."""

import asyncio

import pytest

from custom_components.salusfy.pyit500.devicelistitem import DeviceListItem
from custom_components.salusfy.pyit500.exceptions import SalusCommandError, SalusConnectionError
from custom_components.salusfy.pyit500.heatingzone import ConsolidatedMode
from custom_components.salusfy.pyit500.hotwaterzone import Mode

from . import fixtures
from .helpers import FakeResponse, FakeSession, attributes_response, create_auth, create_device


async def test_commanded_mode_is_shown_until_api_reports_it() -> None:
    """Salus API reflects changes after 10-30 s; the commanded mode is shown meanwhile."""

    session = FakeSession()
    device = await create_device(session)

    await device.ch1.async_set_consolidated_mode(ConsolidatedMode.AUTO)
    assert session.attribute_sets() == [("A89", "0")]
    assert device.ch1.consolidated_mode == ConsolidatedMode.AUTO

    await device.async_update()
    assert device.ch1.consolidated_mode == ConsolidatedMode.AUTO


async def test_confirmed_command_no_longer_overrides_api_state() -> None:
    """Once the API reports the commanded value, later changes made on the thermostat are shown."""

    session = FakeSession()
    device = await create_device(session)
    await device.ch1.async_set_consolidated_mode(ConsolidatedMode.AUTO)

    session.add("getDeviceAttributesWithValues", attributes_response(A89="0"))
    await device.async_update()
    session.add("getDeviceAttributesWithValues", attributes_response(A89="1"))
    await device.async_update()

    assert device.ch1.consolidated_mode == ConsolidatedMode.OFF


async def test_commanded_value_expires() -> None:
    """A command the API never reflects stops overriding its state after a minute."""

    session = FakeSession()
    now = [0.0]
    device = await create_device(session, clock=lambda: now[0])
    await device.ch1.async_set_current_setpoint(22.5)
    assert device.ch1.current_setpoint == 22.5

    now[0] = 61
    assert device.ch1.current_setpoint == 21.0


async def test_rejected_command_raises_and_keeps_state() -> None:
    """A command with non-zero return code is reported as failed and not shown as applied."""

    session = FakeSession()
    device = await create_device(session)
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(1)))

    with pytest.raises(SalusCommandError):
        await device.hw.async_set_mode(Mode.OFF)

    assert device.hw.mode == Mode.ON


async def test_temp_hold_to_auto_switches_through_manual() -> None:
    """Direct temporary hold to auto does not stick in Salus API, so manual mode is set first."""

    session = FakeSession()
    device = await create_device(session, A89="0", A88="1")
    assert device.ch1.consolidated_mode == ConsolidatedMode.TEMP_HOLD

    await device.ch1.async_set_consolidated_mode(ConsolidatedMode.AUTO)

    assert session.attribute_sets() == [("A92", "1"), ("A88", "0"), ("A92", "0")]
    assert device.ch1.consolidated_mode == ConsolidatedMode.AUTO


async def test_setpoint_is_rounded_to_hundredths_of_degree() -> None:
    """Setpoint sent in hundredths of a degree is rounded, float imprecision does not lower it."""

    session = FakeSession()
    device = await create_device(session)

    await device.ch1.async_set_current_setpoint(19.9)

    assert session.attribute_sets() == [("A85", "1990")]


async def test_malformed_response_is_connection_error() -> None:
    """An unexpected (non-XML) API answer is reported as an API problem."""

    session = FakeSession()
    session.add("getDeviceList", FakeResponse(200, text="<html>Service Unavailable"))
    auth = await create_auth(session)

    with pytest.raises(SalusConnectionError):
        await DeviceListItem.async_get_device_list(auth)


async def test_command_does_not_start_background_refresh() -> None:
    """Sending a command does not start an untracked device update; refreshing is up to the caller."""

    session = FakeSession()
    device = await create_device(session)
    updates_before = len(session.endpoint_calls("getDeviceAttributesWithValues"))

    await device.hw.async_set_mode(Mode.AUTO)
    await asyncio.sleep(1.1)

    assert len(session.endpoint_calls("getDeviceAttributesWithValues")) == updates_before

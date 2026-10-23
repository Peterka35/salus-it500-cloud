"""Tests for Salus iT500 config flow."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.salusfy.config_flow import ConfigFlow
from custom_components.salusfy.const import CONF_DEVICE_ID, DOMAIN

from . import fixtures
from .helpers import FakeResponse, FakeSession, attributes_response, login_response

CLIENT_SESSION = "custom_components.salusfy.config_flow.async_get_clientsession"
CREDENTIALS = {CONF_USERNAME: fixtures.USERNAME, CONF_PASSWORD: fixtures.PASSWORD}
DEVICE, SECOND_DEVICE = fixtures.DEVICE_ID, fixtures.SECOND_DEVICE_ID


def _flow(source: str, configured: tuple[str, ...] = ()) -> ConfigFlow:
    """Return flow of Home Assistant that has entries with the `configured` unique ids."""

    flow = ConfigFlow()
    flow.hass = MagicMock()
    entries = [MagicMock(unique_id=unique_id) for unique_id in configured]
    flow.hass.config_entries.async_entries.return_value = entries
    flow.hass.config_entries.async_entry_for_domain_unique_id.side_effect = lambda _domain, unique_id: next(
        (entry for entry in entries if entry.unique_id == unique_id), None
    )
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = []
    flow.handler = DOMAIN
    flow.flow_id = f"{source}-flow"
    flow.context = {"source": source, "entry_id": "salusfy-entry"}
    return flow


def _reauth_flow() -> tuple[ConfigFlow, MagicMock]:
    entry = MagicMock()
    entry.data = {CONF_USERNAME: fixtures.USERNAME, CONF_PASSWORD: "old-password"}
    flow = _flow("reauth")
    flow._get_reauth_entry = MagicMock(return_value=entry)
    flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort", "reason": "reauth_successful"})
    return flow, entry


def _account_session(*login_results: FakeResponse) -> FakeSession:
    session = FakeSession()
    session.add("sessions", *login_results)
    session.add("getDeviceList", FakeResponse(200, text=fixtures.device_list_xml()))
    session.add("getDeviceAttributesWithValues", attributes_response())
    return session


def _two_thermostats_session() -> FakeSession:
    """Return account owning a thermostat in two houses; attributes are asked for in listing order."""

    session = _account_session(login_response())
    session.add("getDeviceList", FakeResponse(200, text=fixtures.device_list_xml(DEVICE, SECOND_DEVICE)))
    session.add("getDeviceAttributesWithValues", attributes_response(), attributes_response(desc="Chata"))
    return session


def _offered(result: dict) -> dict[str, str]:
    """Return thermostats offered by the device step, labels by device id."""

    return next(iter(result["data_schema"].schema.values())).container


async def test_single_thermostat_is_added_without_asking() -> None:
    """An account with one thermostat is added at once, keyed by the thermostat."""

    flow = _flow("user")

    with patch(CLIENT_SESSION, return_value=_account_session(login_response())):
        result = await flow.async_step_user(CREDENTIALS)

    assert (result["type"], result["title"]) == ("create_entry", "Apartmán A")
    assert result["data"] == {**CREDENTIALS, CONF_DEVICE_ID: str(DEVICE)}
    assert flow.unique_id == str(DEVICE)


async def test_account_with_two_thermostats_asks_which_one() -> None:
    """Every thermostat of the account is offered by its name and the chosen one is added."""

    flow = _flow("user")

    with patch(CLIENT_SESSION, return_value=_two_thermostats_session()):
        result = await flow.async_step_user(CREDENTIALS)
        assert result["step_id"] == "device"
        assert _offered(result) == {str(DEVICE): "Apartmán A", str(SECOND_DEVICE): "Chata"}

        result = await flow.async_step_device({CONF_DEVICE_ID: str(SECOND_DEVICE)})

    assert (result["type"], result["title"]) == ("create_entry", "Chata")
    assert result["data"] == {**CREDENTIALS, CONF_DEVICE_ID: str(SECOND_DEVICE)}
    assert flow.unique_id == str(SECOND_DEVICE)


async def test_configured_thermostat_is_not_offered_again() -> None:
    """A thermostat that already has an entry is left out of the choice."""

    flow = _flow("user", configured=(str(DEVICE),))

    with patch(CLIENT_SESSION, return_value=_two_thermostats_session()):
        result = await flow.async_step_user(CREDENTIALS)

    assert _offered(result) == {str(SECOND_DEVICE): "Chata"}


async def test_account_with_every_thermostat_configured_is_not_added() -> None:
    """Adding an account whose thermostats all have entries ends without a new entry."""

    flow = _flow("user", configured=(str(DEVICE), str(SECOND_DEVICE)))

    with patch(CLIENT_SESSION, return_value=_two_thermostats_session()):
        result = await flow.async_step_user(CREDENTIALS)

    assert (result["type"], result["reason"]) == ("abort", "already_configured")


async def test_account_added_by_an_older_version_is_not_added_again() -> None:
    """An entry made before the thermostat choice is keyed by the account until it is next set up."""

    flow = _flow("user", configured=(fixtures.USERNAME,))

    with patch(CLIENT_SESSION, return_value=_account_session(login_response())):
        result = await flow.async_step_user({**CREDENTIALS, CONF_USERNAME: fixtures.USERNAME.upper()})

    assert (result["type"], result["reason"]) == ("abort", "already_configured")


async def test_unavailable_api_is_not_reported_as_invalid_credentials() -> None:
    """Salus API failing during setup is reported as connection problem, not as wrong credentials."""

    flow = _flow("user")

    with patch(CLIENT_SESSION, return_value=_account_session(FakeResponse(503))):
        result = await flow.async_step_user({CONF_USERNAME: fixtures.USERNAME, CONF_PASSWORD: fixtures.PASSWORD})

    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_stores_new_password() -> None:
    """Accepted new password is stored and the integration reloaded."""

    flow, entry = _reauth_flow()

    with patch(CLIENT_SESSION, return_value=_account_session(login_response())):
        result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new-password"})

    assert result["reason"] == "reauth_successful"
    flow.async_update_reload_and_abort.assert_called_once_with(entry, data_updates={CONF_PASSWORD: "new-password"})


async def test_reauth_with_rejected_password_shows_error(caplog: pytest.LogCaptureFixture) -> None:
    """Rejected password is reported in the form without logging the account."""

    caplog.set_level(logging.DEBUG)
    flow, _ = _reauth_flow()

    with patch(CLIENT_SESSION, return_value=_account_session(FakeResponse(403))):
        result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "wrong-password"})

    assert (result["step_id"], result["errors"]) == ("reauth_confirm", {"base": "invalid_auth"})
    flow.async_update_reload_and_abort.assert_not_called()
    assert fixtures.USERNAME not in caplog.text

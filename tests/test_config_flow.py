"""Tests for Salus iT500 config flow."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.salusfy.config_flow import ConfigFlow
from custom_components.salusfy.const import DOMAIN

from . import fixtures
from .helpers import FakeResponse, FakeSession, attributes_response, login_response

CLIENT_SESSION = "custom_components.salusfy.config_flow.async_get_clientsession"


def _flow(source: str) -> ConfigFlow:
    flow = ConfigFlow()
    flow.hass = MagicMock()
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

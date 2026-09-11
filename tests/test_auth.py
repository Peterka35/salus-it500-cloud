"""Tests for Salus iT500 API authentication and requests."""

import logging
from hashlib import md5

import pytest

from custom_components.salusfy.pyit500.auth import Auth
from custom_components.salusfy.pyit500.exceptions import InvalidAuth, SalusConnectionError

from . import fixtures
from .helpers import FakeResponse, FakeSession, create_auth, login_response


def _auth(session: FakeSession) -> Auth:
    return Auth(session, fixtures.USERNAME, fixtures.PASSWORD)


async def test_rejected_credentials_raise_invalid_auth(caplog: pytest.LogCaptureFixture) -> None:
    """Credentials rejected with and without special characters ask for new credentials and leak nothing to the log."""

    caplog.set_level(logging.DEBUG)
    session = FakeSession()
    session.add("sessions", FakeResponse(403, text="Invalid login name or password"))

    with pytest.raises(InvalidAuth):
        await _auth(session).refresh_token()

    assert len(session.endpoint_calls("sessions")) == 2
    assert fixtures.USERNAME not in caplog.text
    assert md5(fixtures.PASSWORD.encode()).hexdigest()[:8] not in caplog.text


async def test_password_without_special_characters_is_tried() -> None:
    """Salus strips special characters from passwords, so login falls back to the stripped password."""

    session = FakeSession()
    session.add("sessions", FakeResponse(403), login_response())
    auth = _auth(session)

    await auth.refresh_token()

    sent_hashes = [kwargs["json"]["password"] for kwargs in session.endpoint_calls("sessions")]
    assert sent_hashes == [md5(b"secret!pass").hexdigest(), md5(b"secretpass").hexdigest()]
    assert (auth.user_id, auth.security_token) == (fixtures.USER_ID, fixtures.SECURITY_TOKEN)


async def test_login_server_error_is_connection_error() -> None:
    """Salus server failing during login is a temporary problem, not rejected credentials."""

    session = FakeSession()
    session.add("sessions", FakeResponse(500, text="Internal Server Error"))

    with pytest.raises(SalusConnectionError):
        await _auth(session).refresh_token()


async def test_server_error_is_retried_once() -> None:
    """Intermittent HTTP 500 from Salus API does not fail the request."""

    session = FakeSession()
    session.add("getDeviceList", FakeResponse(500), FakeResponse(200, text=fixtures.device_list_xml()))
    auth = await create_auth(session)

    assert await auth.request("post", "getDeviceList") == fixtures.device_list_xml()
    assert len(session.endpoint_calls("getDeviceList")) == 2


async def test_repeated_server_error_raises_connection_error() -> None:
    """A request failing again after the retry raises connection error."""

    session = FakeSession()
    session.add("getDeviceList", FakeResponse(500))
    auth = await create_auth(session)

    with pytest.raises(SalusConnectionError):
        await auth.request("post", "getDeviceList")

    assert len(session.endpoint_calls("getDeviceList")) == 2


async def test_timeout_is_retried_once() -> None:
    """A timed out request is retried."""

    session = FakeSession()
    session.add("getDeviceList", TimeoutError(), FakeResponse(200, text=fixtures.device_list_xml()))
    auth = await create_auth(session)

    assert await auth.request("post", "getDeviceList") == fixtures.device_list_xml()


async def test_expired_token_is_renewed() -> None:
    """Rejected security token leads to a new login and the request is sent with the new token."""

    session = FakeSession()
    session.add("getDeviceList", FakeResponse(401), FakeResponse(200, text=fixtures.device_list_xml()))
    auth = await create_auth(session)
    session.add("sessions", login_response("token-2"))

    await auth.request("post", "getDeviceList")

    assert [kwargs["data"]["secToken"] for kwargs in session.endpoint_calls("getDeviceList")] == ["token-1", "token-2"]

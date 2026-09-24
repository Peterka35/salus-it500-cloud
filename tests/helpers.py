"""Test helpers: fake aiohttp session for the Salus iT500 API."""

import json
from collections.abc import Callable
from copy import copy
from typing import Any

from custom_components.salusfy.pyit500.auth import Auth
from custom_components.salusfy.pyit500.device import Device

from . import fixtures


class FakeResponse:
    """Response of the fake session."""

    def __init__(self, status: int = 200, text: str = "") -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class FakeSession:
    """Session answering by the last URL path segment; queued results are used in order, the last one repeats."""

    def __init__(self) -> None:
        self.routes: dict[str, list[FakeResponse | BaseException]] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def add(self, endpoint: str, *results: FakeResponse | BaseException) -> None:
        self.routes[endpoint] = list(results)

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        endpoint = url.rsplit("/", 1)[-1]
        # Snapshot nested dicts, the caller may reuse them for the next request
        self.calls.append((method, endpoint, {key: copy(value) for key, value in kwargs.items()}))
        queue = self.routes[endpoint]
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, BaseException):
            raise result
        return result

    def endpoint_calls(self, endpoint: str) -> list[dict[str, Any]]:
        return [kwargs for _, called, kwargs in self.calls if called == endpoint]

    def attribute_sets(self) -> list[tuple[str, str]]:
        """Return (attribute, value) pairs sent with setMultiDeviceAttributes2, in order."""
        return [
            (params[f"name{index}"], str(params[f"value{index}"]))
            for params in (kwargs["params"] for kwargs in self.endpoint_calls("setMultiDeviceAttributes2"))
            for index in (1, 2, 3)
            if f"name{index}" in params
        ]


def login_response(token: str = fixtures.SECURITY_TOKEN) -> FakeResponse:
    return FakeResponse(200, text=json.dumps({"userId": fixtures.USER_ID, "securityToken": token}))


def attributes_response(reported_at: float | None = None, **changes: str) -> FakeResponse:
    return FakeResponse(
        200, text=fixtures.device_attributes_xml({**fixtures.DEVICE_ATTRIBUTES, **changes}, reported_at)
    )


async def create_auth(session: FakeSession) -> Auth:
    """Return auth logged in to the fake API."""

    session.add("sessions", login_response())
    auth = Auth(session, fixtures.USERNAME, fixtures.PASSWORD)
    await auth.refresh_token()
    return auth


async def create_device(
    session: FakeSession,
    clock: Callable[[], float] = lambda: 0.0,
    reported_at: float | None = None,
    **attribute_changes: str,
) -> Device:
    """Return logged in device loaded from the fake API."""

    session.add("getDeviceAttributesWithValues", attributes_response(reported_at, **attribute_changes))
    session.add("setMultiDeviceAttributes2", FakeResponse(200, text=fixtures.set_attributes_xml(0)))
    device = Device(fixtures.DEVICE_ID, None, await create_auth(session), clock=clock)
    await device.async_update()
    return device

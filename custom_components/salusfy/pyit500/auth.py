"""Module to provide the Authenticated requests"""

import asyncio
import json
import logging
import re
from hashlib import md5
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .exceptions import InvalidAuth, SalusConnectionError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=20)
RETRY_DELAY_SECONDS = 2
AUTH_ERROR_STATUSES = frozenset({401, 403})
TEMPORARY_ERROR_STATUSES = frozenset({500, 502, 503, 504})
# Salus API answers an expired or unknown security token with HTTP 500 and this fault, not with 401
INVALID_TOKEN_FAULT = "<errorCode>106</errorCode>"


def _token_rejected(status: int, body: str) -> bool:
    return status in AUTH_ERROR_STATUSES or INVALID_TOKEN_FAULT in body


def _strip_special_chars(password: str) -> str:
    """Remove special characters from password.

    Salus systems silently strip special characters when passwords are created,
    but users don't know this. This causes authentication failures when users
    enter their password with special characters they thought were saved.
    """
    return re.sub(r"[^a-zA-Z0-9]", "", password)


def _md5(value: str) -> str:
    return md5(value.encode()).hexdigest()


class Auth:
    """Class to make authenticated requests."""

    host = "https://sal-emea-p01-api.arrayent.com"
    auth_path = "acc/applications/SalusService/sessions"
    api_path = "zdk/services/zamapi"

    def __init__(self, websession: ClientSession, username: str, password: str) -> None:
        """Initialize the auth."""
        self.websession = websession
        self.username = username
        self._password = password
        self.passhash = _md5(password)
        self.user_id: int | None = None
        self.security_token: str | None = None

    def get_user_id(self) -> int | None:
        """Return the user ID associated with the auth session."""
        return self.user_id

    async def refresh_token(self) -> None:
        """Get user ID & security token using credentials.

        Rejected credentials are retried with special characters removed from the password,
        because Salus silently strips them when a password is set.
        """
        resp_values = await self._async_login(self.passhash)
        if resp_values is None:
            stripped_password = _strip_special_chars(self._password)
            if stripped_password != self._password:
                resp_values = await self._async_login(_md5(stripped_password))
                if resp_values is not None:
                    _LOGGER.info("Salus accepted the password without special characters")
                    self._password = stripped_password
                    self.passhash = _md5(stripped_password)

        if resp_values is None:
            raise InvalidAuth("Invalid login name or password")
        try:
            self.user_id = resp_values["userId"]
            self.security_token = resp_values["securityToken"]
        except (KeyError, TypeError) as err:
            raise SalusConnectionError("Unexpected Salus login response") from err

    async def _async_login(self, passhash: str) -> Any:
        """Log in with the password hash; return None when Salus rejects the credentials."""
        status, body = await self._async_send(
            "post", f"{self.host}/{self.auth_path}", json={"username": self.username, "password": passhash}
        )
        if status in AUTH_ERROR_STATUSES:
            return None
        try:
            return json.loads(body)
        except ValueError as err:
            raise SalusConnectionError("Unexpected Salus login response") from err

    async def request(
        self,
        method: str,
        path: str,
        *,
        client_timeout: ClientTimeout = REQUEST_TIMEOUT,
        retry: bool = True,
        **kwargs: Any,
    ) -> str:
        """Make an authenticated API request and return the response body.

        A rejected security token is renewed and the request is sent once more. Without `retry`, a
        request that failed or did not answer is not sent a second time."""
        url = f"{self.host}/{self.api_path}/{path}"
        auth_arg = "data" if method == "post" else "params"
        values = dict(kwargs.pop(auth_arg, None) or {})

        for attempt in range(2):
            auth_values = {"userId": self.user_id, **values, "secToken": self.security_token}
            status, body = await self._async_send(
                method, url, client_timeout=client_timeout, retry=retry, **kwargs, **{auth_arg: auth_values}
            )
            if not _token_rejected(status, body):
                return body
            if attempt == 0:
                _LOGGER.debug("Salus security token was rejected, logging in again")
                await self.refresh_token()

        raise SalusConnectionError(f"Salus API rejected the renewed security token (HTTP {status})")

    async def _async_send(
        self,
        method: str,
        url: str,
        *,
        client_timeout: ClientTimeout = REQUEST_TIMEOUT,
        retry: bool = True,
        **kwargs: Any,
    ) -> tuple[int, str]:
        """Send a request and return its status and body.

        Salus API intermittently fails with server errors or does not answer, so such a request is sent once more.
        Authentication errors are returned to the caller."""
        attempts = 2 if retry else 1
        for attempt in range(attempts):
            try:
                resp = await self.websession.request(method, url, timeout=client_timeout, **kwargs)
                body = await resp.text()
            except (TimeoutError, ClientError) as err:
                problem = type(err).__name__
            else:
                if resp.status < 400 or _token_rejected(resp.status, body):
                    return resp.status, body
                if resp.status not in TEMPORARY_ERROR_STATUSES:
                    raise SalusConnectionError(f"Salus API returned HTTP {resp.status}")
                problem = f"HTTP {resp.status}"

            if attempt < attempts - 1:
                _LOGGER.debug("Salus API request failed (%s), retrying", problem)
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        raise SalusConnectionError(f"Salus API request failed: {problem}")

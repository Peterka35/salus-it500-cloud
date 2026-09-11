"""Module to provide the Authenticated requests"""
import logging
import re
from hashlib import md5
from aiohttp import ClientSession, ClientResponse, ClientTimeout, ClientResponseError

_LOGGER = logging.getLogger(__name__)


def _strip_special_chars(password: str) -> str:
    """Remove special characters from password.

    Salus systems silently strip special characters when passwords are created,
    but users don't know this. This causes authentication failures when users
    enter their password with special characters they thought were saved.
    """
    return re.sub(r'[^a-zA-Z0-9]', '', password)


class Auth:  # pylint: disable=too-few-public-methods
    """Class to make authenticated requests."""

    host = "https://sal-emea-p01-api.arrayent.com"
    auth_path = "acc/applications/SalusService/sessions"
    api_path = "zdk/services/zamapi"

    def __init__(
        self,
        websession: ClientSession,
        username: str,
        password: str,
        get_token: bool = False,
    ):
        """Initialize the auth."""
        self.websession = websession
        self.username = username
        self._password = password  # Store original password for fallback
        self.passhash = md5(password.encode()).hexdigest()
        self.user_id = None
        self.security_token = None
        _LOGGER.debug("Auth initialized for user: %s", username)
        if get_token:
            self.refresh_token()

    def get_user_id(self) -> int:
        """Return the user ID associated with the auth session."""
        return self.user_id

    async def _try_authenticate(self, passhash: str) -> dict | None:
        """Attempt authentication with given password hash.

        Returns response dict on success, None on auth failure (403).
        Raises exception on other errors.
        """
        auth_url = f"{self.host}/{self.auth_path}"
        timeout = ClientTimeout(total=30)

        resp = await self.websession.post(
            auth_url,
            json={"username": self.username, "password": passhash},
            timeout=timeout,
        )

        _LOGGER.debug("Auth response status: %s", resp.status)

        if resp.status == 403:
            response_text = await resp.text()
            _LOGGER.debug(
                "Authentication returned 403. Response: %s",
                response_text[:500] if response_text else "(empty)"
            )
            return None

        if resp.status != 200:
            response_text = await resp.text()
            _LOGGER.error(
                "Authentication failed with status %s. Response: %s",
                resp.status,
                response_text[:500] if response_text else "(empty)"
            )
            resp.raise_for_status()

        return await resp.json()

    async def refresh_token(self) -> None:
        """Get user ID & security token using credentials.

        If authentication fails, automatically retries with special characters
        removed from password (Salus silently strips these when setting passwords).
        """
        auth_url = f"{self.host}/{self.auth_path}"
        _LOGGER.debug("Attempting authentication to: %s", auth_url)
        _LOGGER.debug("Username: %s, Password hash: %s...", self.username, self.passhash[:8])

        try:
            # First attempt with original password
            resp_values = await self._try_authenticate(self.passhash)

            # If failed, try without special characters
            if resp_values is None:
                stripped_password = _strip_special_chars(self._password)
                if stripped_password != self._password:
                    _LOGGER.info(
                        "Authentication failed, retrying without special characters "
                        "(Salus may have stripped them from your password)"
                    )
                    stripped_hash = md5(stripped_password.encode()).hexdigest()
                    resp_values = await self._try_authenticate(stripped_hash)

                    if resp_values is not None:
                        # Success with stripped password - update stored hash
                        _LOGGER.info(
                            "Authentication successful after removing special characters. "
                            "Note: Salus stripped special characters from your password when you created it."
                        )
                        self.passhash = stripped_hash

            if resp_values is None:
                _LOGGER.error(
                    "Authentication failed for user %s. Please verify your credentials.",
                    self.username
                )
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=403,
                    message="Invalid login name or password",
                )

            _LOGGER.debug(
                "Auth response keys: %s",
                list(resp_values.keys()) if isinstance(resp_values, dict) else type(resp_values)
            )

            if "userId" not in resp_values:
                _LOGGER.error("Auth response missing 'userId'. Response: %s", resp_values)
                raise ValueError(f"Invalid auth response - missing userId: {resp_values}")

            if "securityToken" not in resp_values:
                _LOGGER.error("Auth response missing 'securityToken'. Response: %s", resp_values)
                raise ValueError(f"Invalid auth response - missing securityToken: {resp_values}")

            self.user_id = resp_values["userId"]
            self.security_token = resp_values["securityToken"]
            _LOGGER.info("Successfully authenticated user %s (userId: %s)", self.username, self.user_id)

        except ClientResponseError as err:
            _LOGGER.error(
                "HTTP error during authentication: status=%s, message=%s, url=%s",
                err.status, err.message, auth_url
            )
            raise
        except Exception as err:
            _LOGGER.error(
                "Unexpected error during authentication: %s (%s)",
                err, type(err).__name__
            )
            raise

    async def request(self, method: str, path: str, **kwargs) -> ClientResponse:
        """Make a request with automatic token refresh on auth errors."""
        full_url = f"{self.host}/{self.api_path}/{path}"
        _LOGGER.debug("API request: %s %s", method.upper(), full_url)

        if method == "post":
            auth_arg = "data"
        else:
            auth_arg = "params"

        auth_arg_value = kwargs.pop(auth_arg, {})

        if auth_arg_value is None:
            auth_arg_value = {}
        else:
            auth_arg_value = dict(auth_arg_value)

        auth_arg_value["secToken"] = self.security_token
        if "userId" not in auth_arg_value:
            auth_arg_value["userId"] = self.user_id

        kwargs[auth_arg] = auth_arg_value

        # Add timeout if not already specified
        if "timeout" not in kwargs:
            kwargs["timeout"] = ClientTimeout(total=30)

        # Make the request
        try:
            response = await self.websession.request(
                method,
                full_url,
                **kwargs,
            )
            _LOGGER.debug("API response status: %s for %s", response.status, path)
        except Exception as err:
            _LOGGER.error("Network error during API request to %s: %s (%s)", path, err, type(err).__name__)
            raise

        # Check for auth errors (401/403) and retry once with token refresh
        try:
            response.raise_for_status()
        except ClientResponseError as err:
            if err.status in (401, 403):
                _LOGGER.warning("Auth error (status %s) for %s, refreshing token and retrying...", err.status, path)
                # Token expired or invalid - refresh and retry
                await self.refresh_token()

                # Update auth parameters with new token
                auth_arg_value["secToken"] = self.security_token
                if "userId" not in auth_arg_value:
                    auth_arg_value["userId"] = self.user_id
                kwargs[auth_arg] = auth_arg_value

                # Retry the request
                response = await self.websession.request(
                    method,
                    full_url,
                    **kwargs,
                )
                _LOGGER.debug("Retry response status: %s for %s", response.status, path)
                # Check status on retry response as well
                response.raise_for_status()
            else:
                _LOGGER.error("API error: status=%s, message=%s, url=%s", err.status, err.message, full_url)
                # Re-raise non-auth errors
                raise

        return response

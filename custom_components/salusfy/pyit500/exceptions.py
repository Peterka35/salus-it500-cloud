"""Exceptions raised by the Salus iT500 API client."""


class SalusError(Exception):
    """Base error of the Salus iT500 API client."""


class InvalidAuth(SalusError):
    """Salus rejected the credentials."""


class SalusConnectionError(SalusError):
    """Salus API could not be reached or failed to answer."""


class SalusCommandError(SalusError):
    """Salus API did not accept a command."""

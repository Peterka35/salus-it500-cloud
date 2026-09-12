"""Shared test configuration."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def entity_platform(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stand in for the platform context Home Assistant provides while setting a platform up."""

    platform = MagicMock()
    monkeypatch.setattr(
        "custom_components.salusfy.climate.entity_platform.async_get_current_platform", lambda: platform
    )
    return platform


@pytest.fixture(autouse=True)
def no_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run retries and mode switch workarounds without waiting."""

    monkeypatch.setattr("custom_components.salusfy.pyit500.auth.RETRY_DELAY_SECONDS", 0, raising=False)
    monkeypatch.setattr("custom_components.salusfy.pyit500.heatingzone.MODE_SWITCH_DELAY_SECONDS", 0, raising=False)

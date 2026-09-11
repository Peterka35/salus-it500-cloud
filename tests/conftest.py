"""Shared test configuration."""

import pytest


@pytest.fixture(autouse=True)
def no_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run retries and mode switch workarounds without waiting."""

    monkeypatch.setattr("custom_components.salusfy.pyit500.auth.RETRY_DELAY_SECONDS", 0, raising=False)
    monkeypatch.setattr("custom_components.salusfy.pyit500.heatingzone.MODE_SWITCH_DELAY_SECONDS", 0, raising=False)

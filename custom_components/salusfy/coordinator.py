"""Data update coordinator for the Salus iT500 integration."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONFIRM_REFRESH_DELAYS, DEVICE_OFFLINE_AFTER, DOMAIN, STALE_DATA_TOLERANCE, UPDATE_INTERVAL
from .portal import SalusPortal
from .pyit500.device import Device
from .pyit500.exceptions import InvalidAuth, SalusError

_LOGGER = logging.getLogger(__name__)

type SalusConfigEntry = ConfigEntry[SalusDataCoordinator]


class SalusDataCoordinator(DataUpdateCoordinator[Device]):
    """Polls the Salus iT500 device and sends its commands."""

    config_entry: SalusConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SalusConfigEntry,
        device: Device,
        clock: Callable[[], float] = time.monotonic,
        portal: SalusPortal | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.device = device
        # The weekly program lives on the web portal, not in the mobile API this coordinator polls
        self.portal = portal
        self._clock = clock
        self._wall_clock = wall_clock
        self._reported_offline = False
        self._last_success: float | None = None
        self._cancel_confirmations: list[CALLBACK_TYPE] = []

    async def _async_update_data(self) -> Device:
        """Fetch data from API."""
        try:
            await self.device.async_update()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Salus rejected the credentials") from err
        except SalusError as err:
            # Salus API fails intermittently, entities keep their last state for a while
            if self._last_success is not None and (
                self._clock() - self._last_success < STALE_DATA_TOLERANCE.total_seconds()
            ):
                _LOGGER.debug("Keeping last known state, update failed: %s", err)
                return self.device
            raise UpdateFailed(f"Error communicating with Salus API: {err}") from err

        self._last_success = self._clock()
        self._log_presence()
        return self.device

    @property
    def device_offline(self) -> bool:
        """Whether the thermostat itself has gone quiet, although the API still answers for it.

        Silence alone is not an outage: a steady thermostat uploads nothing for hours. It takes the
        cloud losing the gateway, and the values being old enough not to contradict that."""
        reported_at = self.device.reported_at
        if reported_at is None or self.device.connected is not False:
            return False
        return self._wall_clock() - reported_at > DEVICE_OFFLINE_AFTER.total_seconds()

    def _log_presence(self) -> None:
        offline = self.device_offline
        if offline == self._reported_offline:
            return
        self._reported_offline = offline
        if offline:
            reported_at = self.device.reported_at or 0
            _LOGGER.warning(
                "Salus thermostat %s has not reported since %s, showing it as unavailable",
                self.device.description,
                time.strftime("%Y-%m-%d %H:%M", time.localtime(reported_at)),
            )
        else:
            _LOGGER.info("Salus thermostat %s is reporting again", self.device.description)

    async def async_run[T](self, command: Callable[[], Awaitable[T]]) -> T:
        """Run a Salus call and turn its failures into Home Assistant errors."""
        try:
            return await command()
        except InvalidAuth as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except SalusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_send_command(self, command: Callable[[], Awaitable[Any]]) -> None:
        """Send a device command.

        The commanded state is shown at once; Salus API reports it after 10-30 seconds,
        so the state is fetched again a few times to confirm it."""
        try:
            await self.async_run(command)
        finally:
            # A mode change consists of several commands, show whatever was applied
            self.async_update_listeners()
            self._schedule_confirmations()

    @callback
    def _schedule_confirmations(self) -> None:
        self._cancel_scheduled_confirmations()
        self._cancel_confirmations = [
            async_call_later(self.hass, delay, self._async_confirm) for delay in CONFIRM_REFRESH_DELAYS
        ]

    @callback
    def _cancel_scheduled_confirmations(self) -> None:
        for cancel in self._cancel_confirmations:
            cancel()
        self._cancel_confirmations = []

    async def _async_confirm(self, _now: datetime) -> None:
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Cancel scheduled refreshes."""
        self._cancel_scheduled_confirmations()
        await super().async_shutdown()

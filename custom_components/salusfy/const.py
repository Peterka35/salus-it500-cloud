"""Constants for the Salus iT500 integration."""

from datetime import timedelta

DOMAIN = "salusfy"

# Update interval for polling
# Salus API can be slow to update (10-30 seconds)
# Use 60 seconds to avoid overwhelming the API server
UPDATE_INTERVAL = timedelta(seconds=60)

# Last known state is kept while Salus API fails for a shorter time
STALE_DATA_TOLERANCE = timedelta(minutes=10)

# The gateway uploads every attribute again every few minutes even when nothing changed; values last
# uploaded longer ago than this are what an offline thermostat said last, and the API keeps serving
# them. Measured on the live estate 2026-09-24: healthy devices 1-8 minutes, an offline one six days.
# `presenceInfo` and the `online` attribute are no help: both read 0 on thermostats uploading fine.
DEVICE_OFFLINE_AFTER = timedelta(minutes=30)

# Seconds after a command when the state is fetched to confirm it
CONFIRM_REFRESH_DELAYS = (5, 20)

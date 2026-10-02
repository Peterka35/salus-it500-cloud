"""Constants for the Salus iT500 integration."""

from datetime import timedelta

DOMAIN = "salusfy"

# Update interval for polling
# Salus API can be slow to update (10-30 seconds)
# Use 60 seconds to avoid overwhelming the API server
UPDATE_INTERVAL = timedelta(seconds=60)

# Last known state is kept while Salus API fails for a shorter time
STALE_DATA_TOLERANCE = timedelta(minutes=10)

# A thermostat is offline when the cloud's `presenceInfo` says its gateway is gone and its values were
# uploaded longer ago than this; the API keeps serving what an offline thermostat said last.
# The upload time alone is no heartbeat: the gateway uploads an attribute only when it changes. The
# 2026-09-24 measurement (healthy devices 1-8 minutes) was taken the day programs were written to every
# zone; afterwards a steady zone held at 15 °C went 14 hours without an upload, and the 30-minute rule
# turned the six thermostats unavailable 350 times in a week. `presenceInfo` alone is not enough either:
# it read 0 on gateways uploading normally on 2026-09-24, so a fresh upload outweighs it.
DEVICE_OFFLINE_AFTER = timedelta(minutes=30)

# Seconds after a command when the state is fetched to confirm it
CONFIRM_REFRESH_DELAYS = (5, 20)

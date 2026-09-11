"""Constants for the Salus iT500 integration."""

from datetime import timedelta

DOMAIN = "salusfy"

# Update interval for polling
# Salus API can be slow to update (10-30 seconds)
# Use 60 seconds to avoid overwhelming the API server
UPDATE_INTERVAL = timedelta(seconds=60)

# Last known state is kept while Salus API fails for a shorter time
STALE_DATA_TOLERANCE = timedelta(minutes=10)

# Seconds after a command when the state is fetched to confirm it
CONFIRM_REFRESH_DELAYS = (5, 20)

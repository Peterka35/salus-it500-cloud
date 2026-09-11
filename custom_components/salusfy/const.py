"""Constants for the Salus iT500 integration."""
from datetime import timedelta

DOMAIN = "salusfy"

# Update interval for polling
# Salus API can be slow to update (10-30 seconds)
# Use 60 seconds to avoid overwhelming the API server
UPDATE_INTERVAL = timedelta(seconds=60)

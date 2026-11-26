"""Constants for TMD WRF Forecast."""

from datetime import timedelta

DOMAIN = "tmd_wrf"
NAME = "TMD WRF Forecast"
ATTRIBUTION = "Model data: Thai Meteorological Department (TMD), NWP-WRF. Unofficial integration, not affiliated with TMD."

CONF_LOCATION_NAME = "name"

UPDATE_INTERVAL = timedelta(minutes=30)
METEOGRAM_REFRESH = timedelta(minutes=55)
REQUEST_TIMEOUT = 30
MAX_PARALLEL = 2  # CSV variables fetched at the same time - be gentle with the TMD server
USER_AGENT = "HomeAssistant-tmd_wrf (+https://github.com/mb26-dev/ha-tmd-wrf)"

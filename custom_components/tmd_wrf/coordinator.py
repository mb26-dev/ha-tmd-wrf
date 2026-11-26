"""Data update coordinator for TMD WRF Forecast."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import wrf
from .api import TmdApi, TmdApiError
from .const import DOMAIN, METEOGRAM_REFRESH, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type TmdConfigEntry = ConfigEntry["TmdCoordinator"]


@dataclass
class TmdData:
    run: str | None = None  # model run of the 3 km data, e.g. "2026112512"
    hourly: list[wrf.Sample] = field(default_factory=list)  # 3 km, hourly, 72 h from the run
    points: list[wrf.Sample] = field(default_factory=list)  # point API, 3-hourly, 7 days
    points_updated: datetime | None = None

    @property
    def samples(self) -> list[wrf.Sample]:
        return wrf.merge(self.hourly, self.points)


class TmdCoordinator(DataUpdateCoordinator[TmdData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.lat = float(entry.data["latitude"])
        self.lon = float(entry.data["longitude"])
        self.api = TmdApi(async_get_clientsession(hass), self.lat, self.lon)
        self._data = TmdData()

    async def _async_update_data(self) -> TmdData:
        d = self._data
        now = dt_util.utcnow()
        errors = []

        # 3 km hourly data: only fetched again when TMD has published a newer run
        try:
            run = await self.api.latest_run(now, newer_than=d.run)
            if run and run != d.run:
                d.hourly = await self.api.hourly(run)
                d.run = run
                _LOGGER.debug("TMD WRF: run %s, %d hourly steps", run, len(d.hourly))
        except TmdApiError as err:
            errors.append(f"3 km data: {err}")

        # point forecast (7 days): small request, refreshed about hourly
        if d.points_updated is None or now - d.points_updated >= METEOGRAM_REFRESH:
            try:
                d.points = await self.api.meteogram()
                d.points_updated = now
            except TmdApiError as err:
                errors.append(f"point forecast: {err}")

        # drop what lies in the past (keep the current step)
        d.hourly = [s for s in d.hourly if (s.time - now).total_seconds() > -3600]
        d.points = [s for s in d.points if (s.time - now).total_seconds() > -3 * 3600]

        if not d.hourly and not d.points:
            raise UpdateFailed("; ".join(errors) or "TMD returned no forecast for this location")
        if errors:
            _LOGGER.warning("TMD WRF: %s", "; ".join(errors))
        return d

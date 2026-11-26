"""HTTP access to the TMD NWP server."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from . import wrf
from .const import MAX_PARALLEL, REQUEST_TIMEOUT, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class TmdApiError(Exception):
    """The TMD server could not be reached or answered with something unexpected."""


class TmdApi:
    def __init__(self, session: aiohttp.ClientSession, lat: float, lon: float) -> None:
        self._session = session
        self.lat = lat
        self.lon = lon
        self._timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        self._headers = {"User-Agent": USER_AGENT}

    async def meteogram(self, name: str = "Home Assistant") -> list[wrf.Sample]:
        params = {"location": name, "lat": f"{self.lat:.4f}", "lon": f"{self.lon:.4f}"}
        try:
            async with self._session.get(wrf.METEOGRAM_URL, params=params, timeout=self._timeout, headers=self._headers) as r:
                if r.status != 200:
                    raise TmdApiError(f"meteogram HTTP {r.status}")
                data = await r.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise TmdApiError(f"meteogram request failed: {err}") from err
        try:
            return wrf.parse_meteogram(data, self.lat, self.lon)
        except ValueError as err:
            raise TmdApiError(str(err)) from err

    async def _range(self, url: str, start: int, end: int) -> tuple[str, int]:
        headers = {**self._headers, "Range": f"bytes={start}-{end}"}
        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as r:
                if r.status not in (200, 206):
                    raise TmdApiError(f"HTTP {r.status} for {url}")
                if r.status == 200:
                    raise TmdApiError(f"{url} ignores range requests")
                total = int(r.headers.get("Content-Range", "/0").rsplit("/", 1)[-1])
                return (await r.read()).decode("utf-8", "replace"), total
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise TmdApiError(f"range request failed for {url}: {err}") from err

    async def run_available(self, run: str) -> bool:
        """A run counts as published when its first and last variable are there."""
        for var in ("t2m", "olr"):
            try:
                async with self._session.get(
                    wrf.csv_url(run, var), headers={**self._headers, "Range": "bytes=0-0"}, timeout=self._timeout
                ) as r:
                    if r.status not in (200, 206):
                        return False
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return False
        return True

    async def latest_run(self, now: datetime | None = None, newer_than: str | None = None) -> str | None:
        for run in wrf.candidate_runs(now or datetime.now(timezone.utc)):
            if newer_than and run <= newer_than:
                return newer_than
            if await self.run_available(run):
                return run
        return None

    async def hourly(self, run: str) -> list[wrf.Sample]:
        """Read every variable at our grid point and combine them into hourly samples."""
        sem = asyncio.Semaphore(MAX_PARALLEL)

        async def one(var: str) -> tuple[str, wrf.PointSeries | None]:
            async with sem:
                try:
                    return var, await wrf.read_point(self._range, wrf.csv_url(run, var), self.lat, self.lon)
                except (TmdApiError, wrf.GridPointError) as err:
                    if var == "t2m":
                        raise
                    _LOGGER.debug("TMD WRF: %s of run %s not available: %s", var, run, err)
                    return var, None

        try:
            results = dict(await asyncio.gather(*(one(v) for v in wrf.VARIABLES)))
        except wrf.GridPointError as err:
            raise TmdApiError(str(err)) from err
        series = {k: v for k, v in results.items() if v is not None}
        return wrf.build_hourly(series, self.lat, self.lon)

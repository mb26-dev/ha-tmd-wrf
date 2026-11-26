"""Pure logic for TMD WRF data - no Home Assistant imports, so it can be tested on its own.

Two TMD sources are combined:

* ``hpc.tmd.go.th/static/csv/<run>/<var>.d02.<run>.csv`` - the 3 km WRF domain, hourly for 72 h.
  One file per variable covers all of Thailand (about 100 MB). Rows are sorted by latitude, then
  longitude, and the server answers HTTP range requests, so a grid point is found with a binary
  search over byte offsets instead of downloading the file.
* ``hpc.tmd.go.th/api/meteogram-data`` - the point forecast behind the TMD meteogram page,
  3-hourly for 7 days. ``rain_1h`` there is the rain of the last 3 hours.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

CSV_URL = "https://hpc.tmd.go.th/static/csv/{run}/{var}.d02.{run}.csv"
METEOGRAM_URL = "https://hpc.tmd.go.th/api/meteogram-data"

# variables read from the 3 km domain
VARIABLES = ("t2m", "rhum", "mslp", "ws10m", "wd10m", "p1h", "dws", "olr")

PROBE = 2048  # bytes read per bisection step (a row is about 520 bytes)
WINDOW = 65536  # bytes read once the search has narrowed down

# (url, first byte, last byte) -> (text, total file size)
RangeFetcher = Callable[[str, int, int], Awaitable[tuple[str, int]]]


class GridPointError(Exception):
    """The requested point is not covered by the file."""


# ---------------------------------------------------------------- model runs


def run_id(t: datetime) -> str:
    return t.strftime("%Y%m%d%H")


def parse_run(run: str) -> datetime:
    return datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def candidate_runs(now: datetime, back_hours: int = 48) -> list[str]:
    """Run ids from the newest possible (00/06/12/18 UTC) backwards."""
    now = now.astimezone(timezone.utc)
    t = now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)
    return [run_id(t - timedelta(hours=6 * k)) for k in range(back_hours // 6 + 1)]


def csv_url(run: str, var: str) -> str:
    return CSV_URL.format(run=run, var=var)


# ---------------------------------------------------------------- grid search


def _parse_time(col: str) -> datetime:
    # "2026-11-25_12:00Z"
    return datetime.strptime(col.strip(), "%Y-%m-%d_%H:%MZ").replace(tzinfo=timezone.utc)


def _num(v: str) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _rows(text: str) -> list[list[str]]:
    """Complete CSV rows of a byte window: drop the partial first and last line."""
    lines = text.split("\n")[1:-1]
    out = []
    for line in lines:
        p = line.strip().split(",")
        if len(p) > 2 and _num(p[0]) is not None and _num(p[1]) is not None:
            out.append(p)
    return out


@dataclass
class PointSeries:
    lat: float
    lon: float
    times: list[datetime]
    values: list[float | None]


async def read_point(fetch: RangeFetcher, url: str, lat: float, lon: float) -> PointSeries:
    """Find the grid point nearest to lat/lon and return its time series."""
    head, size = await fetch(url, 0, 8191)
    header = head.split("\n", 1)[0].strip().split(",")
    if len(header) < 3 or header[0] != "lat":
        raise GridPointError(f"unexpected header in {url}")
    times = [_parse_time(h) for h in header[2:]]

    async def key_at(off: int) -> tuple[float, float]:
        text, _ = await fetch(url, off, min(size - 1, off + PROBE - 1))
        nl = text.find("\n")
        p = text[nl + 1 :].split("\n", 1)[0].split(",")
        return float(p[0]), float(p[1])

    async def bisect(key: tuple[float, float]) -> int:
        lo, hi = 0, max(0, size - PROBE)
        while hi - lo > WINDOW // 2:
            mid = (lo + hi) // 2
            if await key_at(mid) < key:
                lo = mid
            else:
                hi = mid
        return lo

    async def window(start: int) -> list[list[str]]:
        start = max(0, start)
        text, _ = await fetch(url, start, min(size - 1, start + WINDOW - 1))
        return _rows(text)

    # the two latitude rows around the point
    rows = await window(await bisect((lat, -1e9)))
    above = next((float(p[0]) for p in rows if float(p[0]) >= lat), None)
    below = next((float(p[0]) for p in reversed(rows) if float(p[0]) < lat), None)
    lats = [x for x in (above, below) if x is not None]
    if not lats:
        raise GridPointError(f"latitude {lat} not found in {url}")

    best: list[str] | None = None
    best_d = math.inf
    coslat = math.cos(math.radians(lat))
    for row_lat in lats:
        for p in await window(await bisect((row_lat, lon))):
            if float(p[0]) != row_lat:
                continue
            d = math.hypot(float(p[0]) - lat, (float(p[1]) - lon) * coslat)
            if d < best_d:
                best, best_d = p, d
    if best is None or best_d > 0.1:  # about 11 km: outside the model domain
        raise GridPointError(f"no grid point near {lat},{lon} in {url}")
    vals = [_num(v) for v in best[2 : 2 + len(times)]]
    return PointSeries(float(best[0]), float(best[1]), times, vals)


# ---------------------------------------------------------------- physics helpers


def sun_elevation(t: datetime, lat: float, lon: float) -> float:
    """Solar elevation in degrees (NOAA low precision, good to about 0.5 degrees)."""
    rad = math.pi / 180
    d = t.timestamp() / 86400 - 10957.5
    g = (357.529 + 0.98560028 * d) * rad
    q = 280.459 + 0.98564736 * d
    lam = (q + 1.915 * math.sin(g) + 0.02 * math.sin(2 * g)) * rad
    e = (23.439 - 0.00000036 * d) * rad
    ra = math.atan2(math.cos(e) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(e) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    ha = (gmst * 15 + lon) * rad - ra
    return math.asin(math.sin(lat * rad) * math.sin(dec) + math.cos(lat * rad) * math.cos(dec) * math.cos(ha)) / rad


def clear_sky_ghi(elev: float) -> float:
    """Haurwitz clear-sky global horizontal irradiance in W/m2."""
    if elev <= 0:
        return 0.0
    s = math.sin(math.radians(elev))
    return 1098 * s * math.exp(-0.057 / s)


def cloud_cover(dws: float | None, olr: float | None, elev: float) -> float | None:
    """Cloud cover in percent.

    Daytime: from how much of the clear-sky radiation reaches the ground (Kasten-Czeplak,
    k = 1 - 0.75 c^3.4). Night or low sun: from the outgoing long-wave radiation - cold,
    high cloud tops radiate less (about 285 W/m2 clear, 175 W/m2 and below deep convection).
    """
    cs = clear_sky_ghi(elev)
    if dws is not None and cs >= 150:
        k = min(1.0, max(0.0, dws / cs))
        return round(min(1.0, ((1 - k) / 0.75) ** (1 / 3.4)) * 100)
    if olr is not None:
        return round(min(1.0, max(0.0, (285 - olr) / 110)) * 100)
    return None


def dew_point(t: float | None, rh: float | None) -> float | None:
    if t is None or rh is None or rh <= 0:
        return None
    a, b = 17.62, 243.12
    g = math.log(min(rh, 100) / 100) + a * t / (b + t)
    return round(b * g / (a - g), 1)


def apparent_temperature(t: float | None, rh: float | None) -> float | None:
    """NOAA heat index (Rothfusz) in Celsius; plain temperature below 27 C."""
    if t is None:
        return None
    if rh is None or t < 27:
        return round(t, 1)
    f = t * 9 / 5 + 32
    hi = (-42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh - 0.00683783 * f * f
          - 0.05481717 * rh * rh + 0.00122874 * f * f * rh + 0.00085282 * f * rh * rh - 0.00000199 * f * f * rh * rh)
    if rh < 13 and 80 <= f <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(f - 95)) / 17)
    elif rh > 85 and 80 <= f <= 87:
        hi += ((rh - 85) / 10) * ((87 - f) / 5)
    return round((hi - 32) * 5 / 9, 1)


def condition(rain_per_h: float | None, cloud: float | None, olr: float | None, night: bool) -> str:
    """Home Assistant weather condition from rain rate, cloud cover and cloud-top radiation."""
    if rain_per_h is not None and rain_per_h >= 0.3:
        if olr is not None and olr < 200 and rain_per_h >= 1.0:
            return "lightning-rainy"
        return "pouring" if rain_per_h >= 7.6 else "rainy"
    c = 50 if cloud is None else cloud
    if c >= 80:
        return "cloudy"
    if c >= 30:
        return "partlycloudy"
    return "clear-night" if night else "sunny"


def circular_mean(angles: list[float], weights: list[float] | None = None) -> float | None:
    if not angles:
        return None
    w = weights or [1.0] * len(angles)
    x = sum(wi * math.cos(math.radians(a)) for a, wi in zip(angles, w))
    y = sum(wi * math.sin(math.radians(a)) for a, wi in zip(angles, w))
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360)


# ---------------------------------------------------------------- samples


@dataclass
class Sample:
    """One forecast step. ``hours`` is the step length: 1 for the 3 km domain, 3 for the point API."""

    time: datetime
    hours: int
    temperature: float | None
    humidity: float | None
    pressure: float | None
    rain: float | None  # mm within the step
    wind_speed: float | None  # m/s
    wind_bearing: float | None
    radiation: float | None = None  # W/m2
    olr: float | None = None
    cloud: float | None = None
    condition: str | None = None
    dew_point: float | None = None
    apparent: float | None = None


def _fix_units(var: str, vals: list[float | None]) -> list[float | None]:
    present = [v for v in vals if v is not None]
    if not present:
        return vals
    if var == "t2m" and max(present) > 150:  # Kelvin
        return [None if v is None else round(v - 273.15, 2) for v in vals]
    if var == "mslp" and max(present) > 2000:  # Pa
        return [None if v is None else round(v / 100, 1) for v in vals]
    if var == "olr":  # 0 marks a missing value (first step)
        return [None if v is None or v <= 0 else v for v in vals]
    if var in ("p1h", "dws"):
        return [None if v is None else max(0.0, v) for v in vals]
    return vals


def build_hourly(series: dict[str, PointSeries], lat: float, lon: float) -> list[Sample]:
    """Combine the 3 km variables into hourly samples."""
    base = series["t2m"]
    vals = {k: _fix_units(k, s.values) for k, s in series.items()}
    ws, wd = vals.get("ws10m", []), vals.get("wd10m", [])
    pws = [v for v in ws if v is not None]
    pwd = [v for v in wd if v is not None]
    # TMD currently ships the speed in wd10m and the direction in ws10m - tell them apart by range
    if pws and pwd and max(pws) > 60 and max(pwd) <= 60:
        ws, wd = wd, ws

    def at(arr: list[float | None], i: int) -> float | None:
        return arr[i] if i < len(arr) else None

    out = []
    for i, t in enumerate(base.times):
        temp, rh = at(vals["t2m"], i), at(vals.get("rhum", []), i)
        dws, olr, rain = at(vals.get("dws", []), i), at(vals.get("olr", []), i), at(vals.get("p1h", []), i)
        elev = sun_elevation(t - timedelta(minutes=30), lat, lon)
        cloud = cloud_cover(dws, olr, elev)
        night = elev < -0.83
        out.append(Sample(
            time=t, hours=1, temperature=temp, humidity=rh, pressure=at(vals.get("mslp", []), i), rain=rain,
            wind_speed=at(ws, i), wind_bearing=at(wd, i), radiation=dws, olr=olr, cloud=cloud,
            condition=condition(rain, cloud, olr, night), dew_point=dew_point(temp, rh), apparent=apparent_temperature(temp, rh),
        ))
    return out


def parse_meteogram(data: dict, lat: float, lon: float) -> list[Sample]:
    """Samples from the meteogram point API (3-hourly, rain over the last 3 hours)."""
    if data.get("status") != "success":
        raise ValueError(f"meteogram status {data.get('status')!r}")
    out = []
    for p in data.get("series") or []:
        ts = p.get("timestamp_utc")
        if ts is None:
            continue
        t = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        temp, rh, rain = _num(p.get("temperature")), _num(p.get("rh")), _num(p.get("rain_1h"))
        elev = sun_elevation(t - timedelta(minutes=90), lat, lon)
        night = elev < -0.83
        rate = None if rain is None else rain / 3
        out.append(Sample(
            time=t, hours=3, temperature=temp, humidity=rh, pressure=_num(p.get("pressure")), rain=rain,
            wind_speed=_num(p.get("wind_speed")), wind_bearing=_num(p.get("wind_direction")),
            condition=condition(rate, None, None, night),
            dew_point=_num(p.get("dewpoint")) if p.get("dewpoint") is not None else dew_point(temp, rh),
            apparent=apparent_temperature(temp, rh),
        ))
    return out


def merge(hourly: list[Sample], points: list[Sample]) -> list[Sample]:
    """Hourly 3 km samples first, then the point forecast for the time after them."""
    end = hourly[-1].time if hourly else None
    return list(hourly) + [p for p in points if end is None or p.time > end]


def sample_at(samples: list[Sample], now: datetime) -> Sample | None:
    """The step that covers ``now`` (a step ends at its time stamp)."""
    for s in samples:
        if s.time - timedelta(hours=s.hours) < now <= s.time:
            return s
    later = [s for s in samples if s.time >= now]
    return later[0] if later else (samples[-1] if samples else None)


def interpolate(samples: list[Sample], now: datetime, attr: str) -> float | None:
    """Linear interpolation of one attribute between the two steps around ``now``."""
    pts = [(s.time, getattr(s, attr)) for s in samples if getattr(s, attr) is not None]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= now <= t1:
            f = (now - t0) / (t1 - t0) if t1 > t0 else 0
            return round(v0 + (v1 - v0) * f, 1)
    return None


def daily(samples: list[Sample], tz, now: datetime) -> list[dict]:
    """Aggregate samples into local days (only from now on)."""
    days: dict = {}
    for s in samples:
        if s.time <= now:
            continue
        # a step belongs to the day in which it starts
        day = (s.time - timedelta(hours=s.hours)).astimezone(tz).date()
        days.setdefault(day, []).append(s)
    out = []
    today = now.astimezone(tz).date()
    for day, ss in sorted(days.items()):
        hours = sum(s.hours for s in ss)
        if day != today and hours < 12:
            continue  # a cut-off day at the end would show a wrong high and low
        temps = [s.temperature for s in ss if s.temperature is not None]
        if not temps:
            continue
        rain = round(sum(s.rain or 0 for s in ss), 1)
        thunder = any(s.condition == "lightning-rainy" for s in ss)
        clouds = [s.cloud for s in ss if s.cloud is not None and s.condition not in ("clear-night",)]
        cloud = round(sum(clouds) / len(clouds)) if clouds else None
        if thunder and rain >= 5:
            cond = "lightning-rainy"
        elif rain >= 20:
            cond = "pouring"
        elif rain >= 1:
            cond = "rainy"
        elif cloud is not None and cloud >= 80:
            cond = "cloudy"
        elif cloud is not None and cloud < 30:
            cond = "sunny"
        else:
            cond = "partlycloudy"
        ws = [s.wind_speed for s in ss if s.wind_speed is not None]
        wb = [(s.wind_bearing, s.wind_speed or 0.1) for s in ss if s.wind_bearing is not None]
        rh = [s.humidity for s in ss if s.humidity is not None]
        pr = [s.pressure for s in ss if s.pressure is not None]
        dp = [s.dew_point for s in ss if s.dew_point is not None]
        ap = [s.apparent for s in ss if s.apparent is not None]
        out.append({
            "datetime": datetime(day.year, day.month, day.day, tzinfo=tz).isoformat(),
            "condition": cond,
            "temperature": round(max(temps), 1),
            "templow": round(min(temps), 1),
            "precipitation": rain,
            "humidity": round(sum(rh) / len(rh)) if rh else None,
            "pressure": round(sum(pr) / len(pr), 1) if pr else None,
            "dew_point": round(sum(dp) / len(dp), 1) if dp else None,
            "apparent_temperature": round(max(ap), 1) if ap else None,
            "wind_speed": round(max(ws), 1) if ws else None,
            "wind_bearing": circular_mean([a for a, _ in wb], [w for _, w in wb]),
            "cloud_coverage": cloud,
        })
    return out

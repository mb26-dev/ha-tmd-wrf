"""Tests for the pure TMD WRF logic. Run with: python tests/test_wrf.py"""

import asyncio
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tmd_wrf"))
import wrf  # noqa: E402

UTC = timezone.utc
RUN = datetime(2026, 11, 25, 12, tzinfo=UTC)
TIMES = [RUN + timedelta(hours=h) for h in range(73)]

# Real values for Ao Nang (grid point 8.030396, 98.83376), run 2026-11-25 12 UTC
REAL = {
    "t2m": "300.9,298.25,297.82,297.87,297.46,296.87,297.27,297.5,297.58,297.64,297.67,297.6,297.51,297.58,306.2,303.44,302.88,303.62,301.14,302.06,302.59,300.86,301.26,297.7,299.16,298.21,298.33,298.45,298.03,297.52,297.46,297.27,297.21,296.81,296.75,296.6,296.45,299.17,299.34,301.74,302.61,303.32,303.33,301.87,302.02,300.31,300.65,298.86,298.37,298.53,298.47,298.1,298.17,298.04,298.1,297.56,297.23,297.09,297.1,297.12,297.72,298.28,299.55,301.7,302.67,302.77,302.57,301.66,302.12,303.01,300.38,301.7,299.71",
    "rhum": "78,88,91,92,93,94,94,92,89,87,86,85,86,88,54,74,67,64,79,74,70,83,77,91,90,94,91,94,92,93,91,89,92,91,89,90,92,87,92,85,77,74,66,81,78,89,87,89,95,94,94,97,93,90,90,92,94,93,94,95,91,92,88,87,75,77,78,87,76,73,82,79,81",
    "mslp": "1011.2,1012.6,1013,1014.2,1013.5,1013.1,1012.9,1012.4,1011.7,1011.5,1011.5,1012.2,1012.6,1013,1013.4,1013.6,1013.2,1011.8,1011.2,1010.1,1009.3,1009,1010.1,1010.4,1011.5,1012.5,1013.2,1013.7,1013.5,1013,1012.7,1012.3,1011.8,1011.8,1011.7,1012.8,1013.4,1013.8,1014.4,1014.5,1014.1,1012.8,1011.9,1011.1,1010.5,1009.6,1011.4,1012.6,1012.6,1013.3,1014.1,1014.5,1014.5,1013.4,1012.8,1012.5,1012.1,1012.2,1012.2,1013,1013.5,1013.7,1014.4,1014.6,1014.1,1012.9,1011.8,1011.3,1010.6,1010.1,1011.1,1011.5,1012.3",
    # as delivered by TMD: directions in ws10m, speeds in wd10m
    "ws10m": "214,219,223,245,238,221,213,194,199,210,208,223,226,238,242,255,234,200,76,77,83,246,244,34,141,158,186,192,195,208,202,176,189,235,209,227,240,235,246,258,273,261,307,71,49,350,302,331,221,129,155,232,204,199,195,211,204,214,222,224,229,225,235,250,265,303,354,77,237,246,196,216,202",
    "wd10m": "2.43,1.92,2.02,1.43,1.9,1.34,1.58,1.45,1.64,1.83,1.88,1.8,1.68,1.51,1.33,1.71,4.06,2.98,3.4,4.77,4.03,5.94,0.34,2.42,1.51,4.09,1.73,1.83,1.2,1.39,2.04,1.95,2.3,1.75,1.78,1.67,2.06,2.25,2.9,3.24,3.43,3.85,1.4,4.55,4.55,8.33,0.87,0.62,1.34,2.82,1.55,2.31,1.48,2.87,2.9,2.19,1.52,1.63,2.44,2.8,4.02,3.11,3.14,3.01,3.84,2.99,2.92,5.21,11.77,5.53,4.93,6.79,4.62",
    "p1h": "0,0,0.01,0.01,0,0.01,0.01,0,0,0,0,0,0,0,0,0,0,0,0,0.04,0.01,4.91,1.48,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4.61,13.76,3.08,0.08,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.03,0.76,0,0.37,0,0,0",
    "olr": "0,257.64,256.44,243.42,256.54,256.45,230.63,229.67,229.81,230,229.8,230.39,230.67,231.28,258.93,268.6,267.28,268.06,268.53,268.82,269.06,270.78,258.19,111.6,105.58,222.09,260.64,259.59,262.1,263.43,264.53,265.44,265.26,265.26,265.15,265.34,265.06,264.88,268.31,269.94,274.29,273.13,265.64,273.12,274.89,273.72,161.55,83.59,93.76,164.42,266.08,153.71,240.51,265.45,265.89,266.33,267.68,268.35,267.55,268.98,269.81,269.73,270.69,273.37,279.33,280.56,282.77,283.69,274.51,236.25,271.19,122.47,260",
}
AO_NANG = (8.0317, 98.8217)
POINT = (8.030396, 98.83376)


def series(name):
    return [float(x) for x in REAL[name].split(",")]


def dws_series():
    # synthetic but realistic radiation: 85 % of clear sky, real values around noon of day 1
    out = []
    for t in TIMES:
        e = wrf.sun_elevation(t - timedelta(minutes=30), *POINT)
        out.append(round(wrf.clear_sky_ghi(e) * 0.85, 2))
    out[15:21] = [631.01, 804.71, 894.82, 909.6, 848.09, 711.13]
    return out


def make_csv(var, values_at_point):
    """Synthetic d02-like file: rows by latitude, then longitude; the real series at Ao Nang."""
    # grid aligned to the real point, like the TMD domain (about 6 km by 3 km here)
    lats = [round(POINT[0] + 0.054878 * i, 6) for i in range(-50, 80)]
    lons = [round(POINT[1] + 0.0277115 * j, 5) for j in range(-65, 60)]
    lines = ["lat,lon," + ",".join(t.strftime("%Y-%m-%d_%H:%MZ") for t in TIMES)]
    rnd = random.Random(var)
    for la in lats:
        for lo in lons:
            if (la, lo) == POINT:
                vals = values_at_point
            else:
                base = values_at_point[0]
                vals = [round(base + rnd.uniform(-1, 1), 2) for _ in TIMES]
            lines.append(f"{la},{lo}," + ",".join(str(v) for v in vals))
    return "\n".join(lines) + "\n"


class Server:
    def __init__(self):
        self.files = {}
        self.requests = 0

    async def fetch(self, url, a, b):
        self.requests += 1
        data = self.files[url]
        return data[a : b + 1], len(data)


def brute(text, lat, lon):
    best, bd = None, 1e9
    for line in text.split("\n")[1:]:
        if not line:
            continue
        p = line.split(",")
        d = math.hypot(float(p[0]) - lat, (float(p[1]) - lon) * math.cos(math.radians(lat)))
        if d < bd:
            best, bd = (float(p[0]), float(p[1])), d
    return best


def test_search():
    srv = Server()
    url = wrf.csv_url("2026112512", "t2m")
    text = make_csv("t2m", series("t2m"))
    srv.files[url] = text
    ps = asyncio.run(wrf.read_point(srv.fetch, url, *AO_NANG))
    assert (ps.lat, ps.lon) == POINT, (ps.lat, ps.lon)
    assert ps.values[15] == 303.44 and len(ps.values) == 73 and ps.times[0] == RUN
    print(f"  search: Ao Nang found with {srv.requests} range requests on a {len(text) / 1e6:.1f} MB file")
    rnd = random.Random(1)
    for _ in range(25):
        lat, lon = rnd.uniform(5.5, 12.5), rnd.uniform(97.2, 100.4)
        srv.requests = 0
        p = asyncio.run(wrf.read_point(srv.fetch, url, lat, lon))
        assert (p.lat, p.lon) == brute(text, lat, lon), (lat, lon, p.lat, p.lon)
    try:
        asyncio.run(wrf.read_point(srv.fetch, url, 30.0, 98.0))
        raise AssertionError("outside the domain must fail")
    except wrf.GridPointError:
        pass
    print("  search: 25 random points match a full scan, outside domain rejected")


def hourly():
    ser = {k: wrf.PointSeries(*POINT, TIMES, series(k)) for k in REAL}
    ser["dws"] = wrf.PointSeries(*POINT, TIMES, dws_series())
    return wrf.build_hourly(ser, *AO_NANG)


def test_hourly():
    h = hourly()
    s = h[15]  # 2026-11-26 03 UTC = 10:00 local
    assert abs(s.temperature - 30.29) < 0.01, s.temperature
    assert s.wind_speed == 1.71 and s.wind_bearing == 255, (s.wind_speed, s.wind_bearing)  # swap fixed
    assert s.pressure == 1013.6 and s.humidity == 74
    assert h[0].olr is None  # 0 = missing
    assert s.condition in ("sunny", "partlycloudy"), s.condition
    storm = h[46]  # 13.76 mm/h with cloud tops at 84 W/m2
    assert storm.condition == "lightning-rainy", storm.condition
    assert h[21].condition == "lightning-rainy" or h[21].condition == "rainy"
    night = h[5]
    assert night.condition in ("clear-night", "partlycloudy", "cloudy"), night.condition
    assert 20 < s.dew_point < 26 and s.apparent >= s.temperature
    print(f"  hourly: 10:00 {s.temperature:.1f} C, {s.humidity} %, wind {s.wind_speed} m/s from {s.wind_bearing}, {s.condition}, cloud {s.cloud} %")
    print(f"  hourly: storm step {storm.time:%d.%m %H}Z {storm.rain} mm -> {storm.condition}")


MG = {
    "status": "success",
    "series": [
        {"timestamp_utc": int((datetime(2026, 11, 26, 3, tzinfo=UTC) + timedelta(hours=3 * i)).timestamp()),
         "temperature": 29.4 - (i % 8) * 0.6, "dewpoint": 24.5, "rh": 78, "pressure": 1012.5, "rain_1h": [0, 0.3, 7.1, 2.2, 0, 0, 0, 0][i % 8],
         "wind_speed": 2.0, "wind_direction": 240}
        for i in range(57)
    ],
}


def test_meteogram_and_daily():
    pts = wrf.parse_meteogram(MG, *AO_NANG)
    assert len(pts) == 57 and pts[2].condition == "rainy" and pts[2].hours == 3
    h = hourly()
    merged = wrf.merge(h, pts)
    assert merged[len(h) - 1].hours == 1 and merged[len(h)].hours == 3 and merged[len(h)].time > h[-1].time
    now = datetime(2026, 11, 26, 2, 10, tzinfo=UTC)
    tz = ZoneInfo("Asia/Bangkok")
    days = wrf.daily(merged, tz, now)
    assert days[0]["datetime"].startswith("2026-11-26T00:00:00+07:00"), days[0]["datetime"]
    assert len(days) >= 7, len(days)
    d1 = days[1]  # 27 Nov, thunderstorm afternoon in the 3 km data
    assert d1["condition"] == "lightning-rainy" and d1["precipitation"] > 15, d1
    assert d1["temperature"] > d1["templow"]
    cur = wrf.sample_at(merged, now)
    assert cur.time == datetime(2026, 11, 26, 3, tzinfo=UTC)
    rad = wrf.interpolate(merged, now, "radiation")
    assert rad is not None and 0 < rad < 900
    print(f"  daily: {len(days)} days, {d1['datetime'][:10]} {d1['condition']} {d1['templow']}-{d1['temperature']} C {d1['precipitation']} mm, wind max {d1['wind_speed']} m/s from {d1['wind_bearing']}")


def test_runs():
    c = wrf.candidate_runs(datetime(2026, 11, 26, 0, 43, tzinfo=UTC), 24)
    assert c == ["2026112600", "2026112518", "2026112512", "2026112506", "2026112500"], c
    assert wrf.parse_run("2026112512") == RUN
    print("  runs:", ", ".join(c))


if __name__ == "__main__":
    for t in (test_runs, test_search, test_hourly, test_meteogram_and_daily):
        print(t.__name__)
        t()
    print("all tests passed")

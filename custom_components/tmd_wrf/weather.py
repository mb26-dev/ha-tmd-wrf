"""Weather entity for TMD WRF Forecast."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import wrf
from .const import ATTRIBUTION, DOMAIN
from .coordinator import TmdConfigEntry, TmdCoordinator


def device_info(entry: TmdConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Thai Meteorological Department",
        model="NWP-WRF 3 km / point forecast",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://hpc.tmd.go.th/meteogram",
    )


async def async_setup_entry(hass: HomeAssistant, entry: TmdConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([TmdWeather(entry.runtime_data, entry)])


class TmdWeather(SingleCoordinatorWeatherEntity[TmdCoordinator]):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, coordinator: TmdCoordinator, entry: TmdConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_weather"
        self._attr_device_info = device_info(entry)

    @property
    def _now(self) -> wrf.Sample | None:
        return wrf.sample_at(self.coordinator.data.samples, dt_util.utcnow())

    def _interp(self, attr: str) -> float | None:
        return wrf.interpolate(self.coordinator.data.samples, dt_util.utcnow(), attr)

    @property
    def condition(self) -> str | None:
        s = self._now
        if s is None:
            return None
        # the hero icon should follow the sun even when the model step started in daylight
        night = wrf.sun_elevation(dt_util.utcnow(), self.coordinator.lat, self.coordinator.lon) < -0.83
        if s.condition == "sunny" and night:
            return "clear-night"
        if s.condition == "clear-night" and not night:
            return "sunny"
        return s.condition

    @property
    def native_temperature(self) -> float | None:
        return self._interp("temperature")

    @property
    def humidity(self) -> float | None:
        v = self._interp("humidity")
        return None if v is None else round(v)

    @property
    def native_pressure(self) -> float | None:
        return self._interp("pressure")

    @property
    def native_dew_point(self) -> float | None:
        return self._interp("dew_point")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._interp("apparent")

    @property
    def native_wind_speed(self) -> float | None:
        s = self._now
        return s.wind_speed if s else None

    @property
    def wind_bearing(self) -> float | None:
        s = self._now
        return s.wind_bearing if s else None

    @property
    def cloud_coverage(self) -> float | None:
        s = self._now
        return s.cloud if s else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {
            "model_run": wrf.parse_run(d.run).isoformat() if d.run else None,
            "solar_radiation": self._interp("radiation"),
            "hourly_until": d.hourly[-1].time.isoformat() if d.hourly else None,
            "forecast_until": d.samples[-1].time.isoformat() if d.samples else None,
        }

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        now = dt_util.utcnow()
        out: list[Forecast] = []
        for s in self.coordinator.data.samples:
            if s.time <= now - timedelta(hours=1):
                continue
            # HA forecasts are stamped with the start of the step
            f: Forecast = {
                "datetime": (s.time - timedelta(hours=s.hours)).isoformat(),
                "condition": s.condition,
                "native_temperature": s.temperature,
                "native_apparent_temperature": s.apparent,
                "native_dew_point": s.dew_point,
                "humidity": None if s.humidity is None else round(s.humidity),
                "native_pressure": s.pressure,
                "native_precipitation": None if s.rain is None else round(s.rain, 2),
                "native_wind_speed": s.wind_speed,
                "wind_bearing": s.wind_bearing,
                "cloud_coverage": s.cloud,
            }
            out.append(f)
        return out

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.DEFAULT_TIME_ZONE
        out: list[Forecast] = []
        for d in wrf.daily(self.coordinator.data.samples, tz, dt_util.utcnow()):
            out.append({
                "datetime": d["datetime"],
                "condition": d["condition"],
                "native_temperature": d["temperature"],
                "native_templow": d["templow"],
                "native_apparent_temperature": d["apparent_temperature"],
                "native_dew_point": d["dew_point"],
                "humidity": d["humidity"],
                "native_pressure": d["pressure"],
                "native_precipitation": d["precipitation"],
                "native_wind_speed": d["wind_speed"],
                "wind_bearing": d["wind_bearing"],
                "cloud_coverage": d["cloud_coverage"],
            })
        return out

"""Sensors for TMD WRF Forecast."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfIrradiance, UnitOfPrecipitationDepth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import wrf
from .const import ATTRIBUTION
from .coordinator import TmdConfigEntry, TmdCoordinator, TmdData
from .weather import device_info


def _rain_next(hours: int) -> Callable[[TmdData], float | None]:
    def fn(d: TmdData) -> float | None:
        now = dt_util.utcnow()
        end = now + timedelta(hours=hours)
        total, covered = 0.0, 0
        for s in d.samples:
            start = s.time - timedelta(hours=s.hours)
            if s.time <= now or start >= end or s.rain is None:
                continue
            # share of the step that lies inside the window
            a, b = max(start, now), min(s.time, end)
            frac = (b - a).total_seconds() / (s.hours * 3600)
            total += s.rain * frac
            covered += 1
        return round(total, 1) if covered else None

    return fn


def _run(d: TmdData) -> datetime | None:
    return wrf.parse_run(d.run) if d.run else None


@dataclass(frozen=True, kw_only=True)
class TmdSensorDescription(SensorEntityDescription):
    value: Callable[[TmdData], object]


SENSORS: tuple[TmdSensorDescription, ...] = (
    TmdSensorDescription(
        key="solar_radiation",
        translation_key="solar_radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: wrf.interpolate(d.samples, dt_util.utcnow(), "radiation"),
    ),
    TmdSensorDescription(
        key="cloud_coverage",
        translation_key="cloud_coverage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-cloudy",
        value=lambda d: (s.cloud if (s := wrf.sample_at(d.samples, dt_util.utcnow())) else None),
    ),
    TmdSensorDescription(
        key="precipitation_next_24h",
        translation_key="precipitation_next_24h",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
        value=_rain_next(24),
    ),
    TmdSensorDescription(
        key="model_run",
        translation_key="model_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_run,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: TmdConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(TmdSensor(entry.runtime_data, entry, desc) for desc in SENSORS)


class TmdSensor(CoordinatorEntity[TmdCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: TmdSensorDescription

    def __init__(self, coordinator: TmdCoordinator, entry: TmdConfigEntry, desc: TmdSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{desc.key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator.data)

<p align="center">
  <img src="docs/images/banner.jpg" alt="TMD WRF Forecast" width="100%">
</p>

<h1 align="center">🇹🇭 TMD WRF Forecast</h1>

<p align="center">
  <b>The Thai Meteorological Department's own weather model in Home Assistant.</b><br>
  3 km WRF, hourly for three days, then 3-hourly up to seven days - for any place in Thailand.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white" alt="HACS Custom"></a>
  <a href="https://github.com/mb26-dev/ha-tmd-wrf/releases"><img src="https://img.shields.io/badge/release-v0.1.1-blue" alt="Release v0.1.1"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.8%2B-18BCF2?logo=homeassistant&logoColor=white" alt="Home Assistant">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"></a>
  <a href="https://ko-fi.com/mb26dev"><img src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
</p>

---

Global models like ECMWF, GFS or the ones behind Pirate Weather and OpenWeatherMap see Thailand on a coarse grid. The afternoon thunderstorms of the tropics, sea breezes along the coast and rain on the windward side of the mountains happen at a scale they cannot resolve. TMD runs its own regional **WRF** model on a **3 km** grid four times a day and publishes the output openly. This integration brings it into Home Assistant as a normal weather entity.

> [!NOTE]
> Unofficial integration, not affiliated with or endorsed by the Thai Meteorological Department. It reads the files and the point forecast TMD publishes on [hpc.tmd.go.th](https://hpc.tmd.go.th/download). If TMD changes them, the integration may need an update.

## ✨ Features

- **Weather entity** with current conditions and **hourly** and **daily** forecasts - works with every weather card.
- **3 km resolution, hourly** for the next 2-3 days (the WRF *d02* domain), then **3-hourly up to 7 days** from TMD's point forecast.
- **Sensors**
  - **Solar radiation** (W/m²) from the model - useful for solar estimates or surface temperature.
  - **Cloud cover** (%) derived from radiation and cloud-top temperature.
  - **Precipitation next 24 h** (mm).
  - **Model run** (diagnostic): which TMD run the data comes from.
- **Thunderstorm detection**: heavy rain under cold, high cloud tops is shown as *lightning-rainy*.
- **Light on the TMD server**: each 100 MB model file is searched with small range requests (about 30 per file, roughly 250 kB instead of 100 MB), and only when TMD has published a new run.
- English, Thai and German translations.

Pairs well with the [Tropical Weather Card](https://github.com/mb26-dev/ha-tropical-weather): add the entity to its `sources` to compare TMD with the global models, and use the radiation sensor as `solar_radiation`.

## 📦 Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mb26-dev&repository=ha-tmd-wrf&category=integration)

1. Open **HACS** in Home Assistant, search for **TMD WRF Forecast** and install it.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → TMD WRF Forecast**.

<details>
<summary>Not showing up in HACS yet? Add it as a custom repository</summary>

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/mb26-dev/ha-tmd-wrf`, type **Integration**.
2. Install **TMD WRF Forecast** and restart Home Assistant.

</details>

### Manual

Copy `custom_components/tmd_wrf` into your `config/custom_components/` folder and restart Home Assistant.

## ⚙️ Configuration

The setup asks for a name and a location; it suggests your Home Assistant home. The location must lie in the model area - Thailand and the neighbouring parts of Myanmar, Laos, Cambodia and Malaysia. You can add several locations.

Entities for a location named *TMD Ao Nang*:

| Entity | Content |
|---|---|
| `weather.tmd_ao_nang` | Current conditions, hourly and daily forecast |
| `sensor.tmd_ao_nang_solar_radiation` | Global radiation in W/m² |
| `sensor.tmd_ao_nang_cloud_cover` | Cloud cover in % |
| `sensor.tmd_ao_nang_precipitation_next_24_h` | Rain in the next 24 hours in mm |
| `sensor.tmd_ao_nang_model_run` | Start time of the model run (diagnostic) |

The weather entity also carries `model_run`, `solar_radiation`, `hourly_until` and `forecast_until` as attributes.

## 🔬 How it works

| | 3 km domain (hourly) | Point forecast (3-hourly) |
|---|---|---|
| Source | `hpc.tmd.go.th/static/csv/<run>/<variable>.d02.<run>.csv` | `hpc.tmd.go.th/api/meteogram-data` |
| Range | 72 h from the model run | 7 days |
| Variables | temperature, humidity, pressure, rain, wind, solar radiation, outgoing long-wave radiation | temperature, dew point, humidity, pressure, rain, wind |
| Update | new run checked every 30 min (00, 06, 12, 18 UTC runs) | about hourly |

- TMD publishes a run several hours after its start time, so the hourly part usually reaches 50-60 hours ahead; the point forecast continues from there.
- The CSV files are sorted by latitude and longitude. The integration finds the nearest grid point with a binary search over byte ranges and never downloads a whole file.
- **Condition**: rain rate first (≥ 0.3 mm/h rainy, ≥ 7.6 mm/h pouring, ≥ 1 mm/h under cloud tops colder than 200 W/m² thunderstorm). Otherwise cloud cover: by day from how much of the clear-sky radiation reaches the ground, at night from the outgoing long-wave radiation.
- **Feels like** is the NOAA heat index, **dew point** the Magnus formula.
- TMD does not publish a rain probability or a UV index, so those forecast fields stay empty.

## 🧪 Development

```bash
python tests/test_wrf.py   # grid search, units, conditions, daily aggregation (no Home Assistant needed)
python brand_src/make_brand.py   # brand images
```

## 📄 License

MIT - see [LICENSE](LICENSE). Model data © Thai Meteorological Department.

"""
modules/tool_usage/weather_tool.py
-------------------------------------
Live weather fetcher backed by OpenWeatherMap 5-day/3-hour Forecast API.

Endpoint:
    GET https://api.openweathermap.org/data/2.5/forecast
        ?lat={lat}&lon={lon}&appid={key}&units=metric&cnt=1

No OAuth — plain API key in `appid` query param.

OWM condition code → internal severity string mapping
──────────────────────────────────────────────────────
  2xx  Thunderstorm           → "thunderstorm"   (0.90)
  3xx  Drizzle                → "drizzle"        (0.55)
  500  Light rain             → "rainy"          (0.65)
  501  Moderate rain          → "rainy"          (0.65)
  502-504 Heavy/extreme rain  → "heavy_rain"     (0.80)
  511  Freezing rain          → "heavy_rain"     (0.80)
  520-531 Shower rain         → "rainy"          (0.65)
  600-602 Snow                → "snow"           (0.70)
  611+  Heavy snow/sleet      → "blizzard"       (1.00)
  7xx  Atmosphere (fog/haze)  → "foggy"          (0.40)
  800  Clear sky              → "clear"          (0.00)
  801  Few clouds (11-25%)    → "mostly_clear"   (0.10)
  802-803 Scattered/broken    → "cloudy"         (0.30)
  804  Overcast               → "overcast"       (0.45)

Source: 06-ingestion-pipeline.md § 1.6, 07-simplified-model.md § HC_5
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# OWM code → internal condition string
# ─────────────────────────────────────────────────────────────────────────────

def _owm_code_to_condition(code: int) -> str:
    """
    Map an OpenWeatherMap weather condition code to our internal condition string.
    Codes: https://openweathermap.org/weather-conditions
    """
    if 200 <= code < 300:
        return "thunderstorm"
    if 300 <= code < 400:
        return "drizzle"
    if code in (500, 501, 520, 521, 522, 531):
        return "rainy"
    if code in (502, 503, 504, 511):
        return "heavy_rain"
    if 600 <= code <= 602 or code == 620:
        return "snow"
    if 611 <= code <= 616 or code in (621, 622):
        return "blizzard"
    if 700 <= code < 800:
        return "foggy"
    if code == 800:
        return "clear"
    if code == 801:
        return "mostly_clear"
    if code in (802, 803):
        return "cloudy"
    if code == 804:
        return "overcast"
    return "cloudy"  # safe default for unknown codes


# Severity table mirrors condition_monitor.WEATHER_SEVERITY
_CONDITION_SEVERITY: dict[str, float] = {
    "clear":        0.00,
    "mostly_clear": 0.10,
    "cloudy":       0.30,
    "overcast":     0.45,
    "drizzle":      0.55,
    "rainy":        0.65,
    "heavy_rain":   0.80,
    "thunderstorm": 0.90,
    "stormy":       1.00,
    "hail":         1.00,
    "snow":         0.70,
    "blizzard":     1.00,
    "foggy":        0.40,
    "hot":          0.35,
    "heatwave":     0.65,
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeatherReading:
    """
    Parsed weather reading from OWM.

    All fields align with `disruption_events.metadata` JSONB spec
    (06-ingestion-pipeline.md § 1.6).
    """
    condition: str           # internal string, e.g. "thunderstorm"
    severity: float          # [0, 1]; ready for ConditionMonitor.check()
    condition_code: int      # raw OWM weather code
    wind_speed_ms: float     # m/s — from OWM `wind.speed`
    precipitation_mm: float  # mm in 3h window — OWM `rain.3h` or `snow.3h`
    forecast_time: str       # ISO datetime string from OWM `dt_txt`
    is_stub: bool = False    # True when returned by stub path
    raw: dict = field(default_factory=dict)   # full OWM list item

    def to_metadata(self) -> dict:
        """Serialize to disruption_events.metadata JSONB format."""
        return {
            "condition_code":    self.condition_code,
            "condition":         self.condition,
            "severity":          round(self.severity, 4),
            "wind_speed_ms":     self.wind_speed_ms,
            "precipitation_mm":  self.precipitation_mm,
            "forecast_time":     self.forecast_time,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WeatherTool
# ─────────────────────────────────────────────────────────────────────────────

class WeatherTool:
    """Returns OpenWeatherMap-shaped readings from hardcoded stub data."""

    def __init__(self) -> None:
        pass

    def fetch(self, lat: float, lon: float, **kwargs):
        """Return stub weather reading."""
        print(f"  [WeatherTool] Returning stub weather data for ({lat:.4f}, {lon:.4f})")
        return self._stub_reading()


    @staticmethod
    def _stub_reading() -> WeatherReading:
        """Return a benign 'clear' stub reading for testing / offline use."""
        return WeatherReading(
            condition      = "clear",
            severity       = 0.00,
            condition_code = 800,
            wind_speed_ms  = 1.0,
            precipitation_mm = 0.0,
            forecast_time  = "stub",
            is_stub        = True,
        )

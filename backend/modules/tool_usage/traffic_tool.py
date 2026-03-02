"""
modules/tool_usage/traffic_tool.py
-------------------------------------
Live traffic-aware travel time fetcher backed by Google Routes API.

Endpoint:
    POST https://routes.googleapis.com/v1/computeRoutes
    Headers:
        X-Goog-Api-Key: {GOOGLE_PLACES_API_KEY}
        X-Goog-FieldMask: routes.duration,routes.staticDuration
        Content-Type: application/json
    Body:
        {
          "origin":      {"location": {"latLng": {"latitude": ..., "longitude": ...}}},
          "destination": {"location": {"latLng": {"latitude": ..., "longitude": ...}}},
          "travelMode": "DRIVE",
          "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
        }

Response fields:
    routes[0].duration       → "Ns"  traffic-aware travel time
    routes[0].staticDuration → "Ns"  baseline (no traffic) travel time

Derived fields (06-ingestion-pipeline.md § 1.7):
    dij_base_seconds  = int(staticDuration[:-1])
    dij_new_seconds   = int(duration[:-1])
    traffic_level     = (dij_new - dij_base) / dij_base   (ratio ≥ 0)
    delay_minutes     = (dij_new - dij_base) / 60

The same Google API key is used (Routes API must be enabled in Cloud Console).
Cost: $0.01/request (Advanced Routes SKU).

Source: 06-ingestion-pipeline.md § 1.7, copilot-instructions.md Traffic section.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrafficReading:
    """
    Parsed traffic reading from Google Routes API.

    All derived fields align with `disruption_events.metadata` JSONB spec
    (06-ingestion-pipeline.md § 1.7).
    """
    traffic_level: float      # (dij_new - dij_base) / dij_base; 0.0 = no delay
    delay_minutes: float      # (dij_new - dij_base) / 60
    dij_base_seconds: int     # baseline travel time (no traffic) [seconds]
    dij_new_seconds: int      # actual travel time under traffic [seconds]
    dij_base_minutes: float   # convenience: dij_base_seconds / 60
    dij_new_minutes: float    # convenience: dij_new_seconds  / 60
    is_stub: bool = False
    raw: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        """Serialize to disruption_events.metadata JSONB format."""
        return {
            "dij_base_seconds": self.dij_base_seconds,
            "dij_new_seconds":  self.dij_new_seconds,
            "traffic_level":    round(self.traffic_level, 4),
            "delay_minutes":    round(self.delay_minutes, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: parse Google "Ns" duration string → int seconds
# ─────────────────────────────────────────────────────────────────────────────

def _parse_duration_s(value: str) -> int:
    """
    Parse Google Routes duration string to integer seconds.
    Format: "123s" or "123.456s"
    """
    s = value.strip().rstrip("s")
    return int(float(s))


# ─────────────────────────────────────────────────────────────────────────────
# TrafficTool
# ─────────────────────────────────────────────────────────────────────────────

class TrafficTool:
    """Returns Google-Routes-shaped traffic readings from hardcoded stub data."""

    def __init__(self) -> None:
        pass

    def fetch(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        **kwargs,
    ):
        """Return stub traffic reading."""
        print(
            f"  [TrafficTool] Returning stub traffic data "
            f"({origin_lat:.4f},{origin_lon:.4f}) -> ({dest_lat:.4f},{dest_lon:.4f})"
        )
        return self._stub_reading(origin_lat, origin_lon, dest_lat, dest_lon)


    @staticmethod
    def _stub_reading(
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> TrafficReading:
        """
        Return a zero-traffic stub for testing / offline use.
        Estimates baseline from haversine at 20 km/h urban driving speed.
        """
        import math
        r     = 6371.0
        phi1, phi2 = math.radians(origin_lat), math.radians(dest_lat)
        dphi  = math.radians(dest_lat - origin_lat)
        dlam  = math.radians(dest_lon - origin_lon)
        a     = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        km    = 2 * r * math.asin(math.sqrt(a))
        base_s = int((km / 20.0) * 3600)    # 20 km/h urban driving

        return TrafficReading(
            traffic_level     = 0.0,
            delay_minutes     = 0.0,
            dij_base_seconds  = base_s,
            dij_new_seconds   = base_s,
            dij_base_minutes  = base_s / 60.0,
            dij_new_minutes   = base_s / 60.0,
            is_stub           = True,
        )

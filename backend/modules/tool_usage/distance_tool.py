"""
modules/tool_usage/distance_tool.py
-------------------------------------
Travel-time tool using the Haversine formula with a configurable walking speed.
No external HTTP calls are made.

Config knob (config.py):
  OSRM_FALLBACK_SPEED_KMH -- walking speed used for distance calculations (default: 4.5)
"""

from __future__ import annotations
import math
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure maths
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points (Haversine formula) in km."""
    r = _EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _km_to_minutes(km: float, speed_kmh: float) -> float:
    """Straight-line km to minutes at a given speed."""
    return (km / speed_kmh) * 60.0


# ---------------------------------------------------------------------------
# DistanceTool
# ---------------------------------------------------------------------------


class DistanceTool:
    """
    Computes travel times between lat/lon points using the Haversine formula
    plus a configurable walking speed (config.OSRM_FALLBACK_SPEED_KMH).
    No external HTTP calls are made.
    """

    def __init__(self) -> None:
        self.fallback_speed: float = config.OSRM_FALLBACK_SPEED_KMH  # km/h

    def travel_time_minutes(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        mode: Optional[str] = None,
    ) -> float:
        """Return travel time in minutes between two points using Haversine."""
        if lat1 == lat2 and lon1 == lon2:
            return 0.0
        km = haversine_km(lat1, lon1, lat2, lon2)
        return _km_to_minutes(km, self.fallback_speed)

    def travel_time_matrix(
        self,
        coords: list[tuple[float, float]],
        mode: Optional[str] = None,
    ) -> list[list[float]]:
        """Return a full n x n travel-time matrix [minutes]."""
        n = len(coords)
        if n == 0:
            return []
        return self._haversine_matrix(coords)

    def calculate(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return Haversine distance in km (backward-compatible)."""
        return haversine_km(lat1, lon1, lat2, lon2)

    # -------------------------------------------------------------------------
    # Private
    # -------------------------------------------------------------------------

    def _haversine_matrix(self, coords: list[tuple[float, float]]) -> list[list[float]]:
        """Full n x n matrix using Haversine + fallback speed."""
        n = len(coords)
        return [
            [
                0.0 if i == j
                else _km_to_minutes(
                    haversine_km(
                        coords[i][0], coords[i][1],
                        coords[j][0], coords[j][1],
                    ),
                    self.fallback_speed,
                )
                for j in range(n)
            ]
            for i in range(n)
        ]

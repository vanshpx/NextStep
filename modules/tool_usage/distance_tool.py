"""
modules/tool_usage/distance_tool.py
-------------------------------------
Arithmetic tool: calculates distance between two geographic coordinates.
Local computation — no external API required (architecture doc confirms this is an arithmetic tool).

TODO (MISSING from architecture doc):
  - Distance unit not specified (km assumed; configurable via config.DISTANCE_UNIT).
  - Whether road distance (routed) or straight-line (haversine) is expected.
    Currently implements haversine (straight-line). Replace with Google Maps Distance
    Matrix API call if road distance is required.
"""

from __future__ import annotations
import math
import config


# Earth radius constants
_EARTH_RADIUS_KM = 6371.0
_EARTH_RADIUS_MILES = 3958.8


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute great-circle distance between two points using the Haversine formula.

    Args:
        lat1, lon1: Coordinates of point A (decimal degrees).
        lat2, lon2: Coordinates of point B (decimal degrees).

    Returns:
        Distance in kilometres.
    """
    r = _EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class DistanceTool:
    """
    Wraps distance calculation logic.
    Provides a consistent interface matching the Tool-usage Module pattern.
    """

    def __init__(self, unit: str = config.DISTANCE_UNIT):
        # Default to km if unit is not yet specified
        self.unit = unit if unit != "UNSPECIFIED" else "km"

    def calculate(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Compute distance between two geographic points.

        Args:
            lat1, lon1: Start point (decimal degrees).
            lat2, lon2: End point (decimal degrees).

        Returns:
            Distance in self.unit.
        """
        km = haversine_km(lat1, lon1, lat2, lon2)
        if self.unit == "miles":
            return km * 0.621371
        return km  # default: km

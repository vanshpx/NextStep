"""
modules/tool_usage/restaurant_tool.py
---------------------------------------
Fetches real-time restaurant data from an external API.
Called by Recommendation Module during Stage 3.

TODO (MISSING from architecture doc):
  - Exact API endpoint and provider
  - Request/response schema
  - Rate limits
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import requests
import config


@dataclass
class RestaurantRecord:
    """
    Single restaurant returned from the API.

    Fields used by Hard Constraints (HC registry):
      cuisine_type / cuisine_tags  — hc1: dietary match (cuisine ∩ user_preferences ≠ ∅)
      opening_hours                — hc2: must be open at meal time
      avg_price_per_person         — hc3: ≤ per_meal_budget
      wheelchair_accessible        — hc4: if traveler requires it

    Fields used by Soft Constraints (SC scoring):
      rating                       — sc1: normalized quality score
      cuisine_tags                 — sc2: finer-grained cuisine preference match
      accepts_reservations         — sc3: bonus if user prefers reserved seating
    """
    name: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    cuisine_type: str = ""              # primary cuisine e.g. "Indian" | "Italian"
    cuisine_tags: list[str] = field(default_factory=list)
    # ^ fine-grained tags e.g. ["north_indian", "vegetarian_friendly", "street_food"]
    rating: float = 0.0                 # scale 1–5
    avg_price_per_person: float = 0.0   # cost per person per meal
    opening_hours: str = ""             # "HH:MM-HH:MM" format
    accepts_reservations: bool = False
    wheelchair_accessible: bool = True  # default True (unknown → allow)
    raw: dict = field(default_factory=dict)


class RestaurantTool:
    """Wraps the external Restaurant API."""

    def __init__(self, api_url: str = config.RESTAURANT_API_URL, api_key: str = config.SERPAPI_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def fetch(self, location: str, **kwargs: Any) -> list[RestaurantRecord]:
        """
        Fetch restaurants near a location.

        Args:
            location: City or coordinate string.
            **kwargs: cuisine_type, price_range, rating_min, etc.
                      TODO: MISSING — full parameter schema.
        """
        # TODO: Replace entire `if` block with real API call once endpoint/schema is known.
        if self.api_url == "UNSPECIFIED":
            print("  [DUMMY API] RestaurantTool.fetch() — returning hardcoded stub data.")
            return [
                RestaurantRecord(
                    name="Spice Garden", location_lat=28.6120, location_lon=77.2110,
                    cuisine_type="Indian",
                    cuisine_tags=["north_indian", "vegetarian_friendly", "local_cuisine"],
                    rating=4.3, avg_price_per_person=400.0,
                    opening_hours="11:00-23:00", accepts_reservations=True,
                    wheelchair_accessible=True,
                ),
                RestaurantRecord(
                    name="The Rooftop Bistro", location_lat=28.6090, location_lon=77.2060,
                    cuisine_type="Continental",
                    cuisine_tags=["continental", "fine_dining"],
                    rating=4.6, avg_price_per_person=1800.0,  # exceeds budget → HC hc3 blocks
                    opening_hours="12:00-23:00", accepts_reservations=True,
                    wheelchair_accessible=False,
                ),
                RestaurantRecord(
                    name="Street Bites", location_lat=28.6160, location_lon=77.2130,
                    cuisine_type="Indian",
                    cuisine_tags=["street_food", "local_cuisine", "budget"],
                    rating=3.9, avg_price_per_person=150.0,
                    opening_hours="08:00-22:00", accepts_reservations=False,
                    wheelchair_accessible=True,
                ),
                RestaurantRecord(
                    name="Punjabi Dhaba", location_lat=28.6170, location_lon=77.2080,
                    cuisine_type="Indian",
                    cuisine_tags=["north_indian", "non_veg", "local_cuisine"],
                    rating=4.1, avg_price_per_person=300.0,
                    opening_hours="10:00-22:30", accepts_reservations=False,
                    wheelchair_accessible=True,
                ),
            ]

        params: dict[str, Any] = {
            "location": location,
            "api_key": self.api_key,
        }
        params.update(kwargs)

        response = requests.get(self.api_url, params=params, timeout=10)
        response.raise_for_status()
        raw_data: list[dict] = response.json()  # TODO: MISSING — actual response key path

        return [self._parse_record(item) for item in raw_data]

    @staticmethod
    def _parse_record(item: dict) -> RestaurantRecord:
        """TODO: MISSING — replace placeholder keys with actual API response keys."""
        return RestaurantRecord(
            name=item.get("name", ""),
            location_lat=item.get("lat", 0.0),
            location_lon=item.get("lon", 0.0),
            cuisine_type=item.get("cuisine", ""),
            cuisine_tags=item.get("cuisine_tags", []),
            rating=item.get("rating", 0.0),
            avg_price_per_person=item.get("avg_cost", 0.0),
            opening_hours=item.get("opening_hours", ""),
            accepts_reservations=item.get("reservations", False),
            wheelchair_accessible=item.get("wheelchair_accessible", True),
            raw=item,
        )

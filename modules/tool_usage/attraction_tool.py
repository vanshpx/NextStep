"""
modules/tool_usage/attraction_tool.py
--------------------------------------
Fetches real-time attraction data from an external API (e.g., SerpAPI).
Called by Recommendation Module during Stage 3 (Information Gathering).

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
class AttractionRecord:
    """
    Single attraction returned from the API.

    Fields used by Hard Constraints (HC registry):
      opening_hours           — hc1: must be open at visit time
      visit_duration_minutes  — hc2: elapsed + Dij + STi ≤ Tmax
      min_visit_duration_minutes — hc8: can't rush visit below this
      wheelchair_accessible   — hc3: checked if traveler needs it
      min_age                 — hc4: traveler age ≥ min_age
      ticket_required         — hc5: permit availability gate
      min_group_size          — hc6: group must meet venue minimum
      max_group_size          — hc6: group must not exceed venue maximum
      seasonal_open_months    — hc7: trip month must be in open months

    Fields used by Soft Constraints (SC scoring):
      optimal_visit_time      — sc1: time-of-day preference alignment
      category                — sc3: interest/category match with user
      is_outdoor              — sc4: crowd avoidance + time-of-day bonus
      intensity_level         — sc5: energy management (heavy_travel_penalty)
    """
    name: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    opening_hours: str = ""           # "HH:MM-HH:MM" format
    rating: float = 0.0               # scale 1–5
    visit_duration_minutes: int = 60  # typical visit duration [minutes]
    entry_cost: float = 0.0           # cost per person
    category: str = ""                # "museum" | "park" | "landmark" | "temple" | "market" ...
    optimal_visit_time: str = ""      # "HH:MM-HH:MM" — best time window

    # ── HC fields (group, age, permits, seasonal) ─────────────────────────────
    min_visit_duration_minutes: int = 15
    # ^ minimum time to have a meaningful visit; enforces hc8 in registry
    wheelchair_accessible: bool = True
    # ^ default True (unknown → allow) — hc3
    min_age: int = 0                  # hc4: 0 = no restriction
    ticket_required: bool = False     # hc5
    min_group_size: int = 1           # hc6: smallest group allowed
    max_group_size: int = 999         # hc6: largest group allowed (999 = unlimited)
    seasonal_open_months: list[int] = field(default_factory=list)
    # ^ hc7: list of calendar months (1–12) when attraction is open.
    # Empty list means open all year.

    # ── SC fields ─────────────────────────────────────────────────────────────
    is_outdoor: bool = False
    # ^ sc4: outdoor venues get crowd-avoidance penalty mid-day if avoid_crowds=True
    intensity_level: str = "low"
    # ^ sc5: "low" | "medium" | "high"
    # high-intensity attractions are penalised on arrival/departure days
    # when SoftConstraints.heavy_travel_penalty is True.

    # ── Historical / cultural importance ──────────────────────────────────────
    historical_importance: str = ""
    # ^ Shown to user when crowd levels are dangerously high and no rescheduling
    # is possible — lets traveller make an informed skip/go decision.

    raw: dict = field(default_factory=dict)


class AttractionTool:
    """
    Wraps the external Attraction API.
    Uses hard constraints (destination, dates) to query real-time data.
    """

    def __init__(self, api_url: str = config.ATTRACTION_API_URL, api_key: str = config.SERPAPI_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def fetch(self, destination: str, **kwargs: Any) -> list[AttractionRecord]:
        """
        Fetch attractions for a given destination.

        Args:
            destination: Target city or location string.
            **kwargs: Additional hard constraint fields (dates, group size, etc.)

        Returns:
            List of AttractionRecord objects.

        TODO: MISSING — full parameter schema from API documentation.
        TODO: MISSING — pagination, max results, and rate-limit handling.
        """
        # TODO: Replace entire `if` block with real API call once endpoint/schema is known.
        if self.api_url == "UNSPECIFIED":
            print("  [DUMMY API] AttractionTool.fetch() — returning hardcoded stub data.")
            return [
                AttractionRecord(
                    name="City Museum", location_lat=28.6139, location_lon=77.2090,
                    opening_hours="09:00-18:00", rating=4.5,
                    visit_duration_minutes=120, min_visit_duration_minutes=45,
                    entry_cost=15.0, category="museum",
                    optimal_visit_time="10:00-14:00",
                    wheelchair_accessible=True, min_age=0,
                    min_group_size=1, max_group_size=50,
                    seasonal_open_months=[],  # open all year
                    is_outdoor=False, intensity_level="low",
                    historical_importance=(
                        "City Museum is one of the oldest urban history museums in the region, "
                        "housing over 12,000 artefacts spanning 500 years of the city's "
                        "founding, trade routes, and cultural evolution. Skipping it means "
                        "missing the only permanent exhibition of pre-colonial city maps."
                    ),
                ),
                AttractionRecord(
                    name="Riverfront Park", location_lat=28.6200, location_lon=77.2150,
                    opening_hours="06:00-20:00", rating=4.2,
                    visit_duration_minutes=90, min_visit_duration_minutes=30,
                    entry_cost=0.0, category="park",
                    optimal_visit_time="07:00-11:00",
                    wheelchair_accessible=True, min_age=0,
                    min_group_size=1, max_group_size=999,
                    seasonal_open_months=[],
                    is_outdoor=True, intensity_level="low",
                    historical_importance=(
                        "Riverfront Park was the site of the historic 1857 assembly ground "
                        "and contains the original riverside ghats used for trade for over "
                        "300 years. Skipping it means missing the open-air heritage walk "
                        "along the only preserved section of the original city waterfront."
                    ),
                ),
                AttractionRecord(
                    name="Heritage Fort", location_lat=28.6050, location_lon=77.2200,
                    opening_hours="08:00-17:00", rating=4.7,
                    visit_duration_minutes=150, min_visit_duration_minutes=60,
                    entry_cost=25.0, category="landmark",
                    optimal_visit_time="09:00-13:00",
                    wheelchair_accessible=False, min_age=0,
                    min_group_size=1, max_group_size=30,
                    seasonal_open_months=[10, 11, 12, 1, 2, 3],  # Oct–Mar (cooler months)
                    is_outdoor=True, intensity_level="medium",
                    historical_importance=(
                        "Heritage Fort is a 16th-century Mughal fortification designated a "
                        "UNESCO World Heritage Site. It contains the only surviving example "
                        "of double-walled Rajput-Mughal hybrid architecture in Northern India "
                        "and houses the royal treasury chamber. Skipping it means missing an "
                        "irreplaceable piece of medieval military and court history."
                    ),
                ),
                AttractionRecord(
                    name="National Gallery of Art", location_lat=28.6120, location_lon=77.2250,
                    opening_hours="10:00-17:00", rating=4.4,
                    visit_duration_minutes=100, min_visit_duration_minutes=40,
                    entry_cost=20.0, category="museum",
                    optimal_visit_time="10:00-14:00",
                    wheelchair_accessible=True, min_age=0,
                    min_group_size=1, max_group_size=60,
                    seasonal_open_months=[],
                    is_outdoor=False, intensity_level="low",
                    historical_importance=(
                        "The National Gallery of Art holds the country's largest collection "
                        "of Mughal miniature paintings (1,800+ works) and features the "
                        "permanent Kalam school exhibition — the only public display of "
                        "royal court manuscripts from the 17th century."
                    ),
                ),
                AttractionRecord(
                    name="Lotus Temple", location_lat=28.5535, location_lon=77.2588,
                    opening_hours="09:00-17:30", rating=4.6,
                    visit_duration_minutes=75, min_visit_duration_minutes=30,
                    entry_cost=0.0, category="landmark",
                    optimal_visit_time="09:00-11:00",
                    wheelchair_accessible=True, min_age=0,
                    min_group_size=1, max_group_size=999,
                    seasonal_open_months=[],
                    is_outdoor=False, intensity_level="low",
                    historical_importance=(
                        "The Lotus Temple is a Bahá'í House of Worship completed in 1986 and "
                        "is one of the most visited buildings in the world. Its 27 free-standing "
                        "marble petals represent the architectural pinnacle of 20th-century "
                        "spiritual design. Skipping it means missing its meditative silence — "
                        "a rare quiet space in the middle of the city."
                    ),
                ),
            ]

        params: dict[str, Any] = {
            "destination": destination,
            "api_key": self.api_key,
            # TODO: MISSING — add date range, category filters, language, etc.
        }
        params.update(kwargs)

        response = requests.get(self.api_url, params=params, timeout=10)
        response.raise_for_status()
        raw_data: list[dict] = response.json()  # TODO: MISSING — actual response key path

        return [self._parse_record(item) for item in raw_data]

    @staticmethod
    def _parse_record(item: dict) -> AttractionRecord:
        """
        Map raw API dict → AttractionRecord.

        TODO: MISSING — replace placeholder keys with actual API response keys.
        """
        return AttractionRecord(
            name=item.get("name", ""),
            location_lat=item.get("lat", 0.0),
            location_lon=item.get("lon", 0.0),
            opening_hours=item.get("opening_hours", ""),
            rating=item.get("rating", 0.0),
            visit_duration_minutes=item.get("duration_minutes", 60),
            min_visit_duration_minutes=item.get("min_duration_minutes", 15),
            entry_cost=item.get("cost", 0.0),
            category=item.get("category", ""),
            optimal_visit_time=item.get("optimal_time", ""),
            wheelchair_accessible=item.get("wheelchair_accessible", True),
            min_age=item.get("min_age", 0),
            ticket_required=item.get("ticket_required", False),
            min_group_size=item.get("min_group_size", 1),
            max_group_size=item.get("max_group_size", 999),
            seasonal_open_months=item.get("seasonal_open_months", []),
            is_outdoor=item.get("is_outdoor", False),
            intensity_level=item.get("intensity_level", "low"),
            historical_importance=item.get("historical_importance", ""),
            raw=item,
        )

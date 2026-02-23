"""
modules/tool_usage/hotel_tool.py
---------------------------------
Fetches hotel data and splits it into static and dynamic layers.

Resolution 1: Static/Dynamic boundary.
  HotelTool → HotelSplitter → StaticHotelData  (star_rating, amenities, location, brand)
                             → DynamicHotelData (price_per_night, available, discounts)

Static data: stable over time; suitable for persistent POI DB cache.
Dynamic data: volatile (TTL-based); must be refreshed on every planning run.

The full HotelRecord is retained for downstream compatibility.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import requests
import config


# ─────────────────────────────────────────────────────────────────────────────
# Resolution 1: Split data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StaticHotelData:
    """
    Hotel fields that are stable over time.
    Store in persistent POI DB; refresh only when source changes.
    """
    name: str = ""
    brand: str = ""                         # hotel chain / brand name
    location_lat: float = 0.0
    location_lon: float = 0.0
    star_rating: float = 0.0               # scale 1–5
    amenities: list[str] = field(default_factory=list)
    check_in_time: str = "14:00"           # HH:MM (TODO: confirm API format)
    check_out_time: str = "11:00"          # HH:MM
    wheelchair_accessible: bool = False
    min_age: int = 0


@dataclass
class DynamicHotelData:
    """
    Hotel fields that change per-query (price, availability, discounts).
    Store in volatile TTL cache; always re-fetched per planning run.
    """
    price_per_night: float = 0.0           # TODO: MISSING — currency unit
    available: bool = True
    discount_pct: float = 0.0             # 0.0 = no discount
    rooms_left: int = 0                    # 0 = unknown
    fetched_at: str = ""                   # ISO-8601 timestamp of last fetch


@dataclass
class HotelRecord:
    """
    Unified hotel record as returned by HotelTool.
    Composed from static + dynamic layers; exposes a flat view for
    downstream modules (recommenders, scoring, HC registry).
    """
    # Static fields
    name: str = ""
    brand: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    star_rating: float = 0.0
    amenities: list[str] = field(default_factory=list)
    check_in_time: str = ""
    check_out_time: str = ""
    wheelchair_accessible: bool = False
    min_age: int = 0
    # Dynamic fields
    price_per_night: float = 0.0
    available: bool = True
    discount_pct: float = 0.0
    rooms_left: int = 0
    # Raw API response (for debugging / forward-compatibility)
    raw: dict = field(default_factory=dict)

    @property
    def static(self) -> StaticHotelData:
        """Extract static layer as a typed object."""
        return StaticHotelData(
            name=self.name, brand=self.brand,
            location_lat=self.location_lat, location_lon=self.location_lon,
            star_rating=self.star_rating, amenities=self.amenities,
            check_in_time=self.check_in_time, check_out_time=self.check_out_time,
            wheelchair_accessible=self.wheelchair_accessible, min_age=self.min_age,
        )

    @property
    def dynamic(self) -> DynamicHotelData:
        """Extract dynamic layer as a typed object."""
        return DynamicHotelData(
            price_per_night=self.price_per_night, available=self.available,
            discount_pct=self.discount_pct, rooms_left=self.rooms_left,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Splitter utility
# ─────────────────────────────────────────────────────────────────────────────

class HotelSplitter:
    """
    Splits a HotelRecord into its static and dynamic components.
    Use at the ingestion boundary:

        record = HotelTool().fetch(...)
        static, dynamic = HotelSplitter.split(record)
        static_store.upsert(static)
        dynamic_cache.set(record.name, dynamic, ttl=300)
    """

    @staticmethod
    def split(record: HotelRecord) -> tuple[StaticHotelData, DynamicHotelData]:
        return record.static, record.dynamic


# ─────────────────────────────────────────────────────────────────────────────
# Tool
# ─────────────────────────────────────────────────────────────────────────────

class HotelTool:
    """Wraps the external Hotel API and returns HotelRecord (flat, pre-split)."""

    def __init__(self, api_url: str = config.HOTEL_API_URL, api_key: str = config.SERPAPI_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def fetch(self, destination: str, check_in: str, check_out: str, **kwargs: Any) -> list[HotelRecord]:
        """
        Fetch hotels. Dynamic fields (price, availability) are live per-call.
        Static fields may be used to seed a persistent POI DB.

        Args:
            destination : Target city string.
            check_in    : Check-in date (ISO-8601 assumed; TODO: confirm).
            check_out   : Check-out date.
            **kwargs    : Filters: star_rating, max_price, etc.
        """
        # TODO: Replace entire `if` block with real API call once endpoint/schema is known.
        if self.api_url == "UNSPECIFIED":
            print("  [DUMMY API] HotelTool.fetch() — returning hardcoded stub data.")
            return [
                HotelRecord(
                    name="The Grand Palace", brand="Luxury Chain",
                    location_lat=28.6100, location_lon=77.2100,
                    star_rating=5.0, amenities=["pool", "spa", "gym", "restaurant"],
                    check_in_time="14:00", check_out_time="12:00",
                    wheelchair_accessible=True,
                    price_per_night=6000.0, available=True, discount_pct=10.0,
                ),
                HotelRecord(
                    name="Budget Inn", brand="Economy Stay",
                    location_lat=28.6150, location_lon=77.2050,
                    star_rating=2.0, amenities=["wifi"],
                    check_in_time="12:00", check_out_time="10:00",
                    wheelchair_accessible=False,
                    price_per_night=1200.0, available=True, discount_pct=0.0,
                ),
                HotelRecord(
                    name="City Comfort Suites", brand="Mid-Range Group",
                    location_lat=28.6080, location_lon=77.2180,
                    star_rating=3.5, amenities=["wifi", "breakfast", "parking"],
                    check_in_time="13:00", check_out_time="11:00",
                    wheelchair_accessible=True,
                    price_per_night=3500.0, available=False, discount_pct=5.0,
                ),
            ]

        params: dict[str, Any] = {
            "destination": destination,
            "check_in": check_in,
            "check_out": check_out,
            "api_key": self.api_key,
        }
        params.update(kwargs)

        response = requests.get(self.api_url, params=params, timeout=10)
        response.raise_for_status()
        raw_data: list[dict] = response.json()   # TODO: MISSING — actual response key path
        return [self._parse_record(item) for item in raw_data]

    @staticmethod
    def _parse_record(item: dict) -> HotelRecord:
        """TODO: MISSING — replace placeholder keys with actual API response keys."""
        return HotelRecord(
            # Static
            name=item.get("name", ""),
            brand=item.get("brand", ""),
            location_lat=item.get("lat", 0.0),
            location_lon=item.get("lon", 0.0),
            star_rating=item.get("stars", 0.0),
            amenities=item.get("amenities", []),
            check_in_time=item.get("check_in_time", ""),
            check_out_time=item.get("check_out_time", ""),
            wheelchair_accessible=item.get("wheelchair_accessible", False),
            min_age=item.get("min_age", 0),
            # Dynamic
            price_per_night=item.get("price_per_night", 0.0),
            available=item.get("available", True),
            discount_pct=item.get("discount_pct", 0.0),
            rooms_left=item.get("rooms_left", 0),
            raw=item,
        )

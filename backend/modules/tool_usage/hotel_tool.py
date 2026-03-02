"""
modules/tool_usage/hotel_tool.py
---------------------------------
Provides hotel data.

Stub mode  (USE_STUB_HOTELS=true)  — hardcoded Booking.com-shaped records.
Live mode  (USE_STUB_HOTELS=false) — calls TBO Hotel API:
    1. POST /CityList           → resolve city name → TBO CityCode
    2. POST /TBOHotelCodeList   → list hotel codes for city
    3. POST /Hoteldetails       → static info (name, coords, star, amenities)
    4. POST /search             → dynamic pricing & availability

Auth: HTTP Basic (TBO_USERNAME : TBO_PASSWORD)

review_score normalization: rating = review_score / 2.0  (0–10 → 0–5)
TBO star string: "5 Star" → 5.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import config

# requests is used only in live mode — imported lazily to keep stub mode dependency-free
try:
    import requests as _requests
    from requests.auth import HTTPBasicAuth as _HTTPBasicAuth
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


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
    rating: float = 0.0           # Booking.com review_score / 2.0 → [0, 5]


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
    rating: float = 0.0           # review_score / 2.0  (Booking.com 0–10 → 0–5)
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
            rating=self.rating,
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


# ── Booking.com stub response ──────────────────────────────────────────────────
# Shaped exactly like a real Booking.com Demand API
# GET /3.1/accommodations/search response.
#
# Booking.com Demand API reference:
#   https://developers.booking.com/demand/
#
# Three realistic hotels covering three star tiers so the HC/SC pipeline
# has dynamic variety:
#   1. The Grand Palace     — 5-star, high price, available       → HC pass | SC high
#   2. Budget Inn           — 2-star, low price, not wheelchair   → HC vary | SC low
#   3. City Comfort Suites  — 4-star, mid price, unavailable      → HC fail (hc: available)

def _make_stub_booking_response(destination: str) -> dict:
    return {
        "data": [
            # ── Property 1: The Grand Palace ─────────────────────────────────
            {
                "accommodation_id": "bk-grand-palace-001",
                "name": "The Grand Palace",
                "location": {
                    "coordinates": {
                        "latitude":  28.6100,
                        "longitude": 77.2100,
                    },
                    "address": {
                        "address_line1": "1 Connaught Place",
                        "city":          "New Delhi",
                        "country_code":  "IN",
                        "zip":           "110001",
                    },
                },
                "property_info": {
                    "accommodation_type": "Luxury Chain",   # used as brand
                    "star_class":       5,                  # 1–5; used as star_rating
                    "facilities":       ["pool", "spa", "gym", "restaurant", "wifi", "parking"],
                    "checkin":          {"from": "14:00", "to": "23:59"},
                    "checkout":         {"from": "07:00", "to": "12:00"},
                },
                "review_score":       9.2,    # 0–10; normalize → rating = 9.2/2 = 4.6
                "review_score_word":  "Wonderful",
                "accessibility": {
                    "wheelchair_accessible_entire_unit": True,
                },
                "min_price_per_night": {"amount": 6000.0, "currency": "INR"},
                "available_rooms":     5,
                "discount_pct":        10.0,    # 10% discount applied
                "min_age_requirement": 0,
            },
            # ── Property 2: Budget Inn ────────────────────────────────────────
            {
                "accommodation_id": "bk-budget-inn-002",
                "name": "Budget Inn",
                "location": {
                    "coordinates": {
                        "latitude":  28.6150,
                        "longitude": 77.2050,
                    },
                    "address": {
                        "address_line1": "45 Railway Colony",
                        "city":          "New Delhi",
                        "country_code":  "IN",
                        "zip":           "110055",
                    },
                },
                "property_info": {
                    "accommodation_type": "Economy Stay",
                    "star_class":       2,
                    "facilities":       ["wifi"],
                    "checkin":          {"from": "12:00", "to": "23:59"},
                    "checkout":         {"from": "07:00", "to": "10:00"},
                },
                "review_score":       6.4,    # → rating = 3.2
                "review_score_word":  "Good",
                "accessibility": {
                    "wheelchair_accessible_entire_unit": False,
                },
                "min_price_per_night": {"amount": 1200.0, "currency": "INR"},
                "available_rooms":     12,
                "discount_pct":        0.0,
                "min_age_requirement": 0,
            },
            # ── Property 3: City Comfort Suites (available_rooms=0) ───────────
            {
                "accommodation_id": "bk-city-comfort-003",
                "name": "City Comfort Suites",
                "location": {
                    "coordinates": {
                        "latitude":  28.6080,
                        "longitude": 77.2180,
                    },
                    "address": {
                        "address_line1": "87 Karol Bagh",
                        "city":          "New Delhi",
                        "country_code":  "IN",
                        "zip":           "110005",
                    },
                },
                "property_info": {
                    "accommodation_type": "Mid-Range Group",
                    "star_class":       4,
                    "facilities":       ["wifi", "breakfast", "parking", "gym"],
                    "checkin":          {"from": "13:00", "to": "23:59"},
                    "checkout":         {"from": "07:00", "to": "11:00"},
                },
                "review_score":       7.8,    # → rating = 3.9
                "review_score_word":  "Very Good",
                "accessibility": {
                    "wheelchair_accessible_entire_unit": True,
                },
                "min_price_per_night": {"amount": 3500.0, "currency": "INR"},
                "available_rooms":     0,     # fully booked → available = False
                "discount_pct":        5.0,
                "min_age_requirement": 0,
            },
        ],
        "meta": {
            "total_count": 3,
            "request_id":  "stub-booking-001",
        },
    }


# ── TBO Hotel API helpers ──────────────────────────────────────────────────────

def _tbo_auth() -> tuple[str, str]:
    """Return (username, password) for TBO Basic Auth."""
    return config.TBO_USERNAME, config.TBO_PASSWORD


def _tbo_post(path: str, body: dict) -> dict:
    """POST to TBO Hotel API base URL with Basic Auth. Raises on HTTP/network error."""
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("'requests' package is not installed. Run: pip install requests")
    url = f"{config.TBO_HOTEL_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    user, pwd = _tbo_auth()
    resp = _requests.post(
        url,
        json=body,
        auth=_HTTPBasicAuth(user, pwd),
        timeout=config.TBO_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _tbo_get_city_code(city_name: str, country_code: str = "IN") -> str:
    """
    Resolve a human city name → TBO CityCode.
    Calls POST /CityList and fuzzy-matches on CityName (case-insensitive, stripped).
    Returns "" if not found.
    """
    try:
        data = _tbo_post("CityList", {"CountryCode": country_code})
    except Exception as exc:
        print(f"  [HotelTool] CityList failed: {exc}")
        return ""

    cities: list[dict] = data.get("CityList", [])
    target = city_name.strip().lower()
    # exact match first
    for c in cities:
        if c.get("CityName", "").lower() == target:
            return str(c.get("CityCode", ""))
    # fallback: starts-with match
    for c in cities:
        if c.get("CityName", "").lower().startswith(target):
            return str(c.get("CityCode", ""))
    return ""


def _tbo_get_hotel_codes(city_code: str, max_hotels: int = 30) -> str:
    """Returns comma-separated TBO hotel codes for city_code (up to max_hotels)."""
    try:
        data = _tbo_post("TBOHotelCodeList", {"CityCode": city_code, "IsDetailedResponse": "true"})
    except Exception as exc:
        print(f"  [HotelTool] TBOHotelCodeList failed: {exc}")
        return ""

    hotel_list: list[dict] = data.get("TBOHotelCodeList", [])
    codes = [str(h.get("TBOHotelCode", "")) for h in hotel_list if h.get("TBOHotelCode")]
    return ",".join(codes[:max_hotels])


def _tbo_get_hotel_details(hotel_codes_str: str) -> dict[str, dict]:
    """
    Returns a dict keyed by hotel code with static info from /Hoteldetails.
    Silently returns {} on failure so search results still work without static data.
    """
    if not hotel_codes_str:
        return {}
    try:
        data = _tbo_post("Hoteldetails", {"Hotelcodes": hotel_codes_str, "Language": "EN"})
    except Exception as exc:
        print(f"  [HotelTool] Hoteldetails failed: {exc}")
        return {}

    result: dict[str, dict] = {}
    for h in data.get("HotelDetails", []):
        code = str(h.get("Hotelcode", h.get("HotelCode", "")))
        if code:
            result[code] = h
    return result


def _tbo_search(
    hotel_codes_str: str,
    check_in: str,
    check_out: str,
    adults: int,
    children: int,
    nationality: str,
) -> list[dict]:
    """
    POST /search → returns list of hotel result dicts.
    Each dict contains HotelCode, HotelName, Price, BookingCode, etc.
    """
    children_ages = [5] * children  # default child age = 5 (TBO requires ChildrenAges)
    body = {
        "CheckIn": check_in,
        "CheckOut": check_out,
        "HotelCodes": hotel_codes_str,
        "GuestNationality": nationality,
        "PaxRooms": [
            {
                "Adults": adults,
                "Children": children,
                "ChildrenAges": children_ages,
            }
        ],
        "ResponseTime": 20.0,
        "IsDetailedResponse": True,
        "Filters": {
            "Refundable": False,
            "NoOfRooms": 0,
            "MealType": 0,
            "OrderBy": 0,
            "StarRating": 0,
            "HotelName": None,
        },
    }
    try:
        data = _tbo_post("search", body)
    except Exception as exc:
        print(f"  [HotelTool] Search failed: {exc}")
        return []

    return data.get("HotelSearchResult", {}).get("HotelResults", [])


def _tbo_star_to_float(star_str: str) -> float:
    """'5 Star' → 5.0, '3 Star' → 3.0, fallback → 0.0"""
    m = re.search(r"(\d+(?:\.\d+)?)", str(star_str))
    return float(m.group(1)) if m else 0.0


# ── HotelTool ─────────────────────────────────────────────────────────────────

class HotelTool:
    """Returns hotel records from stub data (default) or TBO Hotel API (live mode)."""

    def __init__(self) -> None:
        pass

    def fetch(
        self,
        destination: str,
        check_in:  str = "",
        check_out: str = "",
        adults: int = 1,
        children: int = 0,
        nationality: str = "IN",
        **kwargs: Any,
    ) -> list[HotelRecord]:
        """Return hotel records for *destination*.

        Stub mode (USE_STUB_HOTELS=true):
            Returns hardcoded Booking.com-shaped dataset.
        Live mode (USE_STUB_HOTELS=false):
            Chains four TBO calls: CityList → TBOHotelCodeList → Hoteldetails + search.
            Falls back to an empty list with a printed warning on any API error.
        """
        if config.USE_STUB_HOTELS:
            print(f"  [HotelTool] Returning stub hotel data for '{destination}'")
            raw = _make_stub_booking_response(destination)
            properties: list[dict] = raw.get("data", [])
            return [self._parse_property(p) for p in properties]

        # ── Live mode: TBO Hotel API ──────────────────────────────────────────
        print(f"  [HotelTool] Fetching live TBO data for '{destination}' ({check_in} → {check_out})")

        city_code = _tbo_get_city_code(destination, country_code="IN")
        if not city_code:
            print(f"  [HotelTool] WARNING: city '{destination}' not found in TBO CityList — no hotels.")
            return []

        hotel_codes_str = _tbo_get_hotel_codes(city_code)
        if not hotel_codes_str:
            print(f"  [HotelTool] WARNING: no hotel codes found for CityCode={city_code}.")
            return []

        # Fetch static details and live pricing in parallel (sequential here for simplicity)
        details_map = _tbo_get_hotel_details(hotel_codes_str)

        search_results = _tbo_search(
            hotel_codes_str,
            check_in=check_in or "",
            check_out=check_out or "",
            adults=max(adults, 1),
            children=children,
            nationality=nationality,
        )

        if not search_results:
            print("  [HotelTool] WARNING: TBO search returned no results.")
            return []

        records = [
            self._parse_tbo(result, details_map.get(str(result.get("HotelCode", "")), {}))
            for result in search_results
        ]
        print(f"  [HotelTool] {len(records)} live hotel(s) fetched from TBO.")
        return records

    # ── Private: TBO parser ───────────────────────────────────────────────────

    @staticmethod
    def _parse_tbo(result: dict, detail: dict) -> HotelRecord:
        """
        Merge one TBO search result + its Hoteldetails entry → HotelRecord.

        TBO search result paths:
          .HotelCode          → used as key to join with detail
          .HotelName          → name (fallback from detail)
          .HotelCategory      → "5 Star" → star_rating
          .Price.OfferedPriceRoundedOff → price_per_night
          .BookingCode        → stored in raw for booking flow

        TBO Hoteldetails paths:
          .HotelName          → name
          .Latitude/.Longitude → coords
          .HotelCategory      → "5 Star" → star_rating
          .Amenities[].Name   → amenities list
          .CheckInTime/.CheckOutTime → times
        """
        # Name: detail overrides search result
        name = detail.get("HotelName") or result.get("HotelName", "")

        # Star rating from either source ("3 Star" → 3.0)
        star_str = detail.get("HotelCategory") or result.get("HotelCategory", "")
        star_rating = _tbo_star_to_float(star_str)

        # Coordinates — only in Hoteldetails
        try:
            lat = float(detail.get("Latitude", 0.0) or 0.0)
        except (TypeError, ValueError):
            lat = 0.0
        try:
            lon = float(detail.get("Longitude", 0.0) or 0.0)
        except (TypeError, ValueError):
            lon = 0.0

        # Amenities list
        amenities: list[str] = [
            a["Name"] for a in detail.get("Amenities", []) if a.get("Name")
        ]

        # Check-in / check-out
        check_in_time  = detail.get("CheckInTime", "14:00") or "14:00"
        check_out_time = detail.get("CheckOutTime", "11:00") or "11:00"

        # Accessibility — TBO does not expose this field; default False
        wheelchair_accessible = False

        # Pricing from search result
        price_block = result.get("Price", {})
        price_per_night = float(
            price_block.get("OfferedPriceRoundedOff")
            or price_block.get("PublishedPriceRoundedOff", 0.0)
            or 0.0
        )

        # TBO doesn't expose available_rooms directly; treat any result as available
        available = price_per_night > 0

        # Rating: TBO search may include StarRating (numeric); else derive from star_str
        rating_raw = result.get("StarRating") or detail.get("StarRating")
        if rating_raw is not None:
            try:
                # TBO StarRating is already 0–5
                rating = float(rating_raw)
            except (TypeError, ValueError):
                rating = star_rating
        else:
            rating = star_rating  # use star class as proxy

        return HotelRecord(
            name=name,
            brand=detail.get("ChainName", "") or "",
            location_lat=lat,
            location_lon=lon,
            star_rating=star_rating,
            amenities=amenities,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
            wheelchair_accessible=wheelchair_accessible,
            min_age=0,
            rating=rating,
            price_per_night=price_per_night,
            available=available,
            discount_pct=0.0,
            rooms_left=0,
            raw={**result, "_detail": detail},
        )

    # ── Private: Booking.com stub parser ──────────────────────────────────────
    # ── Private: parser (works on real + stub data identically) ──────────────────
    # ── Private: parser (works on real + stub data identically) ──────────────

    @staticmethod
    def _parse_property(p: dict) -> HotelRecord:
        """
        Parse one Booking.com property dict → HotelRecord.

        Booking.com JSON paths read:
          .name                                          → name
          .property_info.accommodation_type             → brand
          .location.coordinates.latitude / .longitude   → lat/lon
          .property_info.star_class                     → star_rating (1–5)
          .property_info.facilities                     → amenities
          .property_info.checkin.from                   → check_in_time
          .property_info.checkout.to                    → check_out_time
          .accessibility.wheelchair_accessible_entire_unit → wheelchair_accessible
          .min_age_requirement                          → min_age
          .review_score / 2.0                           → rating (0–10 → 1–5)
          .min_price_per_night.amount                   → price_per_night
          .available_rooms > 0                          → available
          .discount_pct                                 → discount_pct
          .available_rooms                              → rooms_left
        """
        # ── Coordinates ───────────────────────────────────────────────────────
        coords = p.get("location", {}).get("coordinates", {})
        lat = float(coords.get("latitude",  0.0) or 0.0)
        lon = float(coords.get("longitude", 0.0) or 0.0)

        # ── Property info ─────────────────────────────────────────────────────
        prop_info:  dict = p.get("property_info", {})
        brand:      str  = prop_info.get("accommodation_type", "")
        star_class: float = float(prop_info.get("star_class", 0) or 0)
        amenities:  list  = prop_info.get("facilities", [])

        checkin_time:  str = prop_info.get("checkin",  {}).get("from", "14:00") or "14:00"
        checkout_time: str = prop_info.get("checkout", {}).get("to",   "11:00") or "11:00"

        # ── Accessibility: absent → False (unlike attractions, hotels may not be) ─
        accessibility: dict = p.get("accessibility", {})
        wheelchair_accessible = bool(
            accessibility.get("wheelchair_accessible_entire_unit", False)
        )

        # ── Age restriction ───────────────────────────────────────────────────
        min_age = int(p.get("min_age_requirement", 0) or 0)

        # ── Review score  0–10 → rating 0–5  (source: § 5.3) ──────────────────
        # Note: we store normalized rating separately from star_class.
        # Downstream HC checks use star_class (star_rating field);
        # The rating field is available for SC quality-preference matching.
        review_raw = float(p.get("review_score", 0.0) or 0.0)
        rating = round(review_raw / 2.0, 2)   # e.g. 9.2 → 4.6

        # ── Pricing ───────────────────────────────────────────────────────────
        price_block:     dict  = p.get("min_price_per_night", {})
        price_per_night: float = float(price_block.get("amount", 0.0) or 0.0)

        # ── Availability ──────────────────────────────────────────────────────
        rooms_left: int  = int(p.get("available_rooms", 0) or 0)
        available:  bool = rooms_left > 0

        # ── Discount ──────────────────────────────────────────────────────────
        discount_pct: float = float(p.get("discount_pct", 0.0) or 0.0)

        return HotelRecord(
            name=p.get("name", ""),
            brand=brand,
            location_lat=lat,
            location_lon=lon,
            star_rating=star_class,
            amenities=amenities,
            check_in_time=checkin_time,
            check_out_time=checkout_time,
            wheelchair_accessible=wheelchair_accessible,
            min_age=min_age,
            rating=rating,
            price_per_night=price_per_night,
            available=available,
            discount_pct=discount_pct,
            rooms_left=rooms_left,
            raw=p,
        )

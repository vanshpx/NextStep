"""
modules/tool_usage/flight_tool.py
----------------------------------
Provides flight data.

Stub mode  (USE_STUB_FLIGHTS=true)  — hardcoded Amadeus-shaped records.
Live mode  (USE_STUB_FLIGHTS=false) — calls TBO India Air API:
    1. POST /Authenticate/ValidateAgency → fetch session TokenId (cached per process)
    2. POST /Search/                     → search flights
    3. Response parsed into FlightRecord list sorted by price.

IsDomestic is auto-detected: both origin + destination IATA codes in _INDIA_IATA_CODES → True.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any
import config

# requests used only in live mode
try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ── City name → IATA code mapping (India) ─────────────────────────────────────
_CITY_TO_IATA: dict[str, str] = {
    "delhi": "DEL",       "new delhi": "DEL",
    "mumbai": "BOM",      "bombay": "BOM",
    "bangalore": "BLR",   "bengaluru": "BLR",   "banglore": "BLR",
    "goa": "GOI",
    "jaipur": "JAI",
    "agra": "AGR",
    "kolkata": "CCU",     "calcutta": "CCU",    "kolkatta": "CCU",
    "chennai": "MAA",     "madras": "MAA",      "chenai": "MAA",
    "hyderabad": "HYD",
    "kochi": "COK",       "cochin": "COK",      "kerala": "COK",
    "pune": "PNQ",
    "ahmedabad": "AMD",
    "varanasi": "VNS",
    "amritsar": "ATQ",
    "lucknow": "LKO",
    "patna": "PAT",
    "bhopal": "BHO",
    "indore": "IDR",
    "nagpur": "NAG",
    "srinagar": "SXR",
    "jammu": "IXJ",
    "chandigarh": "IXC",
    "coimbatore": "CJB",
    "visakhapatnam": "VTZ",  "vizag": "VTZ",
    "bhubaneswar": "BBI",
    "trichy": "TRZ",      "tiruchirappalli": "TRZ",
    "udaipur": "UDR",
    "jodhpur": "JDH",
    "ranchi": "IXR",
    "guwahati": "GAU",
    "imphal": "IMF",
    "port blair": "IXZ",
    "dehradun": "DED",
    "leh": "IXL",
    "raipur": "RPR",
    "aurangabad": "IXU",
    "madurai": "IXM",
    "mangalore": "IXE",
    "hubli": "HBX",
    "tirupati": "TIR",
}

_INDIA_IATA_CODES: frozenset[str] = frozenset(_CITY_TO_IATA.values())


def city_to_iata(city_name: str) -> str:
    """Normalise a city name to its IATA code. Returns '' if not found."""
    return _CITY_TO_IATA.get(city_name.strip().lower(), "")


def _is_domestic(origin_iata: str, destination_iata: str) -> bool:
    """Return True when both airports are in India."""
    return origin_iata in _INDIA_IATA_CODES and destination_iata in _INDIA_IATA_CODES


# ── ISO 8601 duration parser ───────────────────────────────────────────────────

def _parse_iso_duration(duration_str: str) -> int:
    """
    Parse an Amadeus ISO 8601 duration string → total minutes.

    Examples:
        "PT2H10M" → 130
        "PT45M"   → 45
        "PT3H"    → 180
        "PT1H30M" → 90
    """
    if not duration_str:
        return 0
    h_match = re.search(r"(\d+)H", duration_str)
    m_match = re.search(r"(\d+)M", duration_str)
    hours   = int(h_match.group(1)) if h_match else 0
    minutes = int(m_match.group(1)) if m_match else 0
    return hours * 60 + minutes


# ── Amadeus stub response ─────────────────────────────────────────────────────
# Shaped exactly like a real Amadeus /v2/shopping/flight-offers response.
# Real Amadeus response reference:
#   https://developers.amadeus.com/self-service/category/flights/api-doc/
#   flight-offers-search/api-reference
#
# Three realistic offers so the HC/SC pipeline has variety to filter:
#   1. IndiGo   6E-201  Economy  direct   3 500 INR  → HC pass | SC high
#   2. Air India AI-101 Business direct   8 500 INR  → HC pass | SC lower (price)
#   3. SpiceJet  SG-801 Economy  1-stop   2 200 INR  → HC pass | SC medium

def _make_stub_amadeus_response(origin: str, destination: str, departure_date: str) -> dict:
    d = departure_date   # "YYYY-MM-DD"
    return {
        "meta": {"count": 3, "links": {"self": "https://api.amadeus.com/v2/shopping/flight-offers"}},
        "data": [
            # ── Offer 1: IndiGo Economy direct ──────────────────────────────
            {
                "type": "flight-offer",
                "id": "1",
                "source": "GDS",
                "itineraries": [
                    {
                        "duration": "PT2H10M",
                        "segments": [
                            {
                                "departure": {"iataCode": origin,      "terminal": "2", "at": f"{d}T06:00:00"},
                                "arrival":   {"iataCode": destination, "terminal": "3", "at": f"{d}T08:10:00"},
                                "carrierCode": "6E",
                                "number":      "201",
                                "aircraft":    {"code": "320"},
                                "operating":   {"carrierCode": "6E"},
                                "duration":    "PT2H10M",
                                "id":          "1",
                                "numberOfStops": 0,
                            }
                        ],
                    }
                ],
                "price": {
                    "currency": "INR",
                    "base": "3000.00",
                    "total": "3500.00",
                    "grandTotal": "3500.00",
                },
                "travelerPricings": [
                    {
                        "travelerId": "1",
                        "fareOption": "STANDARD",
                        "travelerType": "ADULT",
                        "price": {"currency": "INR", "total": "3500.00"},
                        "fareDetailsBySegment": [
                            {"segmentId": "1", "cabin": "ECONOMY", "class": "E"}
                        ],
                    }
                ],
            },
            # ── Offer 2: Air India Business direct ──────────────────────────
            {
                "type": "flight-offer",
                "id": "2",
                "source": "GDS",
                "itineraries": [
                    {
                        "duration": "PT2H15M",
                        "segments": [
                            {
                                "departure": {"iataCode": origin,      "terminal": "1", "at": f"{d}T09:30:00"},
                                "arrival":   {"iataCode": destination, "terminal": "2", "at": f"{d}T11:45:00"},
                                "carrierCode": "AI",
                                "number":      "101",
                                "aircraft":    {"code": "788"},
                                "operating":   {"carrierCode": "AI"},
                                "duration":    "PT2H15M",
                                "id":          "2",
                                "numberOfStops": 0,
                            }
                        ],
                    }
                ],
                "price": {
                    "currency": "INR",
                    "base": "7500.00",
                    "total": "8500.00",
                    "grandTotal": "8500.00",
                },
                "travelerPricings": [
                    {
                        "travelerId": "1",
                        "fareOption": "STANDARD",
                        "travelerType": "ADULT",
                        "price": {"currency": "INR", "total": "8500.00"},
                        "fareDetailsBySegment": [
                            {"segmentId": "2", "cabin": "BUSINESS", "class": "J"}
                        ],
                    }
                ],
            },
            # ── Offer 3: SpiceJet Economy 1-stop ────────────────────────────
            {
                "type": "flight-offer",
                "id": "3",
                "source": "GDS",
                "itineraries": [
                    {
                        "duration": "PT3H30M",
                        "segments": [
                            {
                                # Leg 1: origin → Jaipur (layover)
                                "departure": {"iataCode": origin, "terminal": "1", "at": f"{d}T14:00:00"},
                                "arrival":   {"iataCode": "JAI",  "terminal": "1", "at": f"{d}T15:30:00"},
                                "carrierCode": "SG",
                                "number":      "801",
                                "aircraft":    {"code": "737"},
                                "operating":   {"carrierCode": "SG"},
                                "duration":    "PT1H30M",
                                "id":          "3",
                                "numberOfStops": 0,
                            },
                            {
                                # Leg 2: Jaipur → destination (completing the flight)
                                "departure": {"iataCode": "JAI",  "terminal": "1", "at": f"{d}T16:00:00"},
                                "arrival":   {"iataCode": destination, "terminal": "1", "at": f"{d}T17:30:00"},
                                "carrierCode": "SG",
                                "number":      "802",
                                "aircraft":    {"code": "737"},
                                "operating":   {"carrierCode": "SG"},
                                "duration":    "PT1H30M",
                                "id":          "4",
                                "numberOfStops": 0,
                            },
                        ],
                    }
                ],
                "price": {
                    "currency": "INR",
                    "base": "1800.00",
                    "total": "2200.00",
                    "grandTotal": "2200.00",
                },
                "travelerPricings": [
                    {
                        "travelerId": "1",
                        "fareOption": "STANDARD",
                        "travelerType": "ADULT",
                        "price": {"currency": "INR", "total": "2200.00"},
                        "fareDetailsBySegment": [
                            {"segmentId": "3", "cabin": "ECONOMY", "class": "Q"},
                            {"segmentId": "4", "cabin": "ECONOMY", "class": "Q"},
                        ],
                    }
                ],
            },
        ],
        # Amadeus dictionaries block — same structure as real response
        "dictionaries": {
            "carriers": {
                "6E": "INDIGO",
                "AI": "AIR INDIA",
                "SG": "SPICEJET",
                "UK": "VISTARA",
                "G8": "GOAIR",
                "I5": "AIRASIA INDIA",
            },
            "aircraft": {
                "320": "AIRBUS A320",
                "788": "BOEING 787-8",
                "737": "BOEING 737-800",
            },
        },
    }


# ── TBO Air API helpers ────────────────────────────────────────────────────────

# Thread-safe token cache — one token per process lifetime (TBO tokens are long-lived)
_tbo_token_lock = threading.Lock()
_tbo_token_cache: dict[str, str] = {}   # key: "token", value: TokenId


def _tbo_air_post(path: str, body: dict) -> dict:
    """POST to TBO Air API base URL. Auth header injected per-call via TokenId in body."""
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("'requests' package is not installed. Run: pip install requests")
    url = f"{config.TBO_AIR_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    resp = _requests.post(
        url,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=config.TBO_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _tbo_air_authenticate() -> str:
    """
    Exchange credentials for a TBO Air session token.
    Result is cached for the process lifetime (tokens are session-scoped).
    Returns TokenId string, or raises on failure.
    """
    with _tbo_token_lock:
        cached = _tbo_token_cache.get("token", "")
        if cached:
            return cached

        body = {
            "BookingMode": "API",
            "UserName": config.TBO_USERNAME,
            "Password": config.TBO_PASSWORD,
            "IPAddress": "0.0.0.0",
        }
        data = _tbo_air_post("Authenticate/ValidateAgency", body)
        token = data.get("TokenId", "")
        if not token:
            raise RuntimeError(
                f"TBO Air authentication failed — no TokenId in response: {data}"
            )
        _tbo_token_cache["token"] = token
        return token


def _tbo_air_search_raw(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int,
    children: int,
    infants: int,
    is_domestic: bool,
    token: str,
) -> list[dict]:
    """
    Call TBO /Search/ and return the flat list of result dicts.
    TBO response: {"Response": {"TraceId": "...", "Results": [[{...}, ...]]}}
    Results is a list-of-lists; we flatten the first sub-list.
    Returns [] on error or empty result.
    """
    body = {
        "AdultCount": str(adults),
        "ChildCount": str(children),
        "InfantCount": str(infants),
        "IsDomestic": str(is_domestic).lower(),
        "BookingMode": "5",
        "DirectFlight": "false",
        "OneStopFlight": "false",
        "JourneyType": "1",           # 1 = One-Way
        "EndUserIp": "0.0.0.0",
        "TokenId": token,
        "Segments": [
            {
                "Origin": origin,
                "Destination": destination,
                "PreferredDepartureTime": f"{departure_date}T00:00:00",
                "PreferredArrivalTime":   f"{departure_date}T23:59:59",
                "FlightCabinClass": 1,  # 1 = All
            }
        ],
        "PreferredCurrency": "INR",
    }
    try:
        data = _tbo_air_post("Search/", body)
    except Exception as exc:
        print(f"  [FlightTool] TBO Search failed: {exc}")
        return []

    results_outer: list[list[dict]] = (
        data.get("Response", {}).get("Results", []) or []
    )
    if not results_outer:
        return []
    # Flatten first array (one-way has a single sub-list)
    return results_outer[0] if results_outer else []


# ── FlightRecord dataclass ─────────────────────────────────────────────────────

@dataclass
class FlightRecord:
    """
    Single flight offer parsed from Amadeus /v2/shopping/flight-offers.

    HC fields (constraint_registry.py FLIGHT checks):
        price              — hc1: must be ≤ flight_budget
        stops              — hc2: 0 required if user requests direct-only
        departure_datetime — hc3: within allowed departure window

    SC fields:
        price              — sc1: value-for-money = flight_budget / price (capped 1.0)
    """
    airline: str = ""               # Resolved via dictionaries.carriers
    flight_number: str = ""         # "carrierCode-number" e.g. "6E-201"
    origin: str = ""                # IATA code
    destination: str = ""           # IATA code
    departure_datetime: str = ""    # ISO-8601 "YYYY-MM-DDTHH:MM:SS"
    arrival_datetime: str = ""      # ISO-8601 "YYYY-MM-DDTHH:MM:SS"
    duration_minutes: int = 0       # Total itinerary duration (minutes)
    price: float = 0.0              # grandTotal in currency below
    currency: str = "INR"           # From price.currency
    cabin_class: str = ""           # "economy" | "business" | "first"
    stops: int = 0                  # len(segments) - 1
    raw: dict = field(default_factory=dict)


# ── FlightTool ─────────────────────────────────────────────────────────────────

class FlightTool:
    """Returns flight records from stub data (default) or TBO India Air API (live mode)."""

    def __init__(self) -> None:
        pass

    def fetch(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        max_results: int = 10,
        **kwargs: Any,
    ) -> list[FlightRecord]:
        """Return flight records for the *origin* → *destination* route.

        Stub mode (USE_STUB_FLIGHTS=true):
            Returns hardcoded Amadeus-shaped stub dataset.
            origin/destination may be city names or IATA codes.
        Live mode (USE_STUB_FLIGHTS=false):
            1. Resolve city names → IATA codes via _CITY_TO_IATA.
            2. Authenticate with TBO → TokenId.
            3. POST /Search/ → raw results.
            4. Parse & sort by price, return up to max_results records.
        """
        if config.USE_STUB_FLIGHTS:
            print(f"  [FlightTool] Returning stub flight data ({origin}→{destination} on {departure_date})")
            raw = _make_stub_amadeus_response(origin, destination, departure_date)
            carriers: dict[str, str] = raw.get("dictionaries", {}).get("carriers", {})
            records = [self._parse_offer(offer, carriers) for offer in raw.get("data", [])]
            records.sort(key=lambda r: r.price)
            return records[:max_results]

        # ── Live mode: TBO Air API ────────────────────────────────────────────
        origin_iata      = city_to_iata(origin)      or origin.upper()
        destination_iata = city_to_iata(destination) or destination.upper()
        domestic         = _is_domestic(origin_iata, destination_iata)

        print(
            f"  [FlightTool] TBO live search: {origin_iata}→{destination_iata} "
            f"on {departure_date} (domestic={domestic})"
        )

        try:
            token = _tbo_air_authenticate()
        except Exception as exc:
            print(f"  [FlightTool] Authentication failed: {exc}")
            return []

        raw_results = _tbo_air_search_raw(
            origin=origin_iata,
            destination=destination_iata,
            departure_date=departure_date,
            adults=max(adults, 1),
            children=children,
            infants=infants,
            is_domestic=domestic,
            token=token,
        )

        if not raw_results:
            print("  [FlightTool] No live flight results from TBO.")
            return []

        records = [self._parse_tbo_air(r) for r in raw_results if r]
        records = [r for r in records if r.price > 0]
        records.sort(key=lambda r: r.price)
        print(f"  [FlightTool] {len(records)} live flight(s) fetched from TBO.")
        return records[:max_results]

    # ── Private: TBO Air parser ────────────────────────────────────────────────

    @staticmethod
    def _parse_tbo_air(result: dict) -> FlightRecord:
        """
        Parse one TBO Air search result dict → FlightRecord.

        TBO Air result paths (one-way):
          .Segments[0][0].Origin.Airport.AirportCode   → origin
          .Segments[0][0].Destination.Airport.AirportCode → destination
          .Segments[0][0].Origin.DepTime               → departure_datetime
          .Segments[0][-1].Destination.ArrTime         → arrival_datetime
          .Segments[0][0].Airline.AirlineName          → airline
          .Segments[0][0].Airline.AirlineCode          → carrier code
          .Segments[0][0].Airline.FlightNumber         → flight number
          .Segments[0][0].Duration                     → leg duration (minutes)
          sum(.Segments[0][*].Duration)                → total duration
          .Fare.TotalFare                              → price
          .Fare.Currency                               → currency
          len(.Segments[0]) - 1                        → stops
        """
        segments_outer: list[list[dict]] = result.get("Segments", [])
        segs: list[dict] = segments_outer[0] if segments_outer else []
        first = segs[0] if segs else {}
        last  = segs[-1] if segs else {}

        origin_code      = first.get("Origin",      {}).get("Airport", {}).get("AirportCode", "")
        destination_code = last.get("Destination",  {}).get("Airport", {}).get("AirportCode", "")
        departure_at     = first.get("Origin",      {}).get("DepTime", "")
        arrival_at       = last.get("Destination",  {}).get("ArrTime", "")

        airline_obj   = first.get("Airline", {})
        airline_name  = airline_obj.get("AirlineName", "")
        carrier_code  = airline_obj.get("AirlineCode", "")
        flight_number = f"{carrier_code}-{airline_obj.get('FlightNumber', '')}"

        total_duration = sum(int(s.get("Duration", 0) or 0) for s in segs)
        stops          = max(len(segs) - 1, 0)

        fare     = result.get("Fare", {})
        price    = float(fare.get("TotalFare", fare.get("PublishedFare", 0.0)) or 0.0)
        currency = fare.get("Currency", "INR")

        # Cabin class: TBO uses CabinClass numeric (1=All/Eco, 2=Eco, 4=Business, 5=First)
        cabin_map = {1: "economy", 2: "economy", 4: "business", 5: "first"}
        cabin_raw = first.get("CabinClass") or result.get("FareClassification", {}).get("Type", 1)
        try:
            cabin_class = cabin_map.get(int(cabin_raw), "economy")
        except (TypeError, ValueError):
            cabin_class = "economy"

        return FlightRecord(
            airline=airline_name,
            flight_number=flight_number,
            origin=origin_code,
            destination=destination_code,
            departure_datetime=departure_at,
            arrival_datetime=arrival_at,
            duration_minutes=total_duration,
            price=price,
            currency=currency,
            cabin_class=cabin_class,
            stops=stops,
            raw=result,
        )

    # ── Private: Amadeus stub parser (works on real + stub data identically) ──

    @staticmethod
    def _parse_offer(offer: dict, carriers: dict[str, str]) -> FlightRecord:
        """
        Parse one Amadeus flight-offer dict → FlightRecord.

        Amadeus JSON paths read:
          .itineraries[0].duration                           → total duration (ISO 8601)
          .itineraries[0].segments[0].departure.iataCode    → origin
          .itineraries[0].segments[0].departure.at          → departure datetime
          .itineraries[0].segments[-1].arrival.iataCode     → destination
          .itineraries[0].segments[-1].arrival.at           → arrival datetime
          .itineraries[0].segments[0].carrierCode           → airline lookup key
          .itineraries[0].segments[0].number                → flight number suffix
          len(.itineraries[0].segments) - 1                 → stops
          .price.grandTotal                                  → total price
          .price.currency                                    → currency
          .travelerPricings[0].fareDetailsBySegment[0].cabin → cabin class
        """
        itinerary = offer.get("itineraries", [{}])[0]
        segments  = itinerary.get("segments", [{}])
        first_seg = segments[0] if segments else {}
        last_seg  = segments[-1] if segments else {}

        origin_code      = first_seg.get("departure", {}).get("iataCode", "")
        destination_code = last_seg.get("arrival",   {}).get("iataCode", "")
        departure_at     = first_seg.get("departure", {}).get("at", "")
        arrival_at       = last_seg.get("arrival",   {}).get("at", "")
        duration_minutes = _parse_iso_duration(itinerary.get("duration", ""))

        carrier_code  = first_seg.get("carrierCode", "")
        flight_number = f"{carrier_code}-{first_seg.get('number', '')}"
        airline       = carriers.get(carrier_code, carrier_code)
        stops         = max(len(segments) - 1, 0)

        price_obj = offer.get("price", {})
        price     = float(price_obj.get("grandTotal", price_obj.get("total", 0.0)))
        currency  = price_obj.get("currency", "INR")

        cabin_class = "economy"
        tp = offer.get("travelerPricings", [])
        if tp:
            fare_segs = tp[0].get("fareDetailsBySegment", [])
            if fare_segs:
                cabin_class = fare_segs[0].get("cabin", "ECONOMY").lower()

        return FlightRecord(
            airline=airline,
            flight_number=flight_number,
            origin=origin_code,
            destination=destination_code,
            departure_datetime=departure_at,
            arrival_datetime=arrival_at,
            duration_minutes=duration_minutes,
            price=price,
            currency=currency,
            cabin_class=cabin_class,
            stops=stops,
            raw=offer,
        )

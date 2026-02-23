"""
modules/tool_usage/flight_tool.py
----------------------------------
Fetches real-time flight options and pricing from an external API.
Called by Recommendation Module during Stage 3 for flight recommendations.

TODO (MISSING from architecture doc):
  - Exact API endpoint and provider (e.g., SerpAPI Google Flights, Amadeus, Skyscanner)
  - Request/response schema
  - Rate limits and pagination
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import requests
import config


@dataclass
class FlightRecord:
    """
    Single flight option returned from the API.

    TODO: MISSING — exact field list and types from API response.
    """
    airline: str = ""
    flight_number: str = ""
    origin: str = ""
    destination: str = ""
    departure_datetime: str = ""       # TODO: MISSING — format (ISO-8601 assumed)
    arrival_datetime: str = ""
    duration_minutes: int = 0          # TODO: MISSING — time unit (assumed minutes)
    price: float = 0.0                 # TODO: MISSING — currency unit
    cabin_class: str = ""              # e.g. "economy" | "business"
    stops: int = 0
    raw: dict = field(default_factory=dict)


class FlightTool:
    """Wraps the external Flight API."""

    def __init__(self, api_url: str = config.FLIGHT_API_URL, api_key: str = config.SERPAPI_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def fetch(self, origin: str, destination: str, departure_date: str, **kwargs: Any) -> list[FlightRecord]:
        """
        Fetch available flights.

        Args:
            origin:         Departure city/airport code.
            destination:    Destination city/airport code.
            departure_date: Date string. TODO: MISSING — exact format.
            **kwargs:       Return date, number of passengers, cabin class, etc.

        TODO: MISSING — full parameter schema.
        """
        # TODO: Replace entire `if` block with real API call once endpoint/schema is known.
        if self.api_url == "UNSPECIFIED":
            print("  [DUMMY API] FlightTool.fetch() — returning hardcoded stub data.")
            return [
                FlightRecord(
                    airline="IndiGo", flight_number="6E-201",
                    origin=origin, destination=destination,
                    departure_datetime=f"{departure_date}T06:00:00",
                    arrival_datetime=f"{departure_date}T08:10:00",
                    duration_minutes=130, price=3500.0,
                    cabin_class="economy", stops=0,
                ),
                FlightRecord(
                    airline="Air India", flight_number="AI-101",
                    origin=origin, destination=destination,
                    departure_datetime=f"{departure_date}T09:30:00",
                    arrival_datetime=f"{departure_date}T11:45:00",
                    duration_minutes=135, price=8500.0,
                    cabin_class="business", stops=0,
                ),
                FlightRecord(
                    airline="SpiceJet", flight_number="SG-401",
                    origin=origin, destination=destination,
                    departure_datetime=f"{departure_date}T14:00:00",
                    arrival_datetime=f"{departure_date}T17:30:00",
                    duration_minutes=210, price=2200.0,
                    cabin_class="economy", stops=1,
                ),
            ]

        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "api_key": self.api_key,
        }
        params.update(kwargs)

        response = requests.get(self.api_url, params=params, timeout=10)
        response.raise_for_status()
        raw_data: list[dict] = response.json()  # TODO: MISSING — actual response key path

        return [self._parse_record(item) for item in raw_data]

    @staticmethod
    def _parse_record(item: dict) -> FlightRecord:
        """TODO: MISSING — replace placeholder keys with actual API response keys."""
        return FlightRecord(
            airline=item.get("airline", ""),
            flight_number=item.get("flight_number", ""),
            origin=item.get("origin", ""),
            destination=item.get("destination", ""),
            departure_datetime=item.get("departure_datetime", ""),
            arrival_datetime=item.get("arrival_datetime", ""),
            duration_minutes=item.get("duration_minutes", 0),
            price=item.get("price", 0.0),
            cabin_class=item.get("cabin_class", "economy"),
            stops=item.get("stops", 0),
            raw=item,
        )

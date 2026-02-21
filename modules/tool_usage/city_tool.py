"""
modules/tool_usage/city_tool.py
---------------------------------
Fetches general city information from an external API.
Called during constraint initialization and planning.

TODO (MISSING from architecture doc):
  - Exact API endpoint and provider
  - Request/response schema
  - What exactly constitutes "general city information"
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import requests
import config


@dataclass
class CityRecord:
    """
    General information about a city.

    TODO: MISSING — exact field list from API response.
    """
    city_name: str = ""
    country: str = ""
    timezone: str = ""                 # e.g. "Asia/Kolkata"
    currency: str = ""                 # TODO: MISSING — but relevant for budget planning
    center_lat: float = 0.0
    center_lon: float = 0.0
    population: int = 0
    language: str = ""
    raw: dict = field(default_factory=dict)


class CityTool:
    """Wraps the external City information API."""

    def __init__(self, api_url: str = config.CITY_API_URL, api_key: str = config.SERPAPI_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def fetch(self, city_name: str, **kwargs: Any) -> CityRecord:
        """
        Fetch general information about a city.

        Args:
            city_name: Name of the city.
            **kwargs:  Additional filters.
                       TODO: MISSING — full parameter schema.

        Returns:
            CityRecord with populated fields.
        """
        # TODO: Replace entire `if` block with real API call once endpoint/schema is known.
        if self.api_url == "UNSPECIFIED":
            print(f"  [DUMMY API] CityTool.fetch({city_name!r}) — returning hardcoded stub data.")
            _CITY_STUBS = {
                "Delhi": CityRecord(
                    city_name="Delhi", country="India", timezone="Asia/Kolkata",
                    currency="INR", center_lat=28.6139, center_lon=77.2090,
                    population=32_900_000, language="Hindi",
                ),
                "Mumbai": CityRecord(
                    city_name="Mumbai", country="India", timezone="Asia/Kolkata",
                    currency="INR", center_lat=19.0760, center_lon=72.8777,
                    population=20_700_000, language="Marathi",
                ),
            }
            return _CITY_STUBS.get(
                city_name,
                CityRecord(city_name=city_name, country="India",
                           timezone="Asia/Kolkata", currency="INR"),
            )

        params: dict[str, Any] = {
            "city": city_name,
            "api_key": self.api_key,
        }
        params.update(kwargs)

        response = requests.get(self.api_url, params=params, timeout=10)
        response.raise_for_status()
        raw_data: dict = response.json()  # TODO: MISSING — actual response key path

        return self._parse_record(raw_data)

    @staticmethod
    def _parse_record(item: dict) -> CityRecord:
        """TODO: MISSING — replace placeholder keys with actual API response keys."""
        return CityRecord(
            city_name=item.get("name", ""),
            country=item.get("country", ""),
            timezone=item.get("timezone", ""),
            currency=item.get("currency", ""),
            center_lat=item.get("lat", 0.0),
            center_lon=item.get("lon", 0.0),
            population=item.get("population", 0),
            language=item.get("language", ""),
            raw=item,
        )

import os
import requests

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def text_search(query: str, max_results: int = 5):
    params = {
        "query": query,
        "key": GOOGLE_API_KEY
    }
    res = requests.get(TEXT_SEARCH_URL, params=params)
    data = res.json()

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append({
            "place_id": item["place_id"],
            "name": item["name"]
        })
    return results


def place_details(place_id: str):
    params = {
        "place_id": place_id,
        "fields": "name,geometry,opening_hours,rating",
        "key": GOOGLE_API_KEY
    }
    res = requests.get(DETAILS_URL, params=params)
    result = res.json().get("result")

    if not result:
        return None

    return {
        "name": result["name"],
        "lat": result["geometry"]["location"]["lat"],
        "lng": result["geometry"]["location"]["lng"],
        "opening_hours": result.get("opening_hours", {}).get("weekday_text"),
        "rating": result.get("rating")
    }

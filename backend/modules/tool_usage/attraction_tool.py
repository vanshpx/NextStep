"""
modules/tool_usage/attraction_tool.py
--------------------------------------
Fetches attraction data from Google Places API (New).
Called by Recommendation Module during Stage 3 (Information Gathering).

Real API:  POST https://places.googleapis.com/v1/places:searchNearby
Auth:      X-Goog-Api-Key header  (config.GOOGLE_PLACES_API_KEY)
Geocode:   GET  https://maps.googleapis.com/maps/api/geocode/json
           used to resolve city name â†’ (lat, lon) for the search circle.

Stub mode: set USE_STUB_ATTRACTIONS=true (or GOOGLE_PLACES_API_KEY absent)
           to return hardcoded Delhi/generic attractions for offline testing.

Only API-verified fields are kept (per 07-simplified-model.md).
Removed: entry_cost, optimal_visit_time, min_age, ticket_required,
         min_group_size, max_group_size, seasonal_open_months, intensity_level
"""

from __future__ import annotations
import json
import re
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import config


# ---------------------------------------------------------------------------
# Category-default visit durations (ST_i)
# Source: 07-simplified-model.md Â§ ST_i Category-default table
# No API provides typical visit duration; these are the authoritative defaults.
# ---------------------------------------------------------------------------
CATEGORY_VISIT_DURATION: dict[str, tuple[int, int]] = {
    # category: (visit_duration_minutes, min_visit_duration_minutes)
    "museum":           (90,  30),
    "park":             (60,  20),
    "landmark":         (45,  15),
    "temple":           (30,  15),
    "place_of_worship": (30,  15),
    "market":           (60,  20),
    "art_gallery":      (75,  30),
    "aquarium":         (120, 45),
    "zoo":              (120, 45),
    "amusement_park":   (180, 60),
    "natural_feature":  (90,  30),
    "campground":       (90,  30),
    "restaurant":       (60,  30),
}
_DEFAULT_VISIT_DURATION     = 60
_DEFAULT_MIN_VISIT_DURATION = 20

# ---------------------------------------------------------------------------
# Google Places type â†’ internal category
# Source: https://developers.google.com/maps/documentation/places/web-service/place-types
# ---------------------------------------------------------------------------
_GOOGLE_TYPE_TO_CATEGORY: dict[str, str] = {
    "museum":                 "museum",
    "art_gallery":            "art_gallery",
    "tourist_attraction":     "landmark",
    "historical_landmark":    "landmark",
    "monument":               "landmark",
    "landmark":               "landmark",
    "point_of_interest":      "landmark",
    "park":                   "park",
    "national_park":          "park",
    "botanical_garden":       "park",
    "nature_park":            "park",
    "garden":                 "park",
    "hiking_area":            "natural_feature",
    "natural_feature":        "natural_feature",
    "campground":             "campground",
    "beach":                  "natural_feature",
    "amusement_park":         "amusement_park",
    "aquarium":               "aquarium",
    "zoo":                    "zoo",
    "wildlife_park":          "zoo",
    "place_of_worship":       "place_of_worship",
    "church":                 "place_of_worship",
    "hindu_temple":           "temple",
    "mosque":                 "place_of_worship",
    "synagogue":              "place_of_worship",
    "temple":                 "temple",
    "market":                 "market",
    "shopping_mall":          "market",
    "bazaar":                 "market",
    "restaurant":             "restaurant",
    "lodging":                "hotel",
    "hotel":                  "hotel",
}

# ---------------------------------------------------------------------------
# Quick city-centre lookup â€” avoids a separate Geocoding API call.
# Covers the most common travel destinations. Anything not here falls back
# to Google Places Text Search (same key as Places (New)).
# ---------------------------------------------------------------------------
_CITY_CENTERS: dict[str, tuple[float, float]] = {
    # ── India ─────────────────────────────────────────────────────────────────
    "delhi":           (28.6139, 77.2090),
    "new delhi":       (28.6139, 77.2090),
    "mumbai":          (19.0760, 72.8777),
    "bangalore":       (12.9716, 77.5946),
    "bengaluru":       (12.9716, 77.5946),
    "hyderabad":       (17.3850, 78.4867),
    "chennai":         (13.0827, 80.2707),
    "kolkata":         (22.5726, 88.3639),
    "calcutta":        (22.5726, 88.3639),
    "pune":            (18.5204, 73.8567),
    "ahmedabad":       (23.0225, 72.5714),
    "jaipur":          (26.9124, 75.7873),
    "agra":            (27.1767, 78.0081),
    "varanasi":        (25.3176, 82.9739),
    "banaras":         (25.3176, 82.9739),
    "kashi":           (25.3176, 82.9739),
    "goa":             (15.2993, 74.1240),
    "panaji":          (15.4909, 73.8278),
    "kochi":           ( 9.9312, 76.2673),
    "cochin":          ( 9.9312, 76.2673),
    "kerala":          ( 9.9312, 76.2673),   # state → Kochi (main tourist city)
    "thiruvananthapuram": (8.5241, 76.9366),
    "trivandrum":      ( 8.5241, 76.9366),
    "kozhikode":       (11.2588, 75.7804),
    "calicut":         (11.2588, 75.7804),
    "munnar":          (10.0893, 77.0597),
    "alleppey":        ( 9.4981, 76.3388),
    "alappuzha":       ( 9.4981, 76.3388),
    "chandigarh":      (30.7333, 76.7794),
    "amritsar":        (31.6340, 74.8723),
    "ludhiana":        (30.9010, 75.8573),
    "udaipur":         (24.5854, 73.7125),
    "jodhpur":         (26.2389, 73.0243),
    "pushkar":         (26.4899, 74.5511),
    "mysore":          (12.2958, 76.6394),
    "mysuru":          (12.2958, 76.6394),
    "ooty":            (11.4102, 76.6950),
    "coimbatore":      (11.0168, 76.9558),
    "madurai":         ( 9.9252, 78.1198),
    "pondicherry":     (11.9416, 79.8083),
    "puducherry":      (11.9416, 79.8083),
    "bhopal":          (23.2599, 77.4126),
    "indore":          (22.7196, 75.8577),
    "nagpur":          (21.1458, 79.0882),
    "surat":           (21.1702, 72.8311),
    "lucknow":         (26.8467, 80.9462),
    "patna":           (25.5941, 85.1376),
    "bhubaneswar":     (20.2961, 85.8245),
    "guwahati":        (26.1445, 91.7362),
    "shillong":        (25.5788, 91.8933),
    "srinagar":        (34.0837, 74.7973),
    "shimla":          (31.1048, 77.1734),
    "manali":          (32.2396, 77.1887),
    "dehradun":        (30.3165, 78.0322),
    "haridwar":        (29.9457, 78.1642),
    "rishikesh":       (30.0869, 78.2676),
    "darjeeling":      (27.0360, 88.2627),
    "gangtok":         (27.3389, 88.6065),
    "leh":             (34.1526, 77.5771),
    "ladakh":          (34.1526, 77.5771),
    "hampi":           (15.3350, 76.4600),
    "mahabalipuram":   (12.6269, 80.1927),
    "khajuraho":       (24.8318, 79.9199),
    "ajmer":           (26.4521, 74.6400),
    "ranthambore":     (26.0173, 76.5026),
    "jim corbett":     (29.5300, 78.7747),
    "andaman":         (11.7401, 92.6586),
    "port blair":      (11.6234, 92.7265),
    # ── India Tier-2 / state capitals ─────────────────────────────────────────
    "meerut":          (28.9845, 77.7064),
    "noida":           (28.5355, 77.3910),
    "ghaziabad":       (28.6692, 77.4538),
    "faridabad":       (28.4089, 77.3178),
    "gurugram":        (28.4595, 77.0266),
    "gurgaon":         (28.4595, 77.0266),
    "kanpur":          (26.4499, 80.3319),
    "prayagraj":       (25.4358, 81.8463),
    "allahabad":       (25.4358, 81.8463),
    "gorakhpur":       (26.7606, 83.3732),
    "moradabad":       (28.8386, 78.7733),
    "aligarh":         (27.8974, 78.0880),
    "mathura":         (27.4924, 77.6737),
    "vrindavan":       (27.5790, 77.6980),
    "kota":            (25.2138, 75.8648),
    "bikaner":         (28.0229, 73.3119),
    "nashik":          (19.9975, 73.7898),
    "aurangabad":      (19.8762, 75.3433),
    "vadodara":        (22.3072, 73.1812),
    "baroda":          (22.3072, 73.1812),
    "rajkot":          (22.3039, 70.8022),
    "jabalpur":        (23.1815, 79.9864),
    "gwalior":         (26.2183, 78.1828),
    "ranchi":          (23.3441, 85.3096),
    "visakhapatnam":   (17.6868, 83.2185),
    "vizag":           (17.6868, 83.2185),
    "vijayawada":      (16.5062, 80.6480),
    "warangal":        (17.9784, 79.5941),
    "tirupati":        (13.6288, 79.4192),
    "mangalore":       (12.9141, 74.8560),
    "mangaluru":       (12.9141, 74.8560),
    "thrissur":        (10.5276, 76.2144),
    "trichy":          (10.7905, 78.7047),
    "tiruchirappalli": (10.7905, 78.7047),
    "salem":           (11.6643, 78.1460),
    "vellore":         (12.9165, 79.1325),
    "tirunelveli":     ( 8.7139, 77.7567),
    "agartala":        (23.8315, 91.2868),
    "imphal":          (24.8170, 93.9368),
    "kohima":          (25.6751, 94.1086),
    "itanagar":        (27.1024, 93.6166),
    "aizawl":          (23.7307, 92.7173),
    "ranchi":          (23.3441, 85.3096),
    "raipur":          (21.2514, 81.6296),
    "chhattisgarh":    (21.2514, 81.6296),
    "jammu":           (32.7266, 74.8570),
    "panipat":         (29.3909, 76.9635),
    "rohtak":          (28.8955, 76.6066),
    "hisar":           (29.1492, 75.7217),
    "ambala":          (30.3782, 76.7767),
    "karnal":          (29.6857, 76.9905),
    # ── International ─────────────────────────────────────────────────────────
    "paris":           (48.8566,  2.3522),
    "london":          (51.5074, -0.1278),
    "new york":        (40.7128, -74.0060),
    "new york city":   (40.7128, -74.0060),
    "nyc":             (40.7128, -74.0060),
    "los angeles":     (34.0522, -118.2437),
    "chicago":         (41.8781, -87.6298),
    "san francisco":   (37.7749, -122.4194),
    "toronto":         (43.6532, -79.3832),
    "tokyo":           (35.6762, 139.6503),
    "osaka":           (34.6937, 135.5023),
    "kyoto":           (35.0116, 135.7681),
    "dubai":           (25.2048,  55.2708),
    "abu dhabi":       (24.4539,  54.3773),
    "singapore":       ( 1.3521, 103.8198),
    "bangkok":         (13.7563, 100.5018),
    "phuket":          ( 7.8804,  98.3923),
    "bali":            (-8.3405, 115.0920),
    "denpasar":        (-8.6705, 115.2126),
    "rome":            (41.9028,  12.4964),
    "florence":        (43.7696,  11.2558),
    "venice":          (45.4408,  12.3155),
    "milan":           (45.4642,   9.1900),
    "barcelona":       (41.3851,   2.1734),
    "madrid":          (40.4168,  -3.7038),
    "lisbon":          (38.7169,  -9.1399),
    "amsterdam":       (52.3676,   4.9041),
    "brussels":        (50.8503,   4.3517),
    "berlin":          (52.5200,  13.4050),
    "munich":          (48.1351,  11.5820),
    "prague":          (50.0755,  14.4378),
    "vienna":          (48.2082,  16.3738),
    "budapest":        (47.4979,  19.0402),
    "zurich":          (47.3769,   8.5417),
    "geneva":          (46.2044,   6.1432),
    "athens":          (37.9838,  23.7275),
    "istanbul":        (41.0082,  28.9784),
    "cairo":           (30.0444,  31.2357),
    "marrakech":       (31.6295,  -7.9811),
    "nairobi":         (-1.2921,  36.8219),
    "cape town":       (-33.9249,  18.4241),
    "johannesburg":    (-26.2041,  28.0473),
    "sydney":          (-33.8688, 151.2093),
    "melbourne":       (-37.8136, 144.9631),
    "auckland":        (-36.8509, 174.7645),
    "kuala lumpur":    ( 3.1390,  101.6869),
    "kl":              ( 3.1390,  101.6869),
    "jakarta":         (-6.2088,  106.8456),
    "ho chi minh city": (10.8231,  106.6297),
    "saigon":          (10.8231,  106.6297),
    "hanoi":           (21.0285,  105.8542),
    "beijing":         (39.9042,  116.4074),
    "shanghai":        (31.2304,  121.4737),
    "hong kong":       (22.3193,  114.1694),
    "seoul":           (37.5665,  126.9780),
    "busan":           (35.1796,  129.0756),
    "mexico city":     (19.4326,  -99.1332),
    "cancun":          (21.1619,  -86.8515),
    "rio de janeiro":  (-22.9068, -43.1729),
    "sao paulo":       (-23.5505, -46.6333),
    "buenos aires":    (-34.6037, -58.3816),
    "lima":            (-12.0464, -77.0428),
    "bogota":          ( 4.7110,  -74.0721),
}



# NOTE: "place_of_worship" is NOT a valid Nearby Search type (returns 400).
# Use specific sub-types (hindu_temple, church, mosque) instead.
_INCLUDED_TYPES: list[str] = [
    "museum",
    "art_gallery",
    "tourist_attraction",
    "historical_landmark",
    "monument",
    "park",
    "national_park",
    "botanical_garden",
    "hiking_area",
    "amusement_park",
    "aquarium",
    "zoo",
    "hindu_temple",
    "church",
    "mosque",
    "market",
]

# Field mask for Google Places (New) Nearby Search
# Only request what AttractionRecord actually uses
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.location,"
    "places.regularOpeningHours,"
    "places.rating,"
    "places.types,"
    "places.accessibilityOptions,"
    "places.editorialSummary"
)

# Types considered outdoor (for SC_o)
_OUTDOOR_TYPES: frozenset[str] = frozenset({
    "park", "national_park", "botanical_garden", "nature_park", "garden",
    "natural_feature", "hiking_area", "campground", "beach", "wildlife_park",
    "outdoor_seating_area",
})


def _visit_duration_for_category(category: str) -> tuple[int, int]:
    """Return (visit_duration_minutes, min_visit_duration_minutes) for a category."""
    cat = (category or "").lower().strip()
    return CATEGORY_VISIT_DURATION.get(cat, (_DEFAULT_VISIT_DURATION, _DEFAULT_MIN_VISIT_DURATION))


def _google_types_to_category(types: list[str]) -> str:
    """Map a Google Places `types` list to the first recognised internal category."""
    for t in types:
        cat = _GOOGLE_TYPE_TO_CATEGORY.get(t)
        if cat:
            return cat
    return types[0] if types else "landmark"


def _normalize_opening_hours(weekday_descs: list[str]) -> str:
    """
    Parse the first entry of regularOpeningHours.weekdayDescriptions to HH:MM-HH:MM.
    Examples:
      "Monday: 9:00 AM â€“ 6:00 PM"  â†’ "09:00-18:00"
      "Monday: Open 24 hours"       â†’ "00:00-23:59"
      "Monday: Closed"              â†’ ""
    """
    if not weekday_descs:
        return ""
    desc = weekday_descs[0]
    # Strip day-name prefix: "Monday: ..." â†’ "..."
    if ": " in desc:
        desc = desc.split(": ", 1)[1].strip()

    lower = desc.lower()
    if "open 24 hours" in lower:
        return "00:00-23:59"
    if lower == "closed":
        return ""

    # Match patterns: "9:00 AM â€“ 6:00 PM" or "09:00â€“18:00"
    pat = r"(\d{1,2}:\d{2}\s*(?:AM|PM)?)\s*[â€“\-â€“â€”]\s*(\d{1,2}:\d{2}\s*(?:AM|PM)?)"
    m = re.search(pat, desc, re.IGNORECASE)
    if not m:
        return ""
    open_str  = m.group(1).strip()
    close_str = m.group(2).strip()

    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            od = datetime.strptime(open_str.upper(), fmt)
            cd = datetime.strptime(close_str.upper(), fmt)
            return f"{od.strftime('%H:%M')}-{cd.strftime('%H:%M')}"
        except ValueError:
            continue
    return ""


@dataclass
class AttractionRecord:
    """
    Single attraction returned from Google Places API (New).

    Only fields reliably sourced from Google Places or derived
    deterministically from category (07-simplified-model.md).

    HC fields:
      opening_hours              â€” hc1: must be open at visit time
      visit_duration_minutes     â€” hc2: derived from category
      min_visit_duration_minutes â€” hc4: derived from category
      wheelchair_accessible      â€” hc3: from accessibilityOptions

    SC fields:
      rating                     â€” SC_r: normalised from 1â€“5
      category                   â€” SC_p: interest match
      is_outdoor                 â€” SC_o: outdoor preference
    """
    name: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    opening_hours: str = ""            # "HH:MM-HH:MM"; "" if unknown
    rating: float = 0.0               # Google Places rating 1â€“5; 0.0 = absent
    category: str = ""                # normalised internal category

    # â”€â”€ HC fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    visit_duration_minutes: int = _DEFAULT_VISIT_DURATION
    min_visit_duration_minutes: int = _DEFAULT_MIN_VISIT_DURATION
    wheelchair_accessible: bool = True
    # default True (absent â†’ conservative allow)

    # â”€â”€ SC fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    is_outdoor: bool = False
    # DERIVED: True if any type âˆˆ _OUTDOOR_TYPES

    # â”€â”€ Historical / cultural importance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    historical_importance: str = ""
    # Google Places editorialSummary.text; enriched by HistoricalInsightTool
    # â”€â”€ City binding â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    city: str = ""                 # normalised lowercase city name; set by AttractionTool.fetch()
    # Used in main.py data-consistency check: attr.city must == destination_city
    raw: dict = field(default_factory=dict)



# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# City name aliases â€” map alternate spellings to canonical dict key
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_CITY_NAME_ALIASES: dict[str, str] = {
    # Official alternate names
    "new delhi":       "delhi",
    "bombay":          "mumbai",
    "bengaluru":       "bangalore",
    "mysore":          "mysuru",
    "pondicherry":     "puducherry",
    "calcutta":        "kolkata",
    "madras":          "chennai",
    "cochin":          "kochi",
    "trivandrum":      "thiruvananthapuram",
    "calicut":         "kozhikode",
    "banaras":         "varanasi",
    "kashi":           "varanasi",
    "saigon":          "ho chi minh city",
    "kl":              "kuala lumpur",
    "nyc":             "new york",
    "new york city":   "new york",
    # State names → primary tourist city
    "kerala":          "kochi",
    "rajasthan":       "jaipur",
    "gujrat":          "ahmedabad",
    "gujarat":         "ahmedabad",
    "punjab":          "amritsar",
    "ladakh":          "leh",
    "bihar":           "patna",
    "up":              "agra",
    "uttar pradesh":   "agra",
    "uttarakhand":     "dehradun",
    "himachal":        "shimla",
    "himachal pradesh": "shimla",
    "madhya pradesh":  "bhopal",
    "mp":              "bhopal",
    "odisha":          "bhubaneswar",
    "orissa":          "bhubaneswar",
    "jharkhand":       "ranchi",
    "west bengal":     "kolkata",
    "bengal":          "kolkata",
    "tamil nadu":      "chennai",
    "andhra pradesh":  "visakhapatnam",
    "telangana":       "hyderabad",
    "karnataka":       "bangalore",
    "maharashtra":     "mumbai",
    "assam":           "guwahati",
    "tripura":         "agartala",
    "manipur":         "imphal",
    "meghalaya":       "shillong",
    "nagaland":        "kohima",
    "sikkim":          "gangtok",
    "arunachal pradesh": "itanagar",
    "mizoram":         "aizawl",
    # Common misspellings
    "kerela":          "kochi",
    "keralaa":         "kochi",
    "mumbai city":     "mumbai",
    "dilli":           "delhi",
    "bangaluru":       "bangalore",
    "banglore":        "bangalore",
    "bangalore":       "bangalore",
    "kolkatta":        "kolkata",
    "kolkota":         "kolkata",
    "chenai":          "chennai",
    "hyderbad":        "hyderabad",
    "hyderabad city":  "hyderabad",
    # Tier-2 city alternates / misspellings
    "gurugram":        "gurgaon",
    "prayagraj":       "allahabad",
    "vizag":           "visakhapatnam",
    "baroda":          "vadodara",
    "mangaluru":       "mangalore",
    "tiruchirappalli": "trichy",
    "trivandrum":      "thiruvananthapuram",
    "banaras":         "varanasi",
    "kashi":           "varanasi",
    "vrindaban":       "vrindavan",
}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Stub builders: one function per city returning a list[AttractionRecord]
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _r(name, lat, lon, oh, rating, cat, wc, outdoor, hist):
    """Convenience builder for stub AttractionRecord rows."""
    v, mv = _visit_duration_for_category(cat)
    return AttractionRecord(
        name=name, location_lat=lat, location_lon=lon,
        opening_hours=oh, rating=rating, category=cat,
        visit_duration_minutes=v, min_visit_duration_minutes=mv,
        wheelchair_accessible=wc, is_outdoor=outdoor,
        historical_importance=hist,
    )


def _delhi_stub_data() -> list[AttractionRecord]:
    """Hardcoded Delhi attractions for offline testing."""
    return [
        # â”€â”€ Zone 1: Old Delhi / Red Fort (~28.652, 77.230) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _r("Red Fort", 28.6561, 77.2410, "09:30-16:30", 4.7, "landmark", True, True,
           "Red Fort is a massive 17th-century Mughal fortress and UNESCO World Heritage "
           "Site, built by Emperor Shah Jahan in 1639 as the seat of Mughal power for "
           "over 200 years. Its Diwan-i-Aam and the legendary Peacock Throne once stood here."),
        _r("Jama Masjid", 28.6507, 77.2335, "07:00-18:30", 4.6, "place_of_worship",
           True, True,
           "Jama Masjid is India's largest mosque, commissioned by Shah Jahan in 1656. "
           "Its courtyard can accommodate 25,000 worshippers and its minarets offer the "
           "finest aerial panorama of Old Delhi's dense medieval streetscape."),
        _r("Chandni Chowk Market", 28.6508, 77.2311, "09:00-20:00", 4.2, "market",
           True, True,
           "Chandni Chowk is a 17th-century market built by Jahanara Begum, Shah Jahan's "
           "daughter. One of Asia's oldest markets, it remains the trading heart of Delhi, "
           "famous for spices and textiles unchanged in character since Mughal times."),
        _r("Sis Ganj Gurudwara", 28.6511, 77.2296, "04:00-23:00", 4.5, "place_of_worship",
           True, False,
           "Sis Ganj Sahib Gurudwara marks the site where Sikh Guru Tegh Bahadur was "
           "martyred in 1675 by Mughal Emperor Aurangzeb. One of the most sacred Sikh "
           "shrines in Delhi, it provides free langar (community meals) around the clock."),
        _r("Fatehpuri Mosque", 28.6512, 77.2199, "06:00-20:00", 4.3, "place_of_worship",
           False, True,
           "Fatehpuri Mosque was built in 1650 by Fatehpuri Begum, a consort of Shah Jahan, "
           "at the western end of Chandni Chowk. After 1857 it was briefly sold to a Hindu "
           "merchant before being restored to Muslim use by the British in 1877."),

        # â”€â”€ Zone 2: Connaught Place / Parliament (~28.628, 77.210) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _r("Jantar Mantar", 28.6271, 77.2166, "06:00-20:00", 4.3, "landmark", True, True,
           "Jantar Mantar is an 18th-century astronomical observatory built by Maharaja "
           "Jai Singh II in 1724. Its 13 giant masonry instruments predict celestial events "
           "with remarkable accuracy and contain the largest stone sundial in the world."),
        _r("Agrasen ki Baoli", 28.6293, 77.2211, "09:00-17:00", 4.5, "landmark", True, False,
           "Agrasen ki Baoli is a 14th-century stepwell with 108 steps descending 60 metres. "
           "Its mythical association with King Agrasen and cool microclimate made it a crucial "
           "water source for Old Delhi's populace for over 600 years."),
        _r("Gurudwara Bangla Sahib", 28.6271, 77.2088, "04:00-23:00", 4.7, "place_of_worship",
           True, False,
           "Gurudwara Bangla Sahib is the most prominent Sikh shrine in Delhi, built where "
           "Guru Har Krishan resided in 1664 and cured smallpox victims using water from its "
           "sacred sarovar (holy tank). Its golden dome is visible across the capital."),
        _r("India Gate", 28.6129, 77.2295, "08:00-22:00", 4.8, "landmark", True, True,
           "India Gate is a 42-metre war memorial arch designed by Sir Edwin Lutyens, "
           "dedicated to the 70,000 Indian soldiers who died in World War I. The Amar Jawan "
           "Jyoti beneath it has burned continuously since 1971 for India's Unknown Soldier."),
        _r("National War Memorial", 28.6120, 77.2282, "09:00-21:30", 4.6, "landmark",
           True, True,
           "The National War Memorial, unveiled in 2019, honours Indian soldiers killed in "
           "post-independence conflicts. Its eternal flame and 25,942 inscribed names make "
           "it the definitive modern monument to India's armed forces."),

        # â”€â”€ Zone 3: City Museum / Central Heritage (~28.607, 77.217) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _r("City Museum", 28.6139, 77.2090, "09:00-18:00", 4.5, "museum", True, False,
           "City Museum is one of the oldest urban history museums in the region, "
           "housing over 12,000 artefacts spanning 500 years of the city's founding, "
           "trade routes, and cultural evolution. Skipping it means missing the only "
           "permanent exhibition of pre-colonial city maps."),
        _r("Riverfront Park", 28.6200, 77.2150, "06:00-20:00", 4.2, "park", True, True,
           "Riverfront Park was the site of the historic 1857 assembly ground and "
           "contains the original riverside ghats used for trade for over 300 years."),
        _r("Heritage Fort", 28.6050, 77.2200, "08:00-17:00", 4.7, "landmark", False, True,
           "Heritage Fort is a 16th-century Mughal fortification designated a UNESCO "
           "World Heritage Site. It contains the only surviving example of "
           "double-walled Rajput-Mughal hybrid architecture in Northern India."),
        _r("National Gallery of Art", 28.6120, 77.2250, "10:00-17:00", 4.4, "museum",
           True, False,
           "The National Gallery of Art holds the country's largest collection of "
           "Mughal miniature paintings (1,800+ works) and the permanent Kalam school "
           "exhibition â€” the only public display of royal court manuscripts from the "
           "17th century."),
        _r("National Museum", 28.6122, 77.2190, "10:00-18:00", 4.5, "museum", True, False,
           "The National Museum of India is the country's largest museum, housing over "
           "200,000 works spanning 5,000 years including the finest collection of Harappan "
           "civilisation artefacts and the Gupta-era bronze gallery."),

        # â”€â”€ Zone 4: South Delhi â€“ Qutub / Mehrauli (~28.531, 77.191) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _r("Qutub Minar", 28.5244, 77.1855, "07:00-17:00", 4.8, "landmark", True, True,
           "The Qutub Minar is a 73-metre UNESCO-listed minaret built in 1193 by Qutb "
           "ud-Din Aibak, founder of the Delhi Sultanate. The adjacent Iron Pillar has "
           "resisted rust for 1,600 years and remains a metallurgical mystery."),
        _r("Mehrauli Archaeological Park", 28.5247, 77.1857, "06:00-18:00", 4.4, "park",
           True, True,
           "Mehrauli Archaeological Park contains over 100 historically significant "
           "structures spanning 10 centuries, including Jamali Kamali Mosque and the tomb "
           "of Adham Khan â€” one of the richest archaeological zones in the world."),
        _r("Garden of Five Senses", 28.5270, 77.1870, "09:00-18:00", 4.2, "park",
           True, True,
           "Garden of Five Senses is a landscaped park designed to stimulate all five "
           "human senses through texture paths, water features, and fragrance gardens, "
           "built on the historical slopes overlooking Mehrauli's millennia of strata."),
        _r("Hauz Khas Village", 28.5494, 77.2001, "10:00-22:00", 4.3, "landmark",
           True, True,
           "Hauz Khas Village surrounds a 14th-century reservoir commissioned by Alauddin "
           "Khalji. The adjacent madrasa ruins and Feroz Shah's tomb overlook its waters, "
           "making it a unique blend of medieval Islamic heritage and modern cafÃ© culture."),
        _r("Safdarjung Tomb", 28.5901, 77.2076, "07:00-17:00", 4.2, "landmark", True, True,
           "Safdarjung Tomb is the last great garden tomb built in the Mughal tradition "
           "(1754). Its four-chambered mausoleum, surrounded by formal charbagh gardens, "
           "is considered the dying gasp of Mughal architectural grandeur."),
        _r("Humayun's Tomb", 28.5933, 77.2507, "07:00-17:00", 4.7, "landmark", True, True,
           "Humayun's Tomb is a UNESCO World Heritage Site built in 1570, considered the "
           "first mature example of Mughal architecture and the direct precursor to the Taj "
           "Mahal. Its double-domed structure introduced the charbagh garden tomb to India."),
        _r("Lodi Garden", 28.5931, 77.2202, "06:00-20:00", 4.5, "park", True, True,
           "Lodi Garden is a 90-acre urban park containing the tombs of the 15th-century "
           "Lodi and Sayyid dynasty rulers of Delhi. The Mohammed Shah and Bara Gumbad "
           "tombs stand among flowering trees, creating a unique fusion of history and nature."),
        _r("Sunder Nursery", 28.5906, 77.2426, "09:00-18:00", 4.3, "park", True, True,
           "Sunder Nursery is a 16th-century Mughal-era heritage garden recently restored "
           "as a 90-acre urban oasis. Located adjacent to Humayun's Tomb, it features 80+ "
           "species of trees and 30+ varieties of birds, making it Delhi's finest eco-park."),

        # â”€â”€ Zone 5: East Delhi â€“ Lotus Temple / ISKCON / Akshardham (~28.556, 77.264)
        _r("Lotus Temple", 28.5535, 77.2588, "09:00-17:30", 4.6, "place_of_worship",
           True, False,
           "The Lotus Temple is a BahÃ¡'Ã­ House of Worship completed in 1986 and is "
           "one of the most visited buildings in the world. Its 27 free-standing "
           "marble petals represent the architectural pinnacle of 20th-century "
           "spiritual design."),
        _r("ISKCON Temple Delhi", 28.5614, 77.2707, "04:30-20:30", 4.6, "place_of_worship",
           True, False,
           "ISKCON Delhi, one of the largest Krishna temples in the world, was consecrated "
           "in 1998. The complex includes a multimedia exhibit of the Bhagavad Gita and the "
           "only robotic stage in an Indian temple showing scenes from the Mahabharata."),
        _r("Kalkaji Temple", 28.5454, 77.2592, "05:00-20:30", 4.4, "place_of_worship",
           True, False,
           "Kalkaji Temple is one of Delhi's oldest temples, dedicated to Goddess Kali "
           "and believed to be over 3,000 years old. Referenced in the Mahabharata, it "
           "is one of the 51 Shakti Peethas and draws lakhs of devotees during Navratri."),
        _r("Govindpuri Garden", 28.5415, 77.2540, "06:00-20:00", 4.0, "park",
           True, True,
           "Govindpuri Garden is a landscaped neighbourhood park in South Delhi "
           "adjacent to a 14th-century baoli (stepwell), offering a quiet green "
           "refuge flanked by remnants of the Lodi-era fortification wall."),
        _r("Chirag Delhi Dargah", 28.5381, 77.2497, "06:00-22:00", 4.3, "place_of_worship",
           True, False,
           "Chirag Delhi Dargah is the shrine of Sufi saint Nasiruddin Chiragh-e-Delhi, "
           "a disciple of Hazrat Nizamuddin. Built in the 14th century, it is one of the "
           "few Chishti shrines whose baraka (blessing) has historically drawn pilgrims "
           "from across the Subcontinent."),
        _r("Akshardham Temple", 28.6127, 77.2773, "10:00-18:30", 4.8, "place_of_worship",
           True, False,
           "Akshardham is a 21st-century Hindu temple complex completed in 2005, built "
           "entirely by 11,000 volunteers using traditional stone-carving techniques. Its "
           "234 ornate pillars and 20,000 murtis place it in the Guinness World Records."),
    ]


def _mumbai_stub_data() -> list[AttractionRecord]:
    """Hardcoded Mumbai attractions for offline testing."""
    return [
        _r("Gateway of India", 18.9220, 72.8347, "00:00-23:59", 4.6, "landmark",
           True, True,
           "The Gateway of India is a triumphal arch built in 1924 to commemorate the visit "
           "of King George V. Standing at the waterfront of Apollo Bunder, it became the "
           "symbolic entry point to India and the last sight of British troops departing in "
           "1948."),
        _r("Elephanta Caves", 18.9633, 72.9315, "09:00-17:30", 4.4, "landmark",
           False, False,
           "Elephanta Caves are a UNESCO World Heritage Site containing rock-cut cave temples "
           "dedicated to the Hindu god Shiva. Dating to the 5thâ€“8th centuries AD, the main "
           "cave houses the celebrated Trimurti sculpture, a 6-metre three-faced bust of "
           "Shiva."),
        _r("Chhatrapati Shivaji Maharaj Terminus", 18.9398, 72.8354, "00:00-23:59", 4.7,
           "landmark", True, False,
           "CSMT is a historic railway station and UNESCO World Heritage Site built in 1887. "
           "A stunning example of Victorian Gothic Revival architecture blended with Indian "
           "motifs, it serves over 3 million commuters daily."),
        _r("Marine Drive", 18.9441, 72.8237, "00:00-23:59", 4.6, "landmark", True, True,
           "Marine Drive is a 3.6-km C-shaped boulevard along the Arabian Sea, known as the "
           "Queen's Necklace for its arc of streetlights at night. Built on reclaimed land "
           "in the 1920s, it is Mumbai's signature promenade."),
        _r("Haji Ali Dargah", 18.9824, 72.8087, "05:30-22:00", 4.5, "place_of_worship",
           False, True,
           "Haji Ali Dargah is a 15th-century mosque and tomb of the Sufi saint Pir Haji "
           "Ali Shah Bukhari, built on a tiny islet connected to the mainland by a narrow "
           "causeway that floods at high tide."),
        _r("Siddhivinayak Temple", 19.0162, 72.8302, "05:30-21:30", 4.6, "temple",
           True, False,
           "Siddhivinayak Temple is one of Mumbai's most revered shrines, dedicated to Lord "
           "Ganesh. Built in 1801, it attracts over 25,000 devotees daily and is famous for "
           "its ornate wooden doors and black stone Ganesh idol."),
        _r("Juhu Beach", 19.0883, 72.8265, "00:00-23:59", 4.1, "natural_feature",
           True, True,
           "Juhu Beach is a 6-km stretch of coastline in the northern suburbs, famous for "
           "its street food stalls serving pav bhaji and chaat. It has been a social hub for "
           "Mumbai residents since the 1920s."),
        _r("Dr Bhau Daji Lad Museum", 19.0226, 72.8429, "10:00-17:30", 4.5, "museum",
           True, False,
           "The Dr Bhau Daji Lad Museum, restored in 2008 after 140 years, is Mumbai's "
           "oldest museum (1872). Its Indo-Saracenic building houses maps, photographs, and "
           "models documenting the city's colonial and industrial history."),
        _r("Chor Bazaar", 18.9669, 72.8322, "11:00-19:00", 4.2, "market", False, False,
           "Chor Bazaar (Thieves' Market) is a 150-year-old antique market in Mohammed Ali "
           "Road. Originally dealing in stolen goods, it now sells Bollywood memorabilia, "
           "vintage furniture, and colonial-era curiosities."),
        _r("Dharavi", 19.0403, 72.8531, "09:00-18:00", 4.0, "market", False, False,
           "Dharavi is one of Asia's largest informal settlements with an annual economic "
           "output exceeding $650 million, driven by leather, pottery, and recycling "
           "industries. Community walking tours offer a genuine window into its thriving "
           "cottage industries."),
        _r("Bandra-Worli Sea Link", 19.0184, 72.8154, "00:00-23:59", 4.5, "landmark",
           True, True,
           "The Bandra-Worli Sea Link is an 8-lane cable-stayed bridge spanning 4.7 km "
           "across Mahim Bay, opened in 2009. Its 8 towers rise 128 metres and it uses "
           "more steel than the Eiffel Tower."),
        _r("Chowpatty Beach", 18.9551, 72.8143, "00:00-23:59", 4.0, "natural_feature",
           True, True,
           "Chowpatty Beach is Mumbai's iconic urban beach at the northern end of Marine "
           "Drive. Famous for the Ganesh Chaturthi immersion ceremony and bhel puri stalls, "
           "it has hosted public gatherings since the independence movement."),
    ]


def _jaipur_stub_data() -> list[AttractionRecord]:
    """Hardcoded Jaipur attractions for offline testing."""
    return [
        _r("Amber Fort", 27.0008, 75.8512, "08:00-17:30", 4.8, "landmark", True, True,
           "Amber Fort is a UNESCO World Heritage Site perched on the Aravalli Hills, built "
           "by Raja Man Singh I in 1592. Its blend of Rajput and Mughal architecture — "
           "palaces, grand courtyards, and mirrored Sheesh Mahal halls — makes it the "
           "finest fortress in Rajasthan."),
        _r("City Palace Jaipur", 26.9258, 75.8237, "09:30-17:00", 4.6, "landmark", True, False,
           "City Palace is the royal residence of the Jaipur royal family, built by Sawai "
           "Jai Singh II in the early 18th century. The Chandra Mahal and Mubarak Mahal "
           "house a priceless collection of royal costumes, manuscripts, and weapons."),
        _r("Hawa Mahal", 26.9239, 75.8267, "09:00-16:30", 4.5, "landmark", False, False,
           "Hawa Mahal (Palace of Winds) is a five-storey pink sandstone screen facade built "
           "in 1799 by Maharaja Sawai Pratap Singh. Its 953 small windows allowed royal "
           "ladies to observe street life unseen — the defining icon of Jaipur."),
        _r("Jantar Mantar Jaipur", 26.9246, 75.8243, "09:00-16:30", 4.5, "landmark", True, True,
           "Jantar Mantar Jaipur is the largest of five astronomical observatories built by "
           "Maharaja Sawai Jai Singh II, completed in 1734. A UNESCO World Heritage Site, "
           "its Samrat Yantra is the world's largest stone sundial, accurate to 2 seconds."),
        _r("Nahargarh Fort", 26.9430, 75.8054, "10:00-17:30", 4.4, "landmark", False, True,
           "Nahargarh Fort (Tiger Fort) crowns the Aravalli ridge above Jaipur, built in 1734 "
           "as a retreat by Sawai Jai Singh II. Its terrace panorama of the Pink City at "
           "sunset is considered the finest viewpoint in Rajasthan."),
        _r("Jaigarh Fort", 27.0103, 75.8465, "09:00-16:30", 4.4, "landmark", False, True,
           "Jaigarh Fort houses the world's largest cannon on wheels, the Jaivana gun, cast "
           "in 1720. Connected to Amber Fort by underground passages, it served as the "
           "treasury and military stronghold of the Kachwaha rulers."),
        _r("Albert Hall Museum", 26.9113, 75.8198, "09:00-17:00", 4.4, "museum", True, False,
           "Albert Hall Museum is Rajasthan's oldest museum, housed in a stunning "
           "Indo-Saracenic building opened in 1887. Its galleries display Egyptian "
           "mummies, Persian metalwork, and one of India's finest collections of miniature "
           "Rajput paintings."),
        _r("Jal Mahal", 26.9513, 75.8483, "06:00-18:00", 4.2, "landmark", False, True,
           "Jal Mahal (Water Palace) appears to float in the centre of Man Sagar Lake. "
           "The five-storey palace, built in 1699, has four storeys submerged; only the "
           "top floor is visible, framed by the Nahargarh Hills."),
        _r("Birla Mandir Jaipur", 26.8960, 75.8071, "08:00-12:00", 4.5, "temple", True, False,
           "Birla Mandir is a striking white marble temple dedicated to Laxmi Narayan, "
           "built by the Birla Group in 1988. Its walls are carved with scenes from the "
           "Bhagavad Gita and Upanishads alongside quotes by world philosophers."),
        _r("Govind Dev Ji Temple", 26.9264, 75.8253, "04:30-20:00", 4.6, "temple", True, False,
           "Govind Dev Ji Temple, built within the City Palace complex in the 18th century, "
           "houses the sacred deity of Lord Krishna believed to be a near-exact likeness. "
           "It is administered by the Jaipur royal family and draws thousands of pilgrims "
           "daily for its seven daily aartis."),
        _r("Sisodiya Rani Garden", 26.9044, 75.8631, "08:00-18:00", 4.2, "park", True, True,
           "Sisodiya Rani Garden is a tiered Mughal-style garden built by Sawai Jai Singh II "
           "in 1728 as a retreat for his second queen. Its fountains, painted pavilions, and "
           "frescoes depicting the legend of Radha-Krishna make it a serene heritage garden."),
        _r("Panna Meena Ka Kund", 27.0053, 75.8526, "06:00-17:00", 4.4, "landmark", False, True,
           "Panna Meena Ka Kund is a 16th-century stepwell near Amber Fort with a "
           "geometrically symmetric network of stairs forming a diamond-grid pattern. "
           "One of the finest examples of a baoli in Rajputana, it is almost perfectly "
           "preserved."),
    ]


def _agra_stub_data() -> list[AttractionRecord]:
    """Hardcoded Agra attractions for offline testing."""
    return [
        _r("Taj Mahal", 27.1751, 78.0421, "06:00-18:30", 4.9, "landmark", True, True,
           "The Taj Mahal is a UNESCO World Heritage Site and one of the Seven Wonders of "
           "the World, built by Emperor Shah Jahan between 1632 and 1653 as a mausoleum "
           "for his wife Mumtaz Mahal. Its white Makrana marble changes colour with the "
           "light — pink at dawn, white at noon, golden at sunset."),
        _r("Agra Fort", 27.1795, 78.0219, "06:00-18:00", 4.7, "landmark", True, True,
           "Agra Fort is a UNESCO World Heritage Site, the primary residence of the Mughal "
           "emperors until 1638. Built by Akbar from 1565, its massive red sandstone walls "
           "enclose palaces, mosques, and the Pearl Mosque; Shah Jahan spent his last years "
           "imprisoned here with a view of the Taj Mahal."),
        _r("Fatehpur Sikri", 27.0945, 77.6632, "06:00-18:00", 4.6, "landmark", True, True,
           "Fatehpur Sikri is a UNESCO World Heritage Site, a complete Mughal city built by "
           "Akbar in 1571 and abandoned after only 14 years due to water scarcity. Its "
           "Buland Darwaza is the highest gateway in India at 54 metres."),
        _r("Itmad-ud-Daulah", 27.1836, 78.0379, "06:00-18:00", 4.5, "landmark", True, True,
           "Itmad-ud-Daulah's tomb, known as the Baby Taj, was built 1622–28 by Nur Jahan "
           "for her father. The first Mughal structure built entirely of white marble with "
           "pietra dura inlay, it is considered the prototype for the Taj Mahal."),
        _r("Mehtab Bagh", 27.1785, 78.0400, "06:00-17:30", 4.4, "park", True, True,
           "Mehtab Bagh (Moonlit Garden) was a Mughal garden created by Babur directly "
           "opposite the Taj Mahal across the Yamuna. Restored as a heritage park, it "
           "offers the single finest unobstructed view of the Taj Mahal and its reflection."),
        _r("Akbar's Tomb", 27.2280, 77.9965, "06:00-18:00", 4.5, "landmark", True, True,
           "Akbar's Tomb at Sikandra is a five-storey mausoleum begun by Akbar himself and "
           "completed by Jahangir in 1613. Its fusion of Hindu, Islamic, Buddhist, and "
           "Christian motifs reflects Akbar's philosophy of Din-i-Ilahi, his syncretic faith."),
        _r("Jama Masjid Agra", 27.1801, 78.0137, "06:00-20:00", 4.4, "place_of_worship", True, True,
           "Agra's Jama Masjid was built in 1648 by Shah Jahan's daughter Jahanara and "
           "dedicated to her. Its red sandstone and white marble courtyard accommodates "
           "10,000 worshippers and is one of the largest mosques in India."),
        _r("Chini Ka Rauza", 27.1890, 78.0387, "06:00-17:30", 3.9, "landmark", False, True,
           "Chini Ka Rauza (China Tomb) is the tomb of Afzal Khan, Shah Jahan's Prime "
           "Minister, built in 1635. Its exterior was once covered in brilliantly glazed "
           "Persian ceramic tiles — the most prominent example of Chinese-Persian tile-work "
           "in Mughal India."),
        _r("Mariam's Tomb", 27.2126, 77.9884, "06:00-18:00", 3.7, "landmark", False, True,
           "Mariam's Tomb at Sikandra is the mausoleum of Mariam-uz-Zamani, Akbar's chief "
           "consort and mother of Emperor Jahangir. Built in the early 17th century, its "
           "sandstone carvings blend Rajput and Mughal craftsmanship."),
        _r("Ram Bagh", 27.2097, 78.0372, "06:00-17:00", 4.0, "park", False, True,
           "Ram Bagh (Garden of Rest) is believed to be the oldest surviving Mughal garden "
           "in India, laid out by Babur in 1528. Its formal charbagh layout along the Yamuna "
           "riverbank directly inspired every subsequent Mughal garden including those "
           "surrounding the Taj Mahal."),
    ]


def _goa_stub_data() -> list[AttractionRecord]:
    """Hardcoded Goa attractions for offline testing."""
    return [
        _r("Basilica of Bom Jesus", 15.5009, 73.9115, "09:00-18:30", 4.7, "place_of_worship",
           True, False,
           "Basilica of Bom Jesus is a UNESCO World Heritage Site built in 1605, housing "
           "the mortal remains of St Francis Xavier. One of the finest examples of Baroque "
           "architecture in India, it draws pilgrims from across the world for the "
           "Exposition of St Francis Xavier held every ten years."),
        _r("Se Cathedral", 15.5015, 73.9112, "07:30-18:00", 4.5, "place_of_worship", True, False,
           "Se Cathedral in Old Goa is the largest church in Asia, built by the Portuguese "
           "between 1562 and 1619 to commemorate the defeat of Muslim forces. Its Golden "
           "Bell is considered the largest and finest toned bell in Goa."),
        _r("Chapora Fort", 15.6086, 73.7389, "08:00-17:30", 4.4, "landmark", False, True,
           "Chapora Fort, built by the Adil Shah of Bijapur and later captured by the "
           "Portuguese in 1717, overlooks the confluence of the Chapora River and the Arabian "
           "Sea. Made famous globally by the Bollywood film Dil Chahta Hai, it offers "
           "one of the most dramatic coastal views in Goa."),
        _r("Calangute Beach", 15.5437, 73.7553, "00:00-23:59", 4.1, "natural_feature",
           True, True,
           "Calangute is Goa's largest and most popular beach, a 7-km stretch known as the "
           "Queen of Beaches. During the hippie era of the 1960s and 70s, it drew "
           "international travellers; today it is the commercial heart of North Goa tourism."),
        _r("Anjuna Beach", 15.5736, 73.7283, "00:00-23:59", 4.2, "natural_feature", True, True,
           "Anjuna Beach is an iconic rocky cove famous for its Wednesday Flea Market, "
           "established by the hippie community in the 1970s. The market now sells clothing, "
           "jewellery, and spices and remains one of the most colourful outdoor bazaars in "
           "India."),
        _r("Fort Aguada", 15.4894, 73.7744, "09:30-18:00", 4.3, "landmark", False, True,
           "Fort Aguada is a well-preserved 17th-century Portuguese fort standing at the "
           "confluence of the Mandovi River and the Arabian Sea. Built in 1612, it housed a "
           "lighthouse that guided ships and a freshwater spring — aguada means water in "
           "Portuguese — after which the fort is named."),
        _r("Dudhsagar Falls", 15.3144, 74.3136, "08:00-17:00", 4.6, "natural_feature",
           False, True,
           "Dudhsagar Falls (Sea of Milk) is a 310-metre, four-tiered waterfall on the "
           "Goa-Karnataka border, one of India's tallest waterfalls. The railway viaduct "
           "crossing its face, visible in the film The Bourne Supremacy, is one of India's "
           "most spectacular engineering sights."),
        _r("Church of Our Lady of the Immaculate Conception", 15.4986, 73.8311,
           "09:00-12:30", 4.6, "place_of_worship", True, False,
           "The Church of Our Lady of the Immaculate Conception in Panjim is Goa's most "
           "photographed building, a brilliant white Baroque church built in 1541 and "
           "rebuilt in 1619. It is the spiritual heart of Panjim and the oldest church "
           "serving the city."),
        _r("Vagator Beach", 15.5975, 73.7350, "00:00-23:59", 4.3, "natural_feature",
           True, True,
           "Vagator Beach consists of a divided north and south cove backed by red laterite "
           "cliffs. The ruins of Chapora Fort loom over the northern half; the beach became "
           "a global centre for trance music culture in the 1990s and retains a bohemian "
           "character."),
        _r("Shri Mangueshi Temple", 15.1338, 74.0272, "06:00-22:00", 4.5, "temple", True, False,
           "Shri Mangueshi Temple is one of the most important Hindu shrines in Goa, "
           "dedicated to Lord Shiva as Mangueshi. The current 18th-century structure, with "
           "its distinctive Portuguese-influenced lamp tower (deepstambha), is the "
           "largest and most visited Hindu temple in Goa."),
        _r("Fontainhas", 15.4960, 73.8338, "00:00-23:59", 4.4, "landmark", True, False,
           "Fontainhas is Goa's oldest Latin Quarter, a heritage precinct of terracotta-roofed "
           "Portuguese colonial houses in pastel colours. Declared a Heritage Zone, its "
           "narrow lanes, balc\u00e3os (verandas), and chapels preserve the 19th-century "
           "atmosphere of the Portuguese colonial capital."),
    ]


def _bangalore_stub_data() -> list[AttractionRecord]:
    """Hardcoded Bangalore attractions for offline testing."""
    return [
        _r("Bangalore Palace", 12.9989, 77.5921, "10:00-17:30", 4.3, "landmark", True, False,
           "Bangalore Palace is a Tudor-style royal residence built in 1887, modelled after "
           "Windsor Castle by Chamaraja Wadiyar. Its 454-acre grounds contain Gothic "
           "turrets, arched corridors, and a large collection of royal paintings and "
           "hunting memorabilia of the Mysore Kingdom."),
        _r("Lalbagh Botanical Garden", 12.9499, 77.5871, "06:00-19:00", 4.6, "park",
           True, True,
           "Lalbagh Botanical Garden is a 240-acre garden established by Hyder Ali in 1760 "
           "and expanded by his son Tipu Sultan. It houses a 3,000-million-year-old "
           "geological rock formation, over 100 species of trees older than 100 years, "
           "and the famous Glass House modelled on London's Crystal Palace."),
        _r("Cubbon Park", 12.9762, 77.5929, "06:00-18:00", 4.6, "park", True, True,
           "Cubbon Park is a 300-acre lung of Bangalore laid out by Commissariat Sir Mark "
           "Cubbon in 1870. It contains the red Gothic Attara Kacheri (1868), the State "
           "Central Library, and over 6,000 trees of 96 species."),
        _r("Tipu Sultan's Palace", 12.9609, 77.5742, "08:30-17:30", 4.2, "landmark",
           True, False,
           "Tipu Sultan's Palace is the summer residence of the Tiger of Mysore, built "
           "entirely in teak between 1791 and 1793. Its ornate wooden balconies, arched "
           "columns, and gilded paintings make it one of the finest examples of Mysorean "
           "wooden architecture."),
        _r("ISKCON Temple Bangalore", 13.0097, 77.5507, "07:15-13:00", 4.7,
           "place_of_worship", True, False,
           "ISKCON Bangalore is the world's largest ISKCON temple, inaugurated in 1997 "
           "and spread over 7 acres. The complex includes three gold-topped vimanas, a "
           "Vedic library, and a multimedia exhibit on Vedic culture, drawing over "
           "10,000 visitors on weekends."),
        _r("Vidhana Soudha", 12.9791, 77.5908, "08:00-18:00", 4.5, "landmark", True, False,
           "Vidhana Soudha is Karnataka's legislative assembly, a monumental "
           "neo-Dravidian granite building completed in 1956 by Chief Minister S Nijalingappa. "
           "Considered one of the most impressive post-independence public buildings in India, "
           "it is lit dramatically every Sunday and on public holidays."),
        _r("Nandi Hills", 13.3702, 77.6835, "06:00-18:00", 4.5, "natural_feature",
           False, True,
           "Nandi Hills is a 1,478-metre hilltop fortress 60 km from Bangalore, the "
           "historical summer retreat of Tipu Sultan. Its sunrise viewpoint, Tipu Sultan's "
           "drop cliff, and the ancient Bhoga Nandeeshwara Temple at the base make it "
           "Bangalore's most popular day trip."),
        _r("Bull Temple", 12.9428, 77.5732, "06:00-21:00", 4.4, "temple", True, False,
           "The Bull Temple in Basavanagudi is one of Bangalore's oldest temples, built "
           "by Kempegowda I in the 16th century. It houses a massive monolithic granite "
           "Nandi bull measuring 4.5 metres high and 6 metres long, the largest Nandi "
           "statue in the world."),
        _r("National Gallery of Modern Art Bangalore", 12.9870, 77.5936, "10:00-17:00",
           4.3, "art_gallery", True, False,
           "NGMA Bangalore, housed in the 1915 Raja of Mysore's mansion, displays modern "
           "and contemporary Indian art from the 1850s to the present. Its permanent "
           "collection of over 14,000 works includes paintings, sculptures, and "
           "installations by India's foremost artists."),
        _r("Ulsoor Lake", 12.9826, 77.6232, "06:00-19:00", 4.2, "park", True, True,
           "Ulsoor Lake is a 123-acre natural lake in central Bangalore developed by the "
           "British in the 1870s. The lake has three islands; its western bank houses the "
           "boating facilities and the historic NCC (National Cadet Corps) complex."),
        _r("Commercial Street", 12.9790, 77.6020, "10:00-21:00", 4.2, "market", True, False,
           "Commercial Street is Bangalore's oldest and most famous shopping precinct, "
           "a kilometre of lanes off Brigade Road selling textiles, jewellery, and street "
           "food since the colonial era. The 1920s-era storefronts and multilingual "
           "signboards make it a living archive of Bangalore's cosmopolitan trading history."),
    ]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# City dispatcher: maps normalised city name â†’ stub builder function
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_STUB_CITY_DATA: dict[str, Any] = {
    "delhi":      _delhi_stub_data,
    "mumbai":     _mumbai_stub_data,
    "jaipur":     _jaipur_stub_data,
    "agra":       _agra_stub_data,
    "goa":        _goa_stub_data,
    "bangalore":  _bangalore_stub_data,
}

# ---------------------------------------------------------------------------
# §2 Explicitly declared set of cities for which stub data exists.
# If USE_STUB_ATTRACTIONS=true and requested city is NOT in STUB_CITIES:
#   → raise ERROR_NO_DATA_FOR_CITY.
# DO NOT add a city to STUB_CITIES without providing a complete, accurate
# dataset. DO NOT use nearest available stub or generate placeholders.
# ---------------------------------------------------------------------------
STUB_CITIES: frozenset[str] = frozenset(_STUB_CITY_DATA.keys())

# ---------------------------------------------------------------------------
# §4 Required-field validator — enforces data integrity on every record.
# Raises ERROR_INCOMPLETE_DATA if any required field is absent or default-zero.
# Called on every record before it leaves fetch(); no guessing, no defaults,
# no inference, no random numbers, no cross-city data.
# ---------------------------------------------------------------------------
_REQUIRED_ATTRACTION_FIELDS: tuple[str, ...] = (
    "name", "location_lat", "location_lon", "category"
)


def _validate_attraction_record(r: "AttractionRecord", city: str) -> None:
    """Raise ValueError(ERROR_INCOMPLETE_DATA) if any required field is missing."""
    missing: list[str] = []
    if not r.name or not r.name.strip():
        missing.append("name")
    if r.location_lat == 0.0 and r.location_lon == 0.0:
        missing.append("location (lat/lon both 0.0)")
    if not r.category or not r.category.strip():
        missing.append("category")
    if missing:
        _name = r.name.strip() if r.name else "(unnamed)"
        raise ValueError(
            f"ERROR_INCOMPLETE_DATA: attraction '{_name}' in city '{city}' "
            f"is missing required fields: {missing}. "
            "DO NOT fill with guessed values, random numbers, or hardcoded defaults."
        )


# ---------------------------------------------------------------------------
# Real Google Places API helpers
# Used when USE_STUB_ATTRACTIONS=false. Requires GOOGLE_PLACES_API_KEY.
# ---------------------------------------------------------------------------

def _geocode_city(city_name: str, api_key: str) -> tuple[float, float]:
    """Resolve a city name to (lat, lon).

    Uses _CITY_CENTERS lookup first (zero API calls for known cities).
    Falls back to Google Geocoding API for unknown cities.
    Raises ValueError(ERROR_NO_DATA_FOR_CITY) if geocoding fails.
    """
    key = city_name.strip().lower()
    if key in _CITY_CENTERS:
        return _CITY_CENTERS[key]

    params = urllib.parse.urlencode({"address": city_name, "key": api_key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(
            f"ERROR_NO_DATA_FOR_CITY: Geocoding network error for '{city_name}': {exc}"
        ) from exc

    if data.get("status") != "OK" or not data.get("results"):
        status = data.get("status", "UNKNOWN")
        hint = ""
        if status == "REQUEST_DENIED":
            hint = (
                " The Geocoding API is not enabled on your Google Cloud project. "
                "Go to console.cloud.google.com/apis/library, search for "
                "'Geocoding API', and click Enable. "
                "Alternatively, add the city to _CITY_CENTERS in attraction_tool.py "
                "so no Geocoding call is needed."
            )
        elif status == "OVER_DAILY_LIMIT" or status == "OVER_QUERY_LIMIT":
            hint = " Geocoding API quota exceeded. Check your billing settings."
        raise ValueError(
            f"ERROR_NO_DATA_FOR_CITY: Geocoding failed for '{city_name}' — "
            f"status={status!r}.{hint}"
        )
    loc = data["results"][0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"])


def _parse_google_place(place: dict, city_norm: str) -> "AttractionRecord":
    """Convert a single Google Places API 'place' dict into an AttractionRecord.

    Only uses fields present in the API response — no defaults inferred from
    unrelated data. Missing optional fields are left at their dataclass defaults.
    """
    name = place.get("displayName", {}).get("text", "").strip()
    loc  = place.get("location", {})
    lat  = float(loc.get("latitude",  0.0))
    lon  = float(loc.get("longitude", 0.0))
    types: list[str] = place.get("types", [])
    category = _google_types_to_category(types)
    rating   = float(place.get("rating", 0.0))
    oh_raw   = place.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
    opening_hours = _normalize_opening_hours(oh_raw)
    acc = place.get("accessibilityOptions", {})
    wheelchair = bool(acc.get("wheelchairAccessibleEntrance", True))
    is_outdoor = bool(set(types) & _OUTDOOR_TYPES)
    hist = place.get("editorialSummary", {}).get("text", "")
    v, mv = _visit_duration_for_category(category)
    return AttractionRecord(
        name=name,
        location_lat=lat,
        location_lon=lon,
        opening_hours=opening_hours,
        rating=rating,
        category=category,
        visit_duration_minutes=v,
        min_visit_duration_minutes=mv,
        wheelchair_accessible=wheelchair,
        is_outdoor=is_outdoor,
        historical_importance=hist,
        city=city_norm,
        raw=place,
    )


def _google_places_nearby(lat: float, lon: float, api_key: str) -> list["AttractionRecord"]:
    """POST to Google Places (New) Nearby Search and return parsed AttractionRecords.

    Raises RuntimeError if the API call fails or returns a non-200 response.
    Returns an empty list (not None) if the API returns zero places.
    """
    url = "https://places.googleapis.com/v1/places:searchNearby"
    payload = json.dumps({
        "includedTypes": _INCLUDED_TYPES,
        "maxResultCount": config.GOOGLE_PLACES_MAX_RESULTS,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(config.GOOGLE_PLACES_SEARCH_RADIUS_M),
            }
        },
        "rankPreference": "POPULARITY",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Goog-Api-Key", api_key)
    req.add_header("X-Goog-FieldMask", _FIELD_MASK)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Google Places API HTTP {exc.code}: {body[:300]}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Google Places API network error: {exc}"
        ) from exc

    return [_parse_google_place(p, "") for p in data.get("places", [])]


class AttractionTool:
    """Fetches attraction records from Google Places API (New) or stub datasets."""

    def __init__(self) -> None:
        pass

    def fetch(self, destination: str, **kwargs) -> list:
        """Return attraction records for *destination* city.

        §1 CITY DATA VALIDATION:
            If city not in available dataset → raise ERROR_NO_DATA_FOR_CITY.
            Never substitute another city, fallback to default, or fabricate POIs.

        §2 STUB MODE RULES:
            USE_STUB_ATTRACTIONS=true  → city must be in STUB_CITIES.
            USE_STUB_ATTRACTIONS=false → calls real API (not yet implemented).

        §3 POST-FETCH ASSERTION:
            assert all records have .city == requested city; HARD_FAIL on mismatch.

        §4 FIELD VALIDATION:
            _validate_attraction_record() called on every record before return;
            raises ERROR_INCOMPLETE_DATA if name/location/category missing.
        """
        city_norm = destination.strip().lower()
        # Alias resolution (e.g. "new delhi" â†’ "delhi")
        city_norm = _CITY_NAME_ALIASES.get(city_norm, city_norm)

        if config.USE_STUB_ATTRACTIONS:
            # ── §1 + §2  City must be in explicitly declared STUB_CITIES ────────
            # DO NOT substitute another city, use nearest stub, or generate POIs.
            if city_norm not in STUB_CITIES:
                raise ValueError(
                    f"ERROR_NO_DATA_FOR_CITY: '{destination}' "
                    f"(normalised: '{city_norm}') is not in "
                    f"STUB_CITIES={sorted(STUB_CITIES)}. "
                    "DO NOT substitute another city, use nearest available stub, "
                    "or generate placeholder attractions."
                )

            records = _STUB_CITY_DATA[city_norm]()

            # ── §4  Required-field validation ────────────────────────────────────
            # Abort if any record is missing name / location / category.
            for r in records:
                _validate_attraction_record(r, city_norm)

            # ── Stamp canonical city name on every record ─────────────────────────
            for r in records:
                r.city = city_norm

            # ── §3  assert fetched_city == requested_city (HARD_FAIL on mismatch) ─
            mismatched_city = [r.name for r in records if r.city != city_norm]
            if mismatched_city:
                raise RuntimeError(
                    f"HARD_FAIL: city stamp mismatch after fetch — "
                    f"{len(mismatched_city)} record(s) have .city != '{city_norm}': "
                    f"{mismatched_city[:5]}. "
                    "Aborting. DO NOT infer or substitute city."
                )
            print(f"  [AttractionTool] Returning stub attraction data for â€˜{destination}â€™ "
                  f"({len(records)} records, city=â€˜{city_norm}â€™)")
            return records
        else:  # pragma: no cover -- real Google Places API path
            # ---------------------------------------------------------------
            # USE_STUB_ATTRACTIONS=false  -->  live Google Places API call
            # Required env var: GOOGLE_PLACES_API_KEY
            # This path is fully implemented; set the key to enable any city.
            # ---------------------------------------------------------------
            if not config.GOOGLE_PLACES_API_KEY:
                raise EnvironmentError(
                    "GOOGLE_PLACES_API_KEY is not set. "
                    "Set USE_STUB_ATTRACTIONS=true for offline testing, or "
                    "export GOOGLE_PLACES_API_KEY=AIza... for live data."
                )

            # Step 1: city name -> (lat, lon)
            lat, lon = _geocode_city(city_norm, config.GOOGLE_PLACES_API_KEY)

            # Step 2: Places Nearby Search
            raw_records = _google_places_nearby(
                lat, lon, config.GOOGLE_PLACES_API_KEY
            )

            if not raw_records:
                raise ValueError(
                    f"ERROR_NO_DATA_FOR_CITY: Google Places returned 0 results "
                    f"for '{destination}' (lat={lat}, lon={lon}). "
                    "Check GOOGLE_PLACES_API_KEY permissions and the Places API (New) quota."
                )

            # Step 3: field validation + city stamp + §3 assertion
            for r in raw_records:
                _validate_attraction_record(r, city_norm)
                r.city = city_norm

            mismatched_city = [r.name for r in raw_records if r.city != city_norm]
            if mismatched_city:  # should never happen
                raise RuntimeError(
                    f"HARD_FAIL: city stamp mismatch after real fetch — "
                    f"{mismatched_city[:5]}"
                )

            print(f"  [AttractionTool] Google Places data for '{destination}' "
                  f"({len(raw_records)} records, city='{city_norm}')")
            return raw_records


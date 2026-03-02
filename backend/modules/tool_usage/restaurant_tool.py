"""
modules/tool_usage/restaurant_tool.py
---------------------------------------
Provides restaurant data using Yelp-shaped dummy records.
All data is hardcoded stub data — no external API calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import config


# ── Yelp price-tier → estimated INR per person ────────────────────────────────
# Yelp price is an ordinal string: "$" | "$$" | "$$$" | "$$$$"
# We map to a representative average cost per person in INR.
# Source: 06-ingestion-pipeline.md § 5.2 (entry_cost MISSING from API → estimated)
_YELP_PRICE_TO_INR: dict[str, float] = {
    "$":    200.0,    # budget street food / casual dining
    "$$":   500.0,    # mid-range restaurant
    "$$$": 1200.0,    # upscale dining
    "$$$$": 2500.0,   # fine dining
}

# ── Yelp category alias → internal cuisine_type ───────────────────────────────
# Yelp uses short alias codes; map the most common to a human-readable type.
# Unmapped aliases are kept as-is in cuisine_tags.
_YELP_ALIAS_TO_CUISINE: dict[str, str] = {
    "indpak":       "Indian",
    "indian":       "Indian",
    "italian":      "Italian",
    "chinese":      "Chinese",
    "japanese":     "Japanese",
    "mediterranean":"Mediterranean",
    "mexican":      "Mexican",
    "continental":  "Continental",
    "french":       "French",
    "thai":         "Thai",
    "middleeastern":"Middle Eastern",
    "vegan":        "Vegan",
    "vegetarian":   "Vegetarian",
    "seafood":      "Seafood",
    "burgers":      "American",
    "pizza":        "Italian",
    "cafe":         "Cafe",
    "breakfast_brunch": "Breakfast",
    "streetfood":   "Street Food",
    "fastfood":     "Fast Food",
    "southindian":  "Indian",
    "northindian":  "Indian",
    "mughlai":      "Indian",
}


# ── Yelp hours parser ─────────────────────────────────────────────────────────

def _yelp_hours_to_str(hours_data: list[dict]) -> str:
    """
    Parse Yelp hours block → "HH:MM-HH:MM" for Monday (day=0).

    Yelp hours structure (real API):
      [
        {
          "open": [
            {"is_overnight": false, "start": "1100", "end": "2300", "day": 0},
            ...
          ],
          "hours_type": "REGULAR",
          "is_open_now": true
        }
      ]

    "start"/"end" are 4-digit 24-hour strings: "0900" → "09:00".
    day=0 is Monday. We take the first entry, falling back to day=0.
    """
    if not hours_data:
        return ""

    open_slots: list[dict] = hours_data[0].get("open", [])
    if not open_slots:
        return ""

    # Prefer Monday (day=0); fall back to first available slot
    monday = next((s for s in open_slots if s.get("day") == 0), open_slots[0])

    def _fmt(t: str) -> str:
        t = t.zfill(4)
        return f"{t[:2]}:{t[2:]}"

    return f"{_fmt(monday.get('start', '0000'))}-{_fmt(monday.get('end', '2359'))}"


# ── Yelp stub response ─────────────────────────────────────────────────────────
# Shaped exactly like a real Yelp Fusion /v3/businesses/search response.
# Real Yelp response reference:
#   https://docs.developer.yelp.com/reference/v3_business_search
#
# Ten realistic businesses spread across 5 Delhi geographic zones:
#   1. Spice Garden          — Indian mid-range, CP area             → HC pass | SC high
#   2. The Rooftop Bistro    — Continental fine-dining, expensive     → HC fail (hc3 budget)
#   3. Street Bites          — Indian budget, no reservations         → HC pass | SC medium
#   4. Punjabi Dhaba         — Indian mid-range, Karol Bagh          → HC pass | SC medium
#   5. Karim's               — Mughlai budget, Old Delhi near masjid → HC pass | SC high
#   6. Al Jawahar            — Mughlai mid-range, Old Delhi           → HC pass | SC high
#   7. Andhra Bhavan Canteen — South Indian budget, near CP           → HC pass | SC high
#   8. Naivedyam             — South Indian mid-range, Hauz Khas     → HC pass | SC high
#   9. Sarvana Bhavan        — South Indian mid-range, Janpath       → HC pass | SC high
#  10. Lotus Garden Cafe     — Cafe/Indian budget, Lotus Temple area  → HC pass | SC medium

def _make_stub_yelp_response(location: str) -> dict:
    return {
        "businesses": [
            # ── Business 1: Spice Garden ─────────────────────────────────────
            {
                "id": "spice-garden-new-delhi",
                "alias": "spice-garden-new-delhi",
                "name": "Spice Garden",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/spice-garden.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/spice-garden-new-delhi",
                "review_count": 342,
                "categories": [
                    {"alias": "indpak",     "title": "Indian"},
                    {"alias": "vegetarian", "title": "Vegetarian"},
                ],
                "rating": 4.3,
                "coordinates": {"latitude": 28.6120, "longitude": 77.2110},
                "transactions": ["restaurant_reservation", "delivery"],
                "price": "$$",
                "location": {
                    "address1": "12 Connaught Place",
                    "address2": "",
                    "address3": "",
                    "city": "New Delhi",
                    "zip_code": "110001",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["12 Connaught Place", "New Delhi, DL 110001"],
                },
                "phone": "+911123456789",
                "display_phone": "+91 11 2345 6789",
                "distance": 450.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 0},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 1},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 2},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 3},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 4},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 5},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 2: The Rooftop Bistro (expensive — HC hc3 will block) ─
            {
                "id": "the-rooftop-bistro-new-delhi",
                "alias": "the-rooftop-bistro-new-delhi",
                "name": "The Rooftop Bistro",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/rooftop.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/the-rooftop-bistro-new-delhi",
                "review_count": 189,
                "categories": [
                    {"alias": "continental", "title": "Continental"},
                    {"alias": "french",      "title": "French"},
                ],
                "rating": 4.6,
                "coordinates": {"latitude": 28.6090, "longitude": 77.2060},
                "transactions": ["restaurant_reservation"],
                "price": "$$$$",    # → INR 2500/person — exceeds budget → HC hc3 fail
                "location": {
                    "address1": "The Imperial Hotel, Janpath",
                    "city": "New Delhi",
                    "zip_code": "110001",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["The Imperial Hotel, Janpath", "New Delhi, DL 110001"],
                },
                "phone": "+911143210000",
                "display_phone": "+91 11 4321 0000",
                "distance": 680.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 0},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 1},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 2},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 3},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 4},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 5},
                            {"is_overnight": False, "start": "1200", "end": "2300", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": False},
            },
            # ── Business 3: Street Bites (budget, no reservations) ────────────
            {
                "id": "street-bites-new-delhi",
                "alias": "street-bites-new-delhi",
                "name": "Street Bites",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/streetbites.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/street-bites-new-delhi",
                "review_count": 521,
                "categories": [
                    {"alias": "streetfood",  "title": "Street Food"},
                    {"alias": "indpak",      "title": "Indian"},
                ],
                "rating": 3.9,
                "coordinates": {"latitude": 28.6160, "longitude": 77.2130},
                "transactions": ["delivery"],   # no restaurant_reservation → False
                "price": "$",      # → INR 200/person
                "location": {
                    "address1": "Chandni Chowk Market",
                    "city": "New Delhi",
                    "zip_code": "110006",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["Chandni Chowk Market", "New Delhi, DL 110006"],
                },
                "phone": "+919876543210",
                "display_phone": "+91 98765 43210",
                "distance": 1200.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 0},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 1},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 2},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 3},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 4},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 5},
                            {"is_overnight": False, "start": "0800", "end": "2200", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 4: Punjabi Dhaba ─────────────────────────────────────
            {
                "id": "punjabi-dhaba-new-delhi",
                "alias": "punjabi-dhaba-new-delhi",
                "name": "Punjabi Dhaba",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/dhaba.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/punjabi-dhaba-new-delhi",
                "review_count": 276,
                "categories": [
                    {"alias": "northindian", "title": "North Indian"},
                    {"alias": "indpak",      "title": "Indian"},
                ],
                "rating": 4.1,
                "coordinates": {"latitude": 28.6170, "longitude": 77.2080},
                "transactions": ["delivery", "pickup"],
                "price": "$$",     # → INR 500/person
                "location": {
                    "address1": "Karol Bagh, Block 4",
                    "city": "New Delhi",
                    "zip_code": "110005",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["Karol Bagh, Block 4", "New Delhi, DL 110005"],
                },
                "phone": "+911128765432",
                "display_phone": "+91 11 2876 5432",
                "distance": 850.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 0},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 1},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 2},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 3},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 4},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 5},
                            {"is_overnight": False, "start": "1000", "end": "2230", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 5: Karim's (Old Delhi – near Jama Masjid) ───────────
            {
                "id": "karims-old-delhi",
                "alias": "karims-old-delhi",
                "name": "Karim's",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/karims.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/karims-old-delhi",
                "review_count": 1482,
                "categories": [
                    {"alias": "mughlai", "title": "Mughlai"},
                    {"alias": "indpak",  "title": "Indian"},
                ],
                "rating": 4.5,
                "coordinates": {"latitude": 28.6503, "longitude": 77.2342},
                "transactions": ["delivery"],
                "price": "$",      # → INR 200/person
                "location": {
                    "address1": "16 Jama Masjid, Gali Kababian",
                    "city": "New Delhi",
                    "zip_code": "110006",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["16 Jama Masjid, Gali Kababian", "New Delhi, DL 110006"],
                },
                "phone": "+911123264981",
                "display_phone": "+91 11 2326 4981",
                "distance": 5100.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 0},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 1},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 2},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 3},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 4},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 5},
                            {"is_overnight": False, "start": "0900", "end": "2330", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 6: Al Jawahar (Old Delhi – near Red Fort) ────────────
            {
                "id": "al-jawahar-old-delhi",
                "alias": "al-jawahar-old-delhi",
                "name": "Al Jawahar",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/aljawahar.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/al-jawahar-old-delhi",
                "review_count": 876,
                "categories": [
                    {"alias": "mughlai",     "title": "Mughlai"},
                    {"alias": "northindian", "title": "North Indian"},
                ],
                "rating": 4.3,
                "coordinates": {"latitude": 28.6505, "longitude": 77.2338},
                "transactions": ["delivery", "pickup"],
                "price": "$$",     # → INR 500/person
                "location": {
                    "address1": "8 Jama Masjid Road",
                    "city": "New Delhi",
                    "zip_code": "110006",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["8 Jama Masjid Road", "New Delhi, DL 110006"],
                },
                "phone": "+911123264880",
                "display_phone": "+91 11 2326 4880",
                "distance": 5080.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 0},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 1},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 2},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 3},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 4},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 5},
                            {"is_overnight": False, "start": "0800", "end": "2300", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": False},
            },
            # ── Business 7: Andhra Bhavan Canteen (near CP / Zone 2) ─────────
            {
                "id": "andhra-bhavan-canteen-delhi",
                "alias": "andhra-bhavan-canteen-delhi",
                "name": "Andhra Bhavan Canteen",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/andhra-bhavan.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/andhra-bhavan-canteen-delhi",
                "review_count": 2103,
                "categories": [
                    {"alias": "southindian", "title": "South Indian"},
                    {"alias": "vegetarian",  "title": "Vegetarian"},
                ],
                "rating": 4.6,
                "coordinates": {"latitude": 28.6192, "longitude": 77.2113},
                "transactions": ["delivery"],
                "price": "$",      # → INR 200/person
                "location": {
                    "address1": "1 Ashoka Road, Andhra Bhavan",
                    "city": "New Delhi",
                    "zip_code": "110001",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["1 Ashoka Road, Andhra Bhavan", "New Delhi, DL 110001"],
                },
                "phone": "+911123388935",
                "display_phone": "+91 11 2338 8935",
                "distance": 700.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 0},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 1},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 2},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 3},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 4},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 5},
                            {"is_overnight": False, "start": "0700", "end": "2200", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 8: Naivedyam (South Delhi – near Hauz Khas) ─────────
            {
                "id": "naivedyam-hauz-khas-delhi",
                "alias": "naivedyam-hauz-khas-delhi",
                "name": "Naivedyam",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/naivedyam.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/naivedyam-hauz-khas-delhi",
                "review_count": 654,
                "categories": [
                    {"alias": "southindian", "title": "South Indian"},
                    {"alias": "vegetarian",  "title": "Vegetarian"},
                ],
                "rating": 4.4,
                "coordinates": {"latitude": 28.5527, "longitude": 77.2051},
                "transactions": ["restaurant_reservation", "delivery"],
                "price": "$$",     # → INR 500/person
                "location": {
                    "address1": "1 Hauz Khas Village",
                    "city": "New Delhi",
                    "zip_code": "110016",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["1 Hauz Khas Village", "New Delhi, DL 110016"],
                },
                "phone": "+911126969328",
                "display_phone": "+91 11 2696 9328",
                "distance": 8300.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "1100", "end": "2230", "day": 0},
                            {"is_overnight": False, "start": "1100", "end": "2230", "day": 1},
                            {"is_overnight": False, "start": "1100", "end": "2230", "day": 2},
                            {"is_overnight": False, "start": "0900", "end": "2230", "day": 3},
                            {"is_overnight": False, "start": "0900", "end": "2230", "day": 4},
                            {"is_overnight": False, "start": "0900", "end": "2230", "day": 5},
                            {"is_overnight": False, "start": "0900", "end": "2230", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 9: Sarvana Bhavan (near Connaught Place) ────────────
            {
                "id": "sarvana-bhavan-cp-delhi",
                "alias": "sarvana-bhavan-cp-delhi",
                "name": "Sarvana Bhavan",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/sarvana.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/sarvana-bhavan-cp-delhi",
                "review_count": 1128,
                "categories": [
                    {"alias": "southindian", "title": "South Indian"},
                    {"alias": "vegetarian",  "title": "Vegetarian"},
                ],
                "rating": 4.4,
                "coordinates": {"latitude": 28.6331, "longitude": 77.2194},
                "transactions": ["delivery", "pickup"],
                "price": "$$",     # → INR 500/person
                "location": {
                    "address1": "46 Janpath",
                    "city": "New Delhi",
                    "zip_code": "110001",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["46 Janpath", "New Delhi, DL 110001"],
                },
                "phone": "+911143594000",
                "display_phone": "+91 11 4359 4000",
                "distance": 2100.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 0},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 1},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 2},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 3},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 4},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 5},
                            {"is_overnight": False, "start": "0800", "end": "2230", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 10: Lotus Garden Cafe (East Delhi – near Lotus Temple)
            {
                "id": "lotus-garden-cafe-delhi",
                "alias": "lotus-garden-cafe-delhi",
                "name": "Lotus Garden Cafe",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/lotus-cafe.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/lotus-garden-cafe-delhi",
                "review_count": 412,
                "categories": [
                    {"alias": "cafe",   "title": "Cafe"},
                    {"alias": "indpak", "title": "Indian"},
                ],
                "rating": 4.1,
                "coordinates": {"latitude": 28.5537, "longitude": 77.2555},
                "transactions": ["delivery"],
                "price": "$",      # → INR 200/person
                "location": {
                    "address1": "Near Lotus Temple Road",
                    "city": "New Delhi",
                    "zip_code": "110017",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["Near Lotus Temple Road", "New Delhi, DL 110017"],
                },
                "phone": "+919811223344",
                "display_phone": "+91 98112 23344",
                "distance": 9200.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 0},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 1},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 2},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 3},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 4},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 5},
                            {"is_overnight": False, "start": "0900", "end": "2100", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
            # ── Business 11: The Big Chill Cafe (Khan Market – Lodi/Humayun area) ──
            {
                "id": "big-chill-cafe-khan-market",
                "alias": "big-chill-cafe-khan-market",
                "name": "The Big Chill Cafe",
                "image_url": "https://s3-media.fl.yelpcdn.com/bphoto/bigchill.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/big-chill-cafe-khan-market",
                "review_count": 892,
                "categories": [
                    {"alias": "cafe",        "title": "Cafe"},
                    {"alias": "continental", "title": "Continental"},
                ],
                "rating": 4.5,
                "coordinates": {"latitude": 28.5998, "longitude": 77.2281},
                "transactions": ["restaurant_reservation", "delivery"],
                "price": "$$",     # → INR 500/person
                "location": {
                    "address1": "N-78 Khan Market",
                    "city": "New Delhi",
                    "zip_code": "110003",
                    "country": "IN",
                    "state": "DL",
                    "display_address": ["N-78 Khan Market", "New Delhi, DL 110003"],
                },
                "phone": "+911143500009",
                "display_phone": "+91 11 4350 0009",
                "distance": 4500.0,
                "hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 0},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 1},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 2},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 3},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 4},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 5},
                            {"is_overnight": False, "start": "1100", "end": "2300", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": True,
                    }
                ],
                "attributes": {"wheelchair_accessible": True},
            },
        ],
        "total": 11,
        "region": {
            "center": {"latitude": 28.6139, "longitude": 77.2090}
        },
    }


# ── RestaurantRecord dataclass ─────────────────────────────────────────────────

@dataclass
class RestaurantRecord:
    """
    Single restaurant parsed from a Yelp Fusion /v3/businesses/search response.

    HC fields (constraint_registry.py RESTAURANT checks):
        cuisine_type / cuisine_tags  — hc1: dietary match (cuisine ∩ user_prefs ≠ ∅)
        opening_hours                — hc2: must be open at planned meal time
        avg_price_per_person         — hc3: ≤ per_meal_budget
        wheelchair_accessible        — hc4: if traveler requires it

    SC fields:
        rating                       — sc1: normalised quality
        cuisine_tags                 — sc2: finer preference match
        accepts_reservations         — sc3: bonus for reservation support
    """
    name: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    cuisine_type: str = ""               # Primary cuisine (first category)
    cuisine_tags: list[str] = field(default_factory=list)
    rating: float = 0.0                  # Yelp 1–5 scale (same as our scale)
    avg_price_per_person: float = 0.0    # Estimated INR/person from price tier
    opening_hours: str = ""              # "HH:MM-HH:MM" (Monday, representative)
    accepts_reservations: bool = False   # "restaurant_reservation" in transactions
    wheelchair_accessible: bool = True   # attributes.wheelchair_accessible; absent → True
    raw: dict = field(default_factory=dict)


# ── RestaurantTool ─────────────────────────────────────────────────────────────

class RestaurantTool:
    """Returns Yelp-shaped restaurant records from hardcoded stub data."""

    def __init__(self) -> None:
        pass

    def fetch(
        self,
        location: str,
        term: str = "restaurants",
        limit: int = 20,
        radius: int = 10000,
        **kwargs: Any,
    ) -> list[RestaurantRecord]:
        """Return restaurant records for *location*.

        Stub mode (USE_STUB_RESTAURANTS=true):
            Returns the hardcoded Yelp-shaped stub dataset.
        Real mode (USE_STUB_RESTAURANTS=false):
            Calls Yelp Fusion API (not yet implemented).
        """
        if config.USE_STUB_RESTAURANTS:
            print(f"  [RestaurantTool] Returning stub restaurant data for '{location}'")
            raw = _make_stub_yelp_response(location)
            businesses: list[dict] = raw.get("businesses", [])
            return [self._parse_business(b) for b in businesses]
        else:  # pragma: no cover
            raise NotImplementedError(
                "Real Yelp Fusion API not configured. "
                "Set USE_STUB_RESTAURANTS=false only after wiring YELP_API_KEY."
            )

    # ── Private: parser (works on real + stub data identically) ──────────────────
    # ── Private: parser (works on real + stub data identically) ──────────────

    @staticmethod
    def _parse_business(b: dict) -> RestaurantRecord:
        """
        Parse one Yelp business dict → RestaurantRecord.

        Yelp JSON paths read:
          .name                                     → name
          .coordinates.latitude / .longitude        → lat/lon
          .categories[0].alias                      → cuisine_type (via lookup)
          .categories[].alias                       → cuisine_tags (all aliases)
          .rating                                   → rating (1–5, same scale as ours)
          .price                                    → avg_price_per_person (via tier map)
          .hours[0].open (day=0)                    → opening_hours "HH:MM-HH:MM"
          "restaurant_reservation" in .transactions → accepts_reservations
          .attributes.wheelchair_accessible         → wheelchair_accessible
        """
        # ── Coordinates ───────────────────────────────────────────────────────
        coords = b.get("coordinates", {})
        lat = float(coords.get("latitude", 0.0) or 0.0)
        lon = float(coords.get("longitude", 0.0) or 0.0)

        # ── Cuisine from categories ───────────────────────────────────────────
        categories: list[dict] = b.get("categories", [])
        aliases    = [c.get("alias", "") for c in categories]
        titles     = [c.get("title", "") for c in categories]

        # Primary cuisine: first alias with a known mapping, else first title
        cuisine_type = ""
        for alias in aliases:
            mapped = _YELP_ALIAS_TO_CUISINE.get(alias)
            if mapped:
                cuisine_type = mapped
                break
        if not cuisine_type and titles:
            cuisine_type = titles[0]

        # cuisine_tags: all aliases (raw Yelp aliases kept for fine-grained matching)
        cuisine_tags = aliases

        # ── Rating (Yelp 1–5 = same scale as ours — no conversion needed) ────
        rating = float(b.get("rating", 0.0) or 0.0)

        # ── Price tier → INR estimate ─────────────────────────────────────────
        price_tier = b.get("price", "$")
        avg_price  = _YELP_PRICE_TO_INR.get(price_tier or "$", 200.0)

        # ── Opening hours (representative Monday slot) ────────────────────────
        hours_data: list[dict] = b.get("hours", [])
        opening_hours = _yelp_hours_to_str(hours_data)

        # ── Reservation support ───────────────────────────────────────────────
        transactions: list[str] = b.get("transactions", [])
        accepts_reservations = "restaurant_reservation" in transactions

        # ── Accessibility: absent → True (conservative default per § 5.2) ─────
        attrs    = b.get("attributes", {})
        wc_value = attrs.get("wheelchair_accessible")
        wheelchair_accessible = bool(wc_value) if wc_value is not None else True

        return RestaurantRecord(
            name=b.get("name", ""),
            location_lat=lat,
            location_lon=lon,
            cuisine_type=cuisine_type,
            cuisine_tags=cuisine_tags,
            rating=rating,
            avg_price_per_person=avg_price,
            opening_hours=opening_hours,
            accepts_reservations=accepts_reservations,
            wheelchair_accessible=wheelchair_accessible,
            raw=b,
        )

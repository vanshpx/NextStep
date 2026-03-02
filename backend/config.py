"""
config.py
---------
Central configuration for TravelAgent.
All secrets loaded from environment variables — never hard-coded.

TODO (MISSING from architecture doc):
  - LLM model name and provider
  - Memory backend connection strings
  - Exact API endpoint URLs for each tool
"""

import os
from pathlib import Path

# Load .env from the backend directory (if it exists) so env vars in that file
# are picked up by os.getenv() below.  Won't override vars already set in the shell.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except ImportError:
    pass  # python-dotenv not installed — rely on shell env vars only

# ── LLM ──────────────────────────────────────────────────────────────────────
# TODO: Replace with actual model identifier once specified.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "google")          # e.g. "openai" | "google" | "anthropic"
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")  # free-tier stable model

# All tools run in stub (dummy-data) mode — no external API calls are made.
# Set USE_STUB_LLM=false and supply LLM_API_KEY to enable real LLM responses.
USE_STUB_LLM: bool = os.getenv("USE_STUB_LLM", "true").lower() in ("1", "true", "yes")

# Per-tool stub flags — each can be toggled independently.
# By default every tool runs in stub mode (no external API keys needed).
# Set any flag to "false" to enable the real API for that tool.
USE_STUB_ATTRACTIONS: bool = os.getenv("USE_STUB_ATTRACTIONS", "true").lower() in ("1", "true", "yes")
USE_STUB_HOTELS:      bool = os.getenv("USE_STUB_HOTELS",      "true").lower() in ("1", "true", "yes")
USE_STUB_RESTAURANTS: bool = os.getenv("USE_STUB_RESTAURANTS", "true").lower() in ("1", "true", "yes")
USE_STUB_FLIGHTS:     bool = os.getenv("USE_STUB_FLIGHTS",     "true").lower() in ("1", "true", "yes")

# ── Google Places API (required when USE_STUB_ATTRACTIONS=false) ──────────────
# Obtain at: https://console.cloud.google.com/apis/credentials
# Enable:  Places API (New)  +  Geocoding API
# Set env: GOOGLE_PLACES_API_KEY=AIza...
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
GOOGLE_PLACES_SEARCH_RADIUS_M: int = int(os.getenv("GOOGLE_PLACES_SEARCH_RADIUS_M", "10000"))
GOOGLE_PLACES_MAX_RESULTS: int    = int(os.getenv("GOOGLE_PLACES_MAX_RESULTS", "20"))

# Haversine walking-speed fallback used by DistanceTool (km/h)
OSRM_FALLBACK_SPEED_KMH: float = 4.5

# ── Budget Categories ─────────────────────────────────────────────────────────
# TODO: MISSING — percentage bounds and min/max values not in architecture doc.
BUDGET_CATEGORIES: list[str] = [
    "Accommodation",
    "Attractions",
    "Restaurants",
    "Transportation",
    "Other_Expenses",
    "Reserve_Fund",
]

# ── Units (CONFIRMED 2026-02-20) ─────────────────────────────────────────────────
# Dij  → minutes | STi → minutes | Tmax → minutes/day | Si → [0,1]
CURRENCY_UNIT: str  = os.getenv("CURRENCY_UNIT", "UNSPECIFIED")   # e.g. "USD" | "INR"
TIME_UNIT: str      = os.getenv("TIME_UNIT", "minutes")            # CONFIRMED
DISTANCE_UNIT: str  = os.getenv("DISTANCE_UNIT", "minutes")       # CONFIRMED: travel-time minutes

# ── Memory Backend ────────────────────────────────────────────────────────────
# TODO: MISSING — storage backend not specified in architecture doc.
MEMORY_BACKEND: str = os.getenv("MEMORY_BACKEND", "in_memory")    # e.g. "redis" | "pinecone" | "in_memory"
MEMORY_DB_URL: str  = os.getenv("MEMORY_DB_URL", "")

# ── FTRM / ACO Parameters (SUGGESTED DEFAULT — tune empirically) ──────────────
# Source: user completions 2026-02-20
ACO_ALPHA: float     = float(os.getenv("ACO_ALPHA",     "2.0"))   # pheromone exponent
ACO_BETA: float      = float(os.getenv("ACO_BETA",      "3.0"))   # heuristic exponent
ACO_RHO: float       = float(os.getenv("ACO_RHO",       "0.1"))   # evaporation rate
ACO_Q: float         = float(os.getenv("ACO_Q",         "1.0"))   # pheromone constant
ACO_TAU_INIT: float  = float(os.getenv("ACO_TAU_INIT",  "1.0"))   # initial pheromone
ACO_NUM_ANTS: int    = int(os.getenv("ACO_NUM_ANTS",    "20"))    # ants per iteration
ACO_ITERATIONS: int  = int(os.getenv("ACO_ITERATIONS",  "100"))   # total iterations
ACO_TMAX_MINUTES: float = float(os.getenv("ACO_TMAX_MINUTES", "600.0"))  # 10h per day (10:00-20:00, per 07-simplified-model.md)

# SC aggregation method (Eq 2)
# Options: "sum" | "least_misery" | "most_pleasure" | "multiplicative"
# RECOMMENDED: "sum" (smooth blending; stable early in training)
SC_AGGREGATION_METHOD: str = os.getenv("SC_AGGREGATION_METHOD", "sum")

# Pheromone update strategy: "best_ant" | "all_ants"
# RECOMMENDED: "best_ant" (lower noise for itinerary planning)
ACO_PHEROMONE_STRATEGY: str = os.getenv("ACO_PHEROMONE_STRATEGY", "best_ant")

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# Schema defined in docs/database/05-implementation.sql
# Apply with: python scripts/run_migrations.py
POSTGRES_HOST: str     = os.getenv("POSTGRES_HOST",     "localhost")
POSTGRES_PORT: int     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB: str       = os.getenv("POSTGRES_DB",       "nextstep")
POSTGRES_USER: str     = os.getenv("POSTGRES_USER",     "nextstep_user")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "nextstep_pass")
POSTGRES_MIN_CONN: int = int(os.getenv("POSTGRES_MIN_CONN", "1"))
POSTGRES_MAX_CONN: int = int(os.getenv("POSTGRES_MAX_CONN", "10"))

# ── TBO API — Hotels + Flights (required when USE_STUB_HOTELS/USE_STUB_FLIGHTS=false) ────────
# Register at: https://www.tbo.com/
# Both Hotel and Air share the same username/password credential.
# Hotel API uses HTTP Basic Auth; Air API exchanges credentials for a session token.
TBO_USERNAME:       str = os.getenv("TBO_USERNAME",       "")
TBO_PASSWORD:       str = os.getenv("TBO_PASSWORD",       "")
TBO_HOTEL_BASE_URL: str = os.getenv("TBO_HOTEL_BASE_URL", "http://api.tbotechnology.in/TBOHolidays_HotelAPI")
TBO_AIR_BASE_URL:   str = os.getenv("TBO_AIR_BASE_URL",   "https://api.tbotechnology.in")
# Timeout in seconds for all TBO HTTP calls
TBO_REQUEST_TIMEOUT: int = int(os.getenv("TBO_REQUEST_TIMEOUT", "30"))

# ── Redis ─────────────────────────────────────────────────────────────────────
# key schemas defined in docs/database/05-implementation.sql PART 2
REDIS_HOST: str        = os.getenv("REDIS_HOST",     "localhost")
REDIS_PORT: int        = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB: int          = int(os.getenv("REDIS_DB",   "0"))
REDIS_PASSWORD: str    = os.getenv("REDIS_PASSWORD", "")
# TTLs (seconds)
# dij TTL: 30 days — aligns with POI catalog refresh cycle (§ 3.2)
# Note: source docs mark dij TTL as MISSING; 2592000 is the recommended value
DIJ_CACHE_TTL: int      = int(os.getenv("DIJ_CACHE_TTL",   "2592000"))  # 30 days
TRIP_STATE_TTL: int     = int(os.getenv("TRIP_STATE_TTL",  "86400"))    # 24 hours

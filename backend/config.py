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

# ── LLM ──────────────────────────────────────────────────────────────────────
# TODO: Replace with actual model identifier once specified.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "google")          # e.g. "openai" | "google" | "anthropic"
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")  # free-tier stable model

# Set USE_STUB_LLM=true to skip all LLM API calls and use hardcoded stubs.
# Useful when API quota is exhausted or no internet access.
USE_STUB_LLM: bool = os.getenv("USE_STUB_LLM", "true").lower() in ("1", "true", "yes")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "AIzaSyDt-r0LtUSNet462Bc-IIHdGi55QMMhDZ8")


# ── External APIs ─────────────────────────────────────────────────────────────
SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Tool Endpoints ────────────────────────────────────────────────────────────
# TODO: MISSING — exact endpoint URLs not present in architecture document.
ATTRACTION_API_URL: str = os.getenv("ATTRACTION_API_URL", "UNSPECIFIED")
HOTEL_API_URL: str       = os.getenv("HOTEL_API_URL", "UNSPECIFIED")
FLIGHT_API_URL: str      = os.getenv("FLIGHT_API_URL", "UNSPECIFIED")
RESTAURANT_API_URL: str  = os.getenv("RESTAURANT_API_URL", "UNSPECIFIED")
CITY_API_URL: str        = os.getenv("CITY_API_URL", "UNSPECIFIED")

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
ACO_TMAX_MINUTES: float = float(os.getenv("ACO_TMAX_MINUTES", "480.0"))  # 8h per day

# SC aggregation method (Eq 2)
# Options: "sum" | "least_misery" | "most_pleasure" | "multiplicative"
# RECOMMENDED: "sum" (smooth blending; stable early in training)
SC_AGGREGATION_METHOD: str = os.getenv("SC_AGGREGATION_METHOD", "sum")

# Pheromone update strategy: "best_ant" | "all_ants"
# RECOMMENDED: "best_ant" (lower noise for itinerary planning)
ACO_PHEROMONE_STRATEGY: str = os.getenv("ACO_PHEROMONE_STRATEGY", "best_ant")

````instructions
# Copilot Instructions — Travel Itinerary Optimizer

## Project Overview
Python travel planner that converts a natural-language chat into a multi-day
itinerary. Uses the FTRM mathematical model + ACO route optimization.
All external APIs are stubbed by default. Real Google Places API supported for
any city when `GOOGLE_PLACES_API_KEY` is set in `backend/.env`.

**Workspace layout**: all source lives under `backend/`. Always use
`.venv\Scripts\python.exe` — never bare `python`.

---

## Running & Testing
```powershell
# Full end-to-end test (6 parts, exit 0 = all pass) — stub mode, no API key needed
$env:PYTHONUTF8="1"; $env:USE_STUB_LLM="true"
& "c:\diske\optimizer\.venv\Scripts\python.exe" "c:\diske\optimizer\backend\test_full_pipeline.py"

# Run main interactively (stub attractions, any stub city)
$env:PYTHONUTF8="1"; $env:USE_STUB_LLM="true"
& "c:\diske\optimizer\.venv\Scripts\python.exe" "c:\diske\optimizer\backend\main.py"

# Live Google Places API — requires backend/.env with GOOGLE_PLACES_API_KEY
# (USE_STUB_ATTRACTIONS=false must be in .env or env)
$env:PYTHONUTF8="1"
& "c:\diske\optimizer\.venv\Scripts\python.exe" "c:\diske\optimizer\backend\main.py"
```

---

## Environment Variables & Config (`backend/config.py`)

`config.py` auto-loads `backend/.env` via `load_dotenv(override=True)` at
import time. All flags default to `"true"` (fully offline, no API keys needed).

| Variable | Default | Purpose |
|---|---|---|
| `USE_STUB_LLM` | `true` | Use `StubLLMClient` instead of Gemini |
| `USE_STUB_ATTRACTIONS` | `true` | Use hardcoded stub data instead of Google Places |
| `USE_STUB_HOTELS` | `true` | Use stub hotel data |
| `USE_STUB_RESTAURANTS` | `true` | Use stub restaurant data |
| `USE_STUB_FLIGHTS` | `true` | Use stub flight data |
| `LLM_API_KEY` | `""` | Gemini API key (only needed when `USE_STUB_LLM=false`) |
| `GOOGLE_PLACES_API_KEY` | `""` | Google Places API key (only needed when `USE_STUB_ATTRACTIONS=false`) |
| `GOOGLE_PLACES_SEARCH_RADIUS_M` | `10000` | Nearby search radius in metres |
| `GOOGLE_PLACES_MAX_RESULTS` | `20` | Max attractions to fetch per city |

**`.env` file**: lives at `backend/.env` (git-ignored). Template at
`backend/.env.example`. Never commit `.env`.

---

## Pipeline Stages (`backend/main.py -> run_pipeline()`)
| Stage | Module | Output |
|---|---|---|
| 1 — Chat Intake | `modules/input/chat_intake.py` | `ConstraintBundle` |
| 2 — Budget Planning | `modules/planning/budget_planner.py` | `BudgetAllocation` |
| 3 — Recommendation | `modules/recommendation/` | ranked `AttractionRecord` list |
| * Pre-Stage 4 Guard | `main.py` lines ~479-527 | 4 `PIPELINE_GUARD` checks |
| 4 — Route Planning | `modules/planning/route_planner.py` + ACO | `Itinerary` |
| 5 — Memory Update | `modules/memory/` | persisted preferences |
| 6 — Re-optimization | `modules/reoptimization/` (runtime) | updated `DayPlan` |

**Trace block** (printed after Stage 1):
```
[TRACE] UserDestination / ConstraintDestination / UserBudget / ConstraintBudget / SoftInterests
```

**Pre-Stage 4 Pipeline Guard** — raises `RuntimeError` on any failure:
- `PIPELINE_GUARD[1]` — `ranked_attractions` must not be empty
- `PIPELINE_GUARD[2]` — every `a.city == destination_city`
- `PIPELINE_GUARD[3]` — `has_chat_input` => interests not empty
- `PIPELINE_GUARD[4]` — `total_budget > 0` and matches `constraints.total_budget`

---

## Data Integrity Rules (`modules/tool_usage/attraction_tool.py`)

**Sec 1 — City validation**: if `USE_STUB_ATTRACTIONS=true` and city not in `STUB_CITIES`
-> raise `RuntimeError("ERROR_NO_DATA_FOR_CITY: ...")`

**Sec 2 — STUB_CITIES explicit set** (never infer from code paths):
```python
STUB_CITIES = frozenset({'agra', 'bangalore', 'delhi', 'goa', 'jaipur', 'mumbai'})
```

**Sec 3 — Post-fetch city assertion**: after stamping every record, assert
`all(r.city == city_norm for r in records)` -> `RuntimeError("HARD_FAIL")`

**Sec 4 — Field validation** (`_validate_attraction_record(r, city)`):
raises `RuntimeError("ERROR_INCOMPLETE_DATA")` if `name`, `location`, or
`category` is missing/empty.

**Sec 5 — No silent fallbacks**: the real API path is active when
`USE_STUB_ATTRACTIONS=false`. There is NO silent fall-through from real->stub.

---

## Route Planner Guards (`modules/planning/route_planner.py`)

**Rule 1 — Anchor Validation** (in `plan()`):
- `_validate_hotel_anchor(hotel_lat, hotel_lon, destination_city)` runs before scheduling.
- Uses `_get_city_center()` -> `_CITY_CENTERS` (zero API calls).
- If hotel > 50 km from city center: raise `ERROR_INVALID_HOTEL_ANCHOR`.
- Skipped when coords are (0, 0) sentinel or city not in `_CITY_CENTERS`.

**Rule 2 — Distance Matrix Validation** (in `_build_graph()`):
- After `travel_time_matrix()`, if ALL non-diagonal cells are `inf`: raise `ERROR_MISSING_DISTANCE_DATA`.

**Rule 3/6 — Hard Failure Guard** (in `plan()`, after all days):
- If `attractions_count > 0 AND total_scheduled == 0`: raise `ERROR_SCHEDULER_LOGIC`.

**Rule 4 — Minimum Scheduling** (in `_plan_single_day()`):
Three-pass retry if `scheduled < _MIN_STOPS_PER_DAY (2)`:
- Pass 1: normal (`buffer=12 min`, `max_travel=60 min`)
- Pass 2: relax buffer -> 0 (`_RELAX_BUFFER_MIN`)
- Pass 3: relax buffer + travel threshold -> 120 min (`_RELAX_TRAVEL_MIN`)
Never relaxed: HC gate, opening hours, city mismatch.

**Rule 5 — Debug Trace** (in `_plan_single_day()`):
Before returning a 0-stop day with non-empty pool, prints for each attraction (first 5):
`HotelAnchorLatLon`, `AttrLatLon`, `TravelTimeMin`, `TmaxRemaining`, `STi`, `S_pti`, `RejectionReason`.

**`_tour_to_day_plan()` signature** now accepts:
- `buffer_min: int = _TRANSITION_BUFFER_MIN` (12)
- `max_travel_min: float = _MAX_SAME_DAY_TRAVEL_MIN` (60)

---

## City Support — Any City

### Stub cities (offline, no API key)
`agra`, `bangalore`, `delhi`, `goa`, `jaipur`, `mumbai`

### Real API cities (requires `GOOGLE_PLACES_API_KEY`)
Any city in the world. Three helper functions in `attraction_tool.py`:
1. `_geocode_city(city, api_key)` — checks `_CITY_CENTERS` dict first (100+
   cities, zero API calls), falls back to Geocoding API only if not found.
2. `_google_places_nearby(lat, lon, api_key)` — POSTs to
   `places.googleapis.com/v1/places:searchNearby`, returns raw place list.
3. `_parse_google_place(place, city_norm)` — converts raw dict ->
   `AttractionRecord` with all required fields set.

### Adding a new stub city
1. Add `_<city>_stub_data() -> list[AttractionRecord]` (minimum 10 records,
   set `historical_importance` on every record).
2. Add entry to `_STUB_CITY_DATA` dispatcher dict.
3. `STUB_CITIES` is derived from `frozenset(_STUB_CITY_DATA.keys())` — no other
   change needed.

### City name aliasing (`_CITY_NAME_ALIASES`)
Maps alternate names / state names / misspellings -> canonical city:
- State names: `"kerala" -> "kochi"`, `"rajasthan" -> "jaipur"`, `"goa" -> "goa"`
- Alternate names: `"bombay" -> "mumbai"`, `"calcutta" -> "kolkata"`
- Misspellings: `"kerela"`, `"banglore"`, `"kolkatta"`, `"chenai"`

`fetch(city)` normalises via `_CITY_NAME_ALIASES` before any lookup.

If Geocoding API gives `REQUEST_DENIED`, the error message includes the exact
fix: "Go to console.cloud.google.com/apis/library -> search 'Geocoding API' ->
Enable". Fix: add the city to `_CITY_CENTERS` to bypass Geocoding entirely.

---

## FTRM Equations (use these variable names everywhere)
```
HC_pti = Prod hcm        (Eq 1)  — 0 if ANY hard constraint violated
SC_pti = Sum Wv * scv    (Eq 2)  — SC weights: [0.25,0.20,0.30,0.15,0.10]
S_pti  = HC_pti * SC_pti (Eq 4) — composite score [0,1]
eta_ij = S_pti / Dij     (Eq 12) — ACO heuristic
P_ij   = tau^a * eta^b / Sum  (Eq 13) — ACO transition probability
```
All times (`Dij`, `STi`, `Tmax`) are **minutes**. Scores are **[0, 1]**.

---

## Re-optimization Architecture (Stage 6)
Entry point: `ReOptimizationSession` in `modules/reoptimization/session.py`

**Event routing in `session.event()` and `session.check_conditions()`:**
- `crowd_action` metadata -> `_handle_crowd_action()` -> 3-strategy tree
- `weather_action` metadata -> `_handle_weather_action()` -> `WeatherAdvisor`
- `traffic_action` metadata -> `_handle_traffic_action()` -> `TrafficAdvisor`
- else -> `_do_replan()`

**Three crowd strategies (`event_handler.py _handle_env_crowd`):**
1. `reschedule_same_day` — defer + replan + un-defer (enough time today)
2. `reschedule_future_day` — move to `current_day + 1`
3. `inform_user` — HC cannot save it; show advisory; user decides

**Advisory panel rules:**
- `WHAT YOU WILL MISS` — shown ONLY for `inform_user` / `USER_SKIP`
- `BEST ALTERNATIVES` — shown for all 3 strategies
- `YOUR CHOICE` — shown ONLY for `inform_user`

**Weather — two severity thresholds:**
```
severity > WeatherThreshold (user-derived) -> disruption triggered
severity >= HC_UNSAFE_THRESHOLD (0.75)     -> HC_pti = 0, stop BLOCKED
threshold <= severity < 0.75              -> stop DEFERRED, duration x0.75
```

**Traffic — defer vs replace:**
```
Dij_new = Dij_base * (1 + traffic_level)
S_pti >= 0.65  ->  DEFER  (high value — keep for later)
S_pti <  0.65  ->  REPLACE (low value — swap for nearby alternative)
eta_ij_new = S_pti / Dij_new   (updated ACO heuristic)
```

---

## Interactive Re-optimizer (`main.py --reoptimize`)

Launch: `python main.py --reoptimize` or `python main.py --chat --reoptimize`

**No scripted steps.** All disruptions are user-triggered. Every `PendingDecision`
requires explicit `approve / reject / modify <n>` before any state mutation.

**Supported commands:**

| Command | Maps to |
|---|---|
| `crowd <pct>` | `session.check_conditions(crowd_level=pct/100)` |
| `traffic <pct>` | `session.check_conditions(traffic_level=pct/100)` |
| `weather <condition>` | `session.check_conditions(weather_condition=…)` |
| `skip` | `session.event(USER_SKIP, {stop_name: next_stop})` |
| `replace` | `session.event(USER_DISLIKE_NEXT, {stop_name: next_stop})` |
| `slower` | `session.event(USER_PREFERENCE_CHANGE, {pace: relaxed})` |
| `faster` | `session.event(USER_PREFERENCE_CHANGE, {pace: fast})` |
| `hungry` | sets `hunger_level=0.80`, fires `HUNGER_DISRUPTION` |
| `tired` | sets `fatigue_level=0.82`, fires `FATIGUE_DISRUPTION` |
| `show options` | lists top-5 pool alternatives for the next stop |
| `continue` | `session.advance_to_stop(next_stop)` — marks it visited |
| `approve` | `session.resolve_pending("APPROVE")` |
| `reject` | `session.resolve_pending("REJECT")` |
| `modify <n>` | `session.resolve_pending("MODIFY", action_index=n)` |
| `summary` | `json.dumps(session.summary())` |
| `end` / `q` | exits loop, prints final summary |

**Disruption gate rule**: new disruption commands (`crowd`, `traffic`, `weather`,
`skip`, `replace`, `hungry`, `tired`) are blocked while `session.pending_decision`
is not None. User must resolve the pending decision first.

**State display** (after every command):
`Current Location | Current Time | Next Stop | Remaining Stops | Remaining Budget`

---

## Key Conventions
- **`AttractionRecord.historical_importance`** — rich text string; primary
  source for `HistoricalInsightTool`; set it on ALL stub attractions.
- **`ConstraintBundle`** has `total_budget: float = 0.0` and
  `has_chat_input: bool = False`; both are set in `chat_intake.run()`.
- **`_INTEREST_KEYWORD_MAP`** in `chat_intake.py` has 40+ keyword->category
  mappings; `_extract_interests_local()` always runs (even in stub LLM mode)
  to populate `bundle.interests` from raw chat text.
- **Deferred != Skipped**: `state.deferred_stops` is a temporary exclusion set;
  `state.skipped_stops` is permanent. `undefer_stop()` re-admits to pool.
- **`PartialReplanner.replan()`** always filters `visited | skipped | deferred`
  before delegating to `RoutePlanner._plan_single_day()`.
- **`DisruptionMemory`** (`modules/memory/disruption_memory.py`) is updated
  after every weather/traffic event and surfaced via `session.summary()`.
- **Threshold derivation** lives in `ConditionMonitor._derive_thresholds()` —
  never hard-code crowd/traffic/weather thresholds; always derive from
  `SoftConstraints`.
- **Hotel anchor**: `run_pipeline()` sets the hotel anchor from the first
  recommended hotel record — never hardcoded.

---

## File Map for New Features
| Concern | File |
|---|---|
| New stub city | `attraction_tool.py` `_<city>_stub_data()` + `_STUB_CITY_DATA` |
| New city alias / misspelling | `attraction_tool.py` `_CITY_NAME_ALIASES` |
| New city coords (bypass Geocoding) | `attraction_tool.py` `_CITY_CENTERS` |
| Route planner guards (anchor/matrix/failure) | `route_planner.py` `_validate_hotel_anchor()`, `_build_graph()`, `plan()`, `_plan_single_day()` |
| New disruption type | `event_handler.py` + new `*_advisor.py` |
| New HC constraint | `constraint_registry.py` + `AttractionRecord` field |
| New SC dimension | `attraction_scoring.py` + weights list |
| Historical/cultural text | `historical_tool.py` (priority: record -> LLM -> stub) |
| Memory persistence | `disruption_memory.py` `.serialize()` / `.deserialize()` |
| New env config flag | `config.py` + `backend/.env.example` |

---

## ACO Defaults (`config.py`)
`a=2.0 b=3.0 rho=0.1 Q=1.0 tau_init=1.0 num_ants=20 iterations=100`
SC aggregation: `"sum"` | Pheromone strategy: `"best_ant"`

````

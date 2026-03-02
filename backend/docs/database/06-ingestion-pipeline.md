# Data Ingestion Pipeline — Travel Itinerary Optimizer

> Source constraints: 05-implementation.sql, 03-schema-entities.md
> Date: 2026-02-23
> Real data sources only. Fabricated values are never written to any table.

---

## PART 1 — Data Sources

### 1.1 POIs (`poi` table)

| Property | Value |
|---|---|
| **Primary provider** | Google Places API (New) |
| **Endpoint** | `POST https://places.googleapis.com/v1/places:searchNearby` |
| **Auth** | API key in `X-Goog-Api-Key` header |
| **Field mask** | `places.id,places.displayName,places.location,places.regularOpeningHours,places.rating,places.types,places.accessibilityOptions,places.editorialSummary,places.priceLevel,places.photos` |
| **Rate limit** | 1,000 QPM per key (Basic Data SKU) |
| **Cost** | Nearby Search (Basic): $0.032/request; Text Search: $0.017/request |
| **Fallback provider** | OpenStreetMap / Overpass API — `https://overpass-api.de/api/interpreter` |
| **Fallback cost** | Free; self-imposed limit ≤10,000 elements/query, wait ≥5 s between requests |

**Required response fields:**

| Google Places Field | Maps to `poi` column | Notes |
|---|---|---|
| `displayName.text` | `name` | UTF-8 string |
| `location.latitude` | `location_lat` | DOUBLE PRECISION |
| `location.longitude` | `location_lon` | DOUBLE PRECISION |
| `regularOpeningHours.weekdayDescriptions[]` | `opening_hours` | Requires normalization — see Part 5.4 |
| `rating` | `rating` | FLOAT 1–5; absent for new places |
| `types[0]` | `category` | Requires type-map normalization — see Part 5.1 |
| `accessibilityOptions.wheelchairAccessibleEntrance` | `wheelchair_accessible` | BOOL; absent → `TRUE` (conservative default) |
| `priceLevel` | `entry_cost` | MISSING: `priceLevel` is an enum (FREE/INEXPENSIVE/MODERATE/EXPENSIVE/VERY_EXPENSIVE), not a numeric cost. No direct mapping to `NUMERIC(8,2)`. Requires city-specific price calibration table not present in current schema. |
| `editorialSummary.text` | `historical_importance` | Partial — generic description, not historical/cultural depth. LLM fallback applies per `historical_tool.py` |
| — | `visit_duration_minutes` | MISSING: Google Places provides no `typical_time_spent` in the New API. Must be derived from category defaults or populated manually. |
| — | `min_visit_duration_minutes` | MISSING: same reason as above |
| — | `optimal_visit_time` | MISSING: not provided by any known public POI API |
| — | `min_age` | MISSING: not provided by Google Places |
| — | `ticket_required` | MISSING: not provided; infer from `priceLevel != FREE` as approximation only — not reliable |
| — | `min_group_size` / `max_group_size` | MISSING: not provided by any known public POI API |
| — | `seasonal_open_months` | MISSING: derive from `regularOpeningHours.specialDays` if available; otherwise empty (`{}`) |
| — | `intensity_level` | MISSING: not provided; derive from category map (e.g., hiking=high, museum=low) |
| `id` (Google's place_id) | `raw_api_response` | Store full response blob in JSONB column; do not create a separate `google_place_id` column (not in schema) |

---

### 1.2 Travel Time Matrix — Dij (`poi_graph_edges` table)

| Property | Value |
|---|---|
| **Primary provider** | OSRM (Open Source Routing Machine) |
| **Self-hosted endpoint** | `GET http://{osrm-host}/table/v1/{profile}/{coordinates}?sources=all&destinations=all&annotations=duration` |
| **Public demo (non-production)** | `http://router.project-osrm.org/table/v1/{profile}/{coords}` — no SLA, rate limit unspecified |
| **Profiles available** | `driving` → maps to `car`; `foot` → maps to `walking`; `cycling` → MISSING (no schema value for `cycling`) |
| **Cost (self-hosted)** | Infrastructure cost only; OSM data is free (ODbL license) |
| **Public transit** | MISSING: OSRM does not support transit routing. OpenTripPlanner (`http://dev.opentripplanner.org`) can provide GTFS-based transit times but requires per-city GTFS feed download and server setup. Not currently wired in schema. |
| **Fallback provider** | Google Routes API — `POST https://routes.googleapis.com/v1/computeRoutes` |
| **Fallback cost** | $5.00 per 1,000 elements (Distance Matrix SKU) |
| **Output unit** | OSRM returns seconds → divide by 60 → store as `travel_time_minutes` FLOAT |

**Required OSRM Table response fields:**

| OSRM Response Field | Maps to `poi_graph_edges` column | Notes |
|---|---|---|
| `durations[i][j]` (seconds) | `travel_time_minutes` = value / 60.0 | `null` in response = no route exists → do not insert row |
| POI coordinate index `i` | `poi_a_id` | Resolved from input coordinate order |
| POI coordinate index `j` | `poi_b_id` | Resolved from input coordinate order |
| OSRM profile name | `transport_mode` | `driving`→`car`, `foot`→`walking`, `cycling`→MISSING |
| Input city name | `city` | Caller-supplied; not in OSRM response |

---

### 1.3 Hotels

| Property | Value |
|---|---|
| **Provider** | Booking.com Demand API |
| **Endpoint** | `GET https://demandapi.booking.com/3.1/accommodations/search` |
| **Auth** | OAuth 2.0 client credentials; requires affiliate partner approval |
| **Rate limit** | MISSING: not publicly documented; subject to affiliate agreement |
| **Cost** | Free for affiliate partners; Booking.com earns commission on bookings |
| **Fallback** | Google Places API — `types=lodging` with Basic + Contact + Atmosphere field masks |
| **Fallback cost** | Contact Data SKU: $0.003/request additional |

> Note: Hotels are stored in the `poi` table with `category = 'hotel'` per the schema. No separate hotel table exists in the current schema.

**Required fields → `poi` column mapping** (hotel-specific):

| Source Field | `poi` column | Notes |
|---|---|---|
| Property name | `name` | |
| `latitude` / `longitude` | `location_lat`, `location_lon` | |
| `checkin_checkout` hours | `opening_hours` | Formatted as check-in time; non-standard for HH:MM-HH:MM but best available source |
| `review_score` (0–10) | `rating` | Normalize: `rating = review_score / 2.0` → [0, 5] |
| `accessibility.wheelchair` | `wheelchair_accessible` | |
| `min_price_per_night` | `entry_cost` | Per-night rate; per-person cost MISSING without party size at ingestion time |
| `accommodation_type` | `category` | Always `'hotel'` in poi.category |

---

### 1.4 Restaurants

| Property | Value |
|---|---|
| **Primary provider** | Google Places API (New) — `types=restaurant` |
| **Fallback** | Yelp Fusion API — `GET https://api.yelp.com/v3/businesses/search` |
| **Yelp rate limit** | 5,000 requests/day (free tier) |
| **Yelp cost** | Free up to 5,000/day; paid tiers available |

**Required fields → `poi` column mapping** (restaurant-specific):

| Source Field | `poi` column | Notes |
|---|---|---|
| `displayName.text` / Yelp `name` | `name` | |
| `location.latitude` / Yelp `coordinates.latitude` | `location_lat` | |
| `location.longitude` / Yelp `coordinates.longitude` | `location_lon` | |
| `regularOpeningHours` / Yelp `hours[0].open[]` | `opening_hours` | Normalization — see Part 5.4 |
| `rating` / Yelp `rating` (0–5) | `rating` | Yelp is already 1–5 scale |
| `priceLevel` / Yelp `price` string | `entry_cost` | MISSING: same as POI — no numeric per-person cost available |
| `types` containing `cuisine` subtype | `category` | Always `'restaurant'`; cuisine → `raw_api_response` for filtering |
| `accessibilityOptions.wheelchairAccessibleEntrance` | `wheelchair_accessible` | |
| Yelp `categories[].alias` | `raw_api_response` | Store as JSONB; cuisine filtering happens at query layer |

---

### 1.5 Flights

| Property | Value |
|---|---|
| **Provider** | Amadeus Travel APIs |
| **Endpoint** | `GET https://api.amadeus.com/v2/shopping/flight-offers` |
| **Auth** | OAuth 2.0 — `POST https://api.amadeus.com/v1/security/oauth2/token` |
| **Sandbox rate limit** | 2,000 requests/month (free sandbox) |
| **Production rate limit** | MISSING: negotiated per contract |
| **Production cost** | MISSING: revenue-sharing model; contact Amadeus |
| **Required query params** | `originLocationCode`, `destinationLocationCode`, `departureDate`, `adults` |

**Required fields → `poi` column mapping** (flight stored as poi with `category='flight'`):

> Note: Schema stores flights in `poi` table. No separate flight table exists.

| Amadeus Response Field | `poi` column | Notes |
|---|---|---|
| `itineraries[0].segments[0].departure.iataCode` | `city` | Departure city IATA |
| `itineraries[0].segments[-1].arrival.iataCode` | `name` | Arrival IATA as name |
| `price.grandTotal` | `entry_cost` | Total price as NUMERIC |
| `price.currency` | `raw_api_response` | Currency stored in JSONB blob |
| `itineraries[0].duration` (ISO 8601) | `visit_duration_minutes` | Parse ISO 8601 duration → minutes |
| `itineraries[0].segments[0].departure.at` | `opening_hours` | Departure datetime; schema field is a poor fit — store full response in `raw_api_response` |
| — | `location_lat`, `location_lon` | MISSING: flights have no coordinate; insert airport coordinates from separate IATA→coordinates lookup table (not in current schema) |

---

### 1.6 Weather

| Property | Value |
|---|---|
| **Provider** | OpenWeatherMap API |
| **Endpoint** | `GET https://api.openweathermap.org/data/2.5/forecast` (5-day/3-hour) |
| **Auth** | `appid` query parameter |
| **Free tier limit** | 1,000 calls/day, 60 calls/minute |
| **Cost** | Free tier sufficient for per-trip weather checks; Professional: $40/month for higher limits |
| **Parameters** | `lat`, `lon`, `appid`, `units=metric` |

**Required fields → `disruption_events.metadata` JSONB:**

| OpenWeatherMap Field | `disruption_events.metadata` key | Notes |
|---|---|---|
| `list[i].weather[0].id` | `condition_code` | OWM weather condition code |
| `list[i].weather[0].description` | `condition` | Human-readable string |
| `list[i].wind.speed` (m/s) | `wind_speed_ms` | |
| `list[i].rain['3h']` (mm) | `precipitation_mm` | Key absent if no rain |
| `list[i].dt_txt` | `forecast_time` | Closest 3h block to trip time slot |
| Derived | `severity` | Computed by `ConditionMonitor._derive_thresholds()`; see severity formula below |

**Severity derivation formula (from copilot-instructions.md):**

```
severity = f(condition_code, wind_speed, precipitation)

severity ≥ 0.75 → HC_UNSAFE_THRESHOLD → stop BLOCKED
threshold ≤ severity < 0.75 → stop DEFERRED, duration × 0.75
severity < threshold → no disruption
```

Exact mapping of OWM condition codes → severity float: MISSING in codebase (`ConditionMonitor._derive_thresholds()` uses SoftConstraints, not a hardcoded table).

---

### 1.7 Traffic

| Property | Value |
|---|---|
| **Primary provider** | Google Routes API (traffic-aware) |
| **Endpoint** | `POST https://routes.googleapis.com/v1/computeRoutes` |
| **Auth** | `X-Goog-Api-Key` header |
| **Required body fields** | `origin`, `destination`, `travelMode`, `routingPreference: TRAFFIC_AWARE` |
| **Rate limit** | MISSING: quota managed via Google Cloud Console per project |
| **Cost** | Advanced Routes SKU: $0.01/request |
| **Fallback** | HERE Traffic API — `GET https://data.traffic.ls.hereapi.com/traffic/6.3/flow.json` |
| **HERE cost** | Free tier: 250,000 transactions/month; paid beyond |

**Required fields → `disruption_events.metadata` JSONB:**

| Google Routes Field | `disruption_events.metadata` key | Notes |
|---|---|---|
| `routes[0].duration` (seconds) | `dij_new_seconds` | Current travel time under traffic |
| `routes[0].staticDuration` (seconds) | `dij_base_seconds` | Baseline no-traffic travel time |
| Derived | `traffic_level` = `(dij_new - dij_base) / dij_base` | Ratio used in `Dij_new = Dij_base × (1 + traffic_level)` |
| Derived | `delay_minutes` = `(dij_new - dij_base) / 60` | |

---

## PART 2 — Normalization Layer

### 2.1 `users` table

No external API sources. `users` rows are created at registration.

| Field | Source | Rule |
|---|---|---|
| `user_id` | Application | `uuid_generate_v4()` at INSERT |
| `email` | Registration form | MISSING: auth system not implemented in codebase |
| `created_at` | Application | `NOW()` at INSERT |
| `last_active_at` | Application | Updated at session start |
| `preferred_currency` | Registration form | MISSING: `config.py` `CURRENCY_UNIT = "UNSPECIFIED"` |

---

### 2.2 `trips` table

Source: Phase 1 `ConstraintBundle` from `chat_intake.py`.

| `trips` column | Source object | Source field | Transformation |
|---|---|---|---|
| `trip_id` | Application | — | `uuid_generate_v4()` |
| `user_id` | Session | `user_id` | FK lookup |
| `destination_city` | `HardConstraints` | `destination_city` | Direct string copy |
| `departure_city` | `HardConstraints` | `departure_city` | Direct string copy |
| `departure_date` | `HardConstraints` | `travel_dates.start` | Python `date` → Postgres `DATE` |
| `return_date` | `HardConstraints` | `travel_dates.end` | Python `date` → Postgres `DATE` |
| `num_adults` | `HardConstraints` | `group_size.adults` | SMALLINT |
| `num_children` | `HardConstraints` | `group_size.children` | SMALLINT |
| `group_size` | `HardConstraints` | `group_size.adults + group_size.children` | Derived at INSERT |
| `traveler_ages` | `HardConstraints` | `traveler_ages` | Python list → `SMALLINT[]` |
| `requires_wheelchair` | `HardConstraints` | `requires_wheelchair` | BOOL |
| `restaurant_preference` | `HardConstraints` | `restaurant_preference` | VARCHAR |
| `fixed_appointments` | `HardConstraints` | `fixed_appointments` | `json.dumps()` → JSONB |
| `visa_restricted_countries` | `HardConstraints` | `visa_restricted_countries` | `CHAR(2)[]` |
| `total_budget` | `HardConstraints` | `budget` | `NUMERIC(12,2)` |
| `currency` | `config.py` | `CURRENCY_UNIT` | MISSING: currently `"UNSPECIFIED"` |
| `status` | Application | — | `'planned'` at creation |
| `generated_at` | Application | — | `NOW()` at Stage 4 output |
| `budget_allocation` | `BudgetAllocation` | all 6 float fields | `json.dumps(dataclass.__dict__)` → JSONB |

---

### 2.3 `poi` table

Source: Google Places API response (primary).

| `poi` column | Google Places field | Transformation |
|---|---|---|
| `poi_id` | — | `uuid_generate_v4()` |
| `city` | Caller-supplied | From bootstrap job input parameter |
| `name` | `displayName.text` | Direct copy |
| `location_lat` | `location.latitude` | DOUBLE PRECISION |
| `location_lon` | `location.longitude` | DOUBLE PRECISION |
| `opening_hours` | `regularOpeningHours.weekdayDescriptions[0]` | Parse first entry → HH:MM-HH:MM — see Part 5.4 |
| `rating` | `rating` | FLOAT; absent → `NULL` (not defaulted to any value) |
| `visit_duration_minutes` | — | MISSING: no API field; category-default table required |
| `min_visit_duration_minutes` | — | MISSING: same as above |
| `entry_cost` | `priceLevel` | MISSING: no numeric mapping available |
| `category` | `types[0]` | Map via category normalization table — see Part 5.1 |
| `optimal_visit_time` | — | MISSING |
| `wheelchair_accessible` | `accessibilityOptions.wheelchairAccessibleEntrance` | BOOL; absent → `TRUE` |
| `min_age` | — | MISSING; default `0` |
| `ticket_required` | — | MISSING; default `FALSE` |
| `min_group_size` | — | MISSING; default `1` |
| `max_group_size` | — | MISSING; default `999` |
| `seasonal_open_months` | `regularOpeningHours.specialDays` | MISSING consistent structure; default `'{}'` |
| `is_outdoor` | `types[]` contains `park\|natural_feature\|campground` | Boolean derived from type set |
| `intensity_level` | `types[0]` | Category-to-intensity map — see Part 5.1 |
| `historical_importance` | `editorialSummary.text` | Direct copy; LLM enrichment applied post-insert |
| `source_api` | Caller | `'serpapi'` if via SerpAPI wrapper, else `'manual'` or `'stub'` |
| `raw_api_response` | Full response object | `json.dumps(response_dict)` → JSONB |
| `fetched_at` | Application | `NOW()` at insert |

---

### 2.4 `poi_graph_edges` table

Source: OSRM Table service.

| `poi_graph_edges` column | Source | Transformation |
|---|---|---|
| `edge_id` | — | `BIGSERIAL` auto |
| `city` | Caller-supplied | Bootstrap job input |
| `poi_a_id` | Input coordinate index `i` | Resolved from ordered POI list: `poi_id_list[i]` |
| `poi_b_id` | Input coordinate index `j` | Resolved from ordered POI list: `poi_id_list[j]` |
| `transport_mode` | OSRM profile name | `'driving'`→`'car'`, `'foot'`→`'walking'`; `'cycling'`→MISSING |
| `travel_time_minutes` | `durations[i][j]` (seconds) | `value / 60.0`; `NULL` response → skip row |
| `last_updated` | Application | `NOW()` at insert or UPDATE |

---

### 2.5 `itinerary_days` table

Source: Stage 4 `Itinerary` + `DayPlan` objects from `route_planner.py`.

| `itinerary_days` column | Source object | Transformation |
|---|---|---|
| `day_id` | — | `uuid_generate_v4()` |
| `trip_id` | `Itinerary.trip_id` | FK |
| `day_number` | `DayPlan.day_number` | SMALLINT |
| `date` | `DayPlan.date` | Python `date` → Postgres `DATE` |
| `daily_budget_used` | `DayPlan.total_cost` | `NUMERIC(10,2)` |
| `route_points` | `DayPlan.route_points` (list of `RoutePoint`) | `json.dumps([rp.__dict__ for rp in day.route_points])` → JSONB |
| `replan_version` | Application | `0` at creation; incremented by `PartialReplanner.replan()` via `UPDATE ... SET replan_version = replan_version + 1` |

---

### 2.6 `disruption_events` table

Source: `DisruptionMemory` records at session end (`serialize()` → promote to DB).

| `disruption_events` column | Source record | Transformation |
|---|---|---|
| `event_id` | — | `uuid_generate_v4()` |
| `trip_id` | Session context | FK |
| `day_number` | `record.day_number` | SMALLINT |
| `event_type` | Record class type | `WeatherRecord`→`'weather'`, `TrafficRecord`→`'traffic'`, `ReplacementRecord`→`'user_replace'`, `HungerRecord`→`'hunger'`, `FatigueRecord`→`'fatigue'`, `record_generic()` payload → `'generic'` or specific type string |
| `trigger_time` | `record.time` | `HH:MM` string; already formatted in `DisruptionMemory` |
| `severity` | `record.severity` | FLOAT; `0.0` for user-triggered types |
| `impacted_stops` | `record.stop_name` or list | Wrap single string in array: `ARRAY[record.stop_name]` |
| `action_taken` | `record.action_taken` | VARCHAR(64) |
| `user_response` | `record.user_response` | VARCHAR(16); map to CHECK constraint values |
| `s_pti_affected` | `record.s_pti` | FLOAT or `NULL` if not recorded |
| `metadata` | Record type-specific fields | `json.dumps(record.extra_fields)` → JSONB |
| `recorded_at` | Application | `NOW()` at promote-to-DB call |

---

## PART 3 — Data Loading Strategy

### 3.1 One-Time City Bootstrap

Performed once per city before any trip to that city is served.

```
Step 1 — POI fetch
  Input:  city name, bounding box coordinates
  Action: Call Google Places searchNearby for each category in batches of 20
  Limit:  Max 500 POIs per city (ACO practical limit; n>50 degrades performance)
  Output: INSERT INTO poi (...) ON CONFLICT (city, name) DO UPDATE SET fetched_at = NOW()

Step 2 — POI deduplication
  Run deduplication pass — see Part 5.1

Step 3 — Dij matrix computation
  Input:  All poi_ids + coordinates for the city
  Action: OSRM Table call for each transport_mode separately
  Output: INSERT INTO poi_graph_edges (...) ON CONFLICT (uq_poi_graph_edges) DO UPDATE SET travel_time_minutes = EXCLUDED.travel_time_minutes, last_updated = NOW()

Step 4 — Redis warm-up
  Action: For each row in poi_graph_edges WHERE city = target:
          SET dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode} "{travel_time_minutes}"
          EXPIRE ... {dij_ttl}
```

---

### 3.2 Periodic Refresh Policy

| Data type | Refresh interval | Trigger |
|---|---|---|
| `poi` catalog (Google Places) | 30 days | Scheduled background job per city |
| `poi_graph_edges` (OSRM) | On POI set change OR 30 days | Triggered after POI refresh if INSERT/DELETE count > 0 |
| `poi.historical_importance` (LLM enrichment) | On NULL or empty column | Triggered at first trip request to that POI |
| Hotel/restaurant records | 7 days | Booking availability changes faster than POI data |
| Flight records | Not persisted beyond trip planning session | Prices are volatile; re-fetch at trip activation |
| Weather data | Real-time during active trip | Fetched by `ConditionMonitor` per session event cycle |
| Traffic data | Real-time during active trip | Fetched by `TrafficAdvisor` per stop transition |

---

### 3.3 Cache Invalidation Rules

| Cache key pattern | Invalidation condition | Action |
|---|---|---|
| `dij:{city}:*` | `poi_graph_edges.last_updated` for that city changes | `DEL dij:{city}:*` then re-warm |
| `dij:{city}:{a}:{b}:{mode}` | Single edge updated in Postgres | `DEL dij:{city}:{a}:{b}:{mode}` only |
| `tripstate:{trip_id}:{user_id}` | Trip status set to `'completed'` or `'cancelled'` | `DEL tripstate:{trip_id}:{user_id}` |
| `tripstate:{trip_id}:{user_id}` | TTL expiry (86400 s) | Automatic by Redis |

---

### 3.4 TTL Definitions

| Data | Storage layer | TTL |
|---|---|---|
| `tripstate:{trip_id}:{user_id}` | Redis | 86400 seconds (24 hours from last write); reset on every HSET |
| `dij:{city}:{a}:{b}:{mode}` | Redis | MISSING: not specified in source docs; recommended = 2592000 s (30 days) to align with POI refresh cycle, but this value is not in the schema docs |
| `poi.fetched_at` age threshold | Postgres | 30 days (application enforces via `WHERE fetched_at < NOW() - INTERVAL '30 days'`) |
| Hotel/restaurant `fetched_at` | Postgres | 7 days |
| Flight `fetched_at` | Postgres | Not retained — deleted after trip activation |

---

## PART 4 — Precomputation Plan

### 4.1 Dij Matrix Computation

**Input:**
- All `(poi_id, location_lat, location_lon)` rows for a city from `poi` table
- Transport modes: `walking`, `car` (OSRM profiles: `foot`, `driving`)

**Computation:**

```
For each transport_mode in ['walking', 'car']:
    coordinates = [(lat, lon) for each poi in city]  # ordered list
    poi_ids     = [poi_id for each poi in city]       # same order

    osrm_response = GET /table/v1/{profile}/{coordinates}
        ?sources=all&destinations=all&annotations=duration

    For i in range(len(poi_ids)):
        For j in range(len(poi_ids)):
            if i == j:
                SKIP  # self-edge, not inserted
            duration_seconds = osrm_response['durations'][i][j]
            if duration_seconds is NULL:
                SKIP  # no route exists
            travel_time_minutes = duration_seconds / 60.0

            INSERT INTO poi_graph_edges
                (city, poi_a_id, poi_b_id, transport_mode, travel_time_minutes, last_updated)
            VALUES
                ({city}, {poi_ids[i]}, {poi_ids[j]}, {transport_mode}, {travel_time_minutes}, NOW())
            ON CONFLICT (uq_poi_graph_edges)
            DO UPDATE SET travel_time_minutes = EXCLUDED.travel_time_minutes,
                          last_updated = NOW();
```

**Matrix size:** For N POIs → N×(N−1) directional edge pairs × 2 transport modes.  
At N=100: 19,800 rows. At N=500: 498,000 rows.

---

### 4.2 When to Recompute

| Trigger | Scope |
|---|---|
| New POI inserted for city | Compute edges from new POI to all existing POIs (2 × (N−1) new rows) |
| POI deleted for city | `DELETE FROM poi_graph_edges WHERE poi_a_id = {id} OR poi_b_id = {id}`; no OSRM call needed |
| POI coordinates updated | Recompute all edges involving that POI |
| Scheduled 30-day refresh | Full city matrix recompute |
| OSRM server version upgrade | Full city matrix recompute |

---

### 4.3 Storage Layer Assignment

| Data | Layer | Rationale |
|---|---|---|
| All `poi_graph_edges` rows | Postgres | Persistent backing store; survives restarts; source of truth |
| Active-trip Dij lookups | Redis hot cache | ACO inner loop sub-millisecond requirement |
| Cold-city Dij (not in cache) | Postgres only | Cache-aside: miss triggers Postgres SELECT + Redis SET |
| ACO pheromone matrix τ_ij | In-process memory only | MUST NOT leave optimizer process — see Part 3 / 04-exclusions |

---

### 4.4 Cache Warm-up at Session Start

```
On trip activation (status: planned → active):

    SELECT city FROM trips WHERE trip_id = {trip_id}

    SELECT poi_a_id, poi_b_id, transport_mode, travel_time_minutes
    FROM poi_graph_edges
    WHERE city = {city}

    For each row:
        SET dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode} "{travel_time_minutes}"
        EXPIRE dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode} 86400
```

TTL on Dij cache keys set to 86400 s at warm-up (aligned with session TTL). Refreshed if session extends beyond 24 h.

---

## PART 5 — Data Validation Rules

### 5.1 Deduplication Logic

**POI deduplication** — applied after each city bootstrap and refresh:

```sql
-- Find duplicate candidates: same city, same name, coordinates within ~50m
WITH duplicates AS (
    SELECT
        poi_id,
        city,
        name,
        location_lat,
        location_lon,
        fetched_at,
        ROW_NUMBER() OVER (
            PARTITION BY city, lower(trim(name))
            ORDER BY fetched_at DESC
        ) AS rn
    FROM poi
    WHERE city = {city}
)
DELETE FROM poi
WHERE poi_id IN (
    SELECT poi_id FROM duplicates WHERE rn > 1
);
```

**Coordinate proximity deduplication** (same place, slightly different name spelling):

```sql
-- Identify POIs within 50 metres of another in the same city
-- (0.00045 degrees ≈ 50 metres at equator)
SELECT a.poi_id AS keep, b.poi_id AS discard
FROM poi a
JOIN poi b
  ON a.city = b.city
 AND a.poi_id < b.poi_id
 AND abs(a.location_lat - b.location_lat) < 0.00045
 AND abs(a.location_lon - b.location_lon) < 0.00045;
-- Resolution: retain higher-rated; if equal, retain most recently fetched
```

**poi_graph_edges deduplication** — handled by `ON CONFLICT (uq_poi_graph_edges) DO UPDATE`. No post-hoc cleanup needed.

---

### 5.2 Missing-Field Handling

| `poi` column | Absent in API response | Action |
|---|---|---|
| `rating` | Place has no ratings | Insert `NULL`; do not default |
| `opening_hours` | Not provided | Insert `NULL`; HC hc2 check skips NULL rows |
| `entry_cost` | MISSING generally | Insert `0.0`; flag in `raw_api_response` |
| `visit_duration_minutes` | MISSING generally | Apply category-default table below |
| `historical_importance` | Empty / absent | Insert `NULL`; `HistoricalInsightTool` falls back to LLM |
| `wheelchair_accessible` | Not provided | Insert `TRUE` (conservative — do not exclude accessible requirement) |
| `seasonal_open_months` | Not provided | Insert `'{}'` (open all year by default) |
| `ticket_required` | Not provided | Insert `FALSE` |
| `min_age` | Not provided | Insert `0` |

**Category-default `visit_duration_minutes` table** (applied when API provides no duration):

| Category | `visit_duration_minutes` | `min_visit_duration_minutes` |
|---|---|---|
| `museum` | 90 | 30 |
| `park` | 60 | 20 |
| `landmark` | 45 | 15 |
| `temple` / `church` / `place_of_worship` | 30 | 15 |
| `market` | 60 | 20 |
| `restaurant` | 60 | 30 |
| `hotel` | MISSING: not a visitation POI | MISSING |
| `art_gallery` | 75 | 30 |
| `aquarium` / `zoo` | 120 | 45 |
| `amusement_park` | 180 | 60 |
| `natural_feature` / `campground` | 90 | 30 |
| All others | 60 | 20 |

---

### 5.3 Unit Standardization

| Field | External unit | Internal unit | Conversion |
|---|---|---|---|
| `travel_time_minutes` | OSRM: seconds | minutes | `seconds / 60.0` |
| `travel_time_minutes` | Google Routes: `"1800s"` string | minutes | Strip `'s'`, cast INT, divide by 60 |
| `visit_duration_minutes` | Amadeus flight duration: ISO 8601 (`PT2H30M`) | minutes | Parse hours × 60 + minutes |
| `rating` (Yelp) | 1–5 float | 1–5 float | Direct; already same scale |
| `rating` (Booking.com `review_score`) | 0–10 float | 1–5 float | `review_score / 2.0` |
| `entry_cost` | Local city currency (unknown at ingestion) | `NUMERIC(8,2)` in `trips.currency` | MISSING: currency conversion not in codebase |
| Weather wind speed | m/s (OWM `metric`) | m/s | No conversion; store as-is in metadata JSONB |
| Weather precipitation | mm / 3h | mm / 3h | No conversion; store as-is |
| `total_budget` in `trips` | User-input currency | MISSING | Same as entry_cost — `CURRENCY_UNIT = "UNSPECIFIED"` in config.py |

---

### 5.4 Opening Hours Format Normalization

**Target format:** `HH:MM-HH:MM` (single string; schema `VARCHAR(32)`).

**Google Places input:** `regularOpeningHours.weekdayDescriptions[]`  
Example: `"Monday: 9:00 AM – 6:00 PM"`

**Normalization algorithm:**

```python
import re
from datetime import datetime

def normalize_opening_hours(weekday_desc: str) -> str | None:
    """
    Input:  "Monday: 9:00 AM – 6:00 PM"
    Output: "09:00-18:00"
    Returns None if pattern not matched.
    """
    pattern = r"(\d{1,2}:\d{2}\s?[AP]M)\s*[–\-]\s*(\d{1,2}:\d{2}\s?[AP]M)"
    match = re.search(pattern, weekday_desc, re.IGNORECASE)
    if not match:
        return None
    open_raw, close_raw = match.group(1), match.group(2)
    fmt = "%I:%M %p"
    open_dt  = datetime.strptime(open_raw.strip().upper(), fmt)
    close_dt = datetime.strptime(close_raw.strip().upper(), fmt)
    return f"{open_dt.strftime('%H:%M')}-{close_dt.strftime('%H:%M')}"
```

**Edge cases:**

| Input case | Handling |
|---|---|
| `"Open 24 hours"` | Store as `"00:00-23:59"` |
| `"Closed"` | Store as `NULL` |
| Multiple time ranges (e.g., split-day) | Store first range only; full text stored in `raw_api_response` |
| OSM `opening_hours` tag (e.g., `Mo-Fr 08:00-20:00`) | Parse OSM schema separately; take first day's range as representative |
| Missing entirely | Store `NULL`; HC hc2 treats NULL as always open |

---

### 5.5 Required Validation Checks Before INSERT

Applied in the ingestion layer before any Postgres INSERT:

| Check | Column | Rule |
|---|---|---|
| Non-null coordinates | `location_lat`, `location_lon` | Reject row if either is NULL or 0.0 |
| Valid latitude range | `location_lat` | Must be in [-90, 90]; reject otherwise |
| Valid longitude range | `location_lon` | Must be in [-180, 180]; reject otherwise |
| Non-empty name | `name` | Reject if blank string or NULL |
| Rating range | `rating` | If present, must be in [1, 5]; else NULL |
| Travel time non-negative | `travel_time_minutes` | Reject row if value < 0 or NULL from OSRM |
| Self-edge exclusion | `poi_a_id`, `poi_b_id` | Reject if `poi_a_id = poi_b_id` |
| Budget non-negative | `total_budget` | Reject if < 0 |
| Date ordering | `departure_date`, `return_date` | Reject if `return_date < departure_date` |
| Day number positive | `day_number` | Reject if ≤ 0 |
| Event type in allowlist | `event_type` | Must match CHECK constraint values before INSERT |
| `group_size` consistency | `group_size` | Must equal `num_adults + num_children`; enforce in application before INSERT |

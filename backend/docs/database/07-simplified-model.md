# Simplified Data Model — API-Verified Reduction

> Source constraints: 05-implementation.sql, 06-ingestion-pipeline.md
> Allowed APIs: Google Places (New), OpenStreetMap/OSRM, OpenWeather, Google Routes, Yelp (optional), Amadeus (optional)
> Date: 2026-02-23

---

## PART 1 — Schema Reduction

### Table: `users`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `user_id` | **Keep** | Application-generated UUID | Application |
| `email` | **Keep** | User-provided at registration | Registration form |
| `created_at` | **Keep** | Application timestamp | Application |
| `last_active_at` | **Keep** | Application timestamp | Application |
| `preferred_currency` | **MISSING** | `config.py` `CURRENCY_UNIT = "UNSPECIFIED"`; no API source | — |

---

### Table: `user_memory_profile`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `user_id` | **Keep** | FK | Application |
| `sc_weights` | **Keep** | Initialized to `[0.25, 0.20, 0.30, 0.15, 0.10]`; updated via λ-learning from session feedback | Application (λ-learning) |
| `learning_rate` | **Keep** | Application constant; default λ=0.1 | Application |
| `interests` | **Keep** | User-provided at onboarding | User input |
| `dietary_preferences` | **Keep** | User-provided | User input |
| `travel_preferences` | **Keep** | User-provided | User input |
| `character_traits` | **Keep** | User-provided | User input |
| `pace_preference` | **Keep** | User-provided | User input |
| `avoid_crowds` | **Keep** | User-provided | User input |
| `preferred_transport_mode` | **Keep** | User-provided | User input |
| `rest_interval_minutes` | **Keep** | User-provided or hardcoded default | User input |
| `heavy_travel_penalty` | **Keep** | User-provided | User input |
| `avoid_consecutive_same_category` | **Keep** | User-provided | User input |
| `novelty_spread` | **Keep** | User-provided | User input |
| `commonsense_rules` | **REMOVE** | LLM-extracted; no verifiable API source; per 04-data-exclusions rule #12 | — |
| `last_updated` | **Keep** | Application timestamp | Application |

---

### Table: `trips`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `trip_id` | **Keep** | Application-generated UUID | Application |
| `user_id` | **Keep** | FK | Application |
| `destination_city` | **Keep** | User-provided | User input |
| `departure_city` | **Keep** | User-provided | User input |
| `departure_date` | **Keep** | User-provided | User input |
| `return_date` | **Keep** | User-provided | User input |
| `num_adults` | **Keep** | User-provided | User input |
| `num_children` | **Keep** | User-provided | User input |
| `group_size` | **DERIVED** | `num_adults + num_children` at INSERT; no external API needed | Application |
| `traveler_ages` | **REMOVE** | Only used for HC hc4 (min_age); min_age removed — no API source for per-POI age restrictions | — |
| `requires_wheelchair` | **Keep** | User-provided; enforces HC against `poi.wheelchair_accessible` from Google Places | User input |
| `restaurant_preference` | **Keep** | User-provided | User input |
| `fixed_appointments` | **Keep** | User-provided | User input |
| `visa_restricted_countries` | **REMOVE** | No visa data API in allowed sources | — |
| `total_budget` | **Keep** | User-provided | User input |
| `currency` | **MISSING** | `config.py` `CURRENCY_UNIT = "UNSPECIFIED"`; no API source | — |
| `status` | **Keep** | Application state machine | Application |
| `generated_at` | **Keep** | Application timestamp | Application |
| `budget_allocation` | **Keep** | Computed from `total_budget` by `budget_planner.py` | Application |

---

### Table: `poi`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `poi_id` | **Keep** | Application UUID | Application |
| `city` | **Keep** | Bootstrap job input parameter | Application |
| `name` | **Keep** | `displayName.text` | Google Places API |
| `location_lat` | **Keep** | `location.latitude` | Google Places API |
| `location_lon` | **Keep** | `location.longitude` | Google Places API |
| `opening_hours` | **Keep** | `regularOpeningHours.weekdayDescriptions[0]`; normalized to `HH:MM-HH:MM` | Google Places API |
| `rating` | **Keep** | `rating` (FLOAT 1–5); `NULL` if absent | Google Places API |
| `visit_duration_minutes` | **DERIVED** | No API provides typical visit duration; derived from deterministic category-default table — see Part 5 | Category-default table |
| `min_visit_duration_minutes` | **DERIVED** | Same derivation as `visit_duration_minutes` | Category-default table |
| `entry_cost` | **REMOVE** | Google Places `priceLevel` is an ordinal enum (FREE/INEXPENSIVE/MODERATE/EXPENSIVE/VERY_EXPENSIVE); no numeric per-person cost available from any allowed API | — |
| `category` | **DERIVED** | Mapped from `types[0]` via deterministic normalization table — see Part 5 | Google Places `types[]` |
| `optimal_visit_time` | **REMOVE** | Not provided by any allowed API | — |
| `wheelchair_accessible` | **Keep** | `accessibilityOptions.wheelchairAccessibleEntrance`; absent → `TRUE` (conservative) | Google Places API |
| `min_age` | **REMOVE** | Not provided by any allowed API | — |
| `ticket_required` | **REMOVE** | Not reliably derivable from `priceLevel`; inference too unreliable | — |
| `min_group_size` | **REMOVE** | Not provided by any allowed API | — |
| `max_group_size` | **REMOVE** | Not provided by any allowed API | — |
| `seasonal_open_months` | **REMOVE** | `regularOpeningHours.specialDays` is not a reliable seasonal availability source; inconsistently populated | — |
| `is_outdoor` | **DERIVED** | `TRUE` if `types[]` intersects `{park, natural_feature, campground, beach, hiking_area}`; else `FALSE` | Google Places `types[]` |
| `intensity_level` | **REMOVE** | Not provided by any allowed API; derivation from category is speculative | — |
| `historical_importance` | **Keep** | `editorialSummary.text`; `NULL` if absent; no LLM invention | Google Places API |
| `source_api` | **Keep** | Caller-set audit field | Application |
| `raw_api_response` | **Keep** | Full API response blob; JSONB | Google Places API |
| `fetched_at` | **Keep** | Application timestamp | Application |

---

### Table: `poi_graph_edges`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `edge_id` | **Keep** | BIGSERIAL auto | Application |
| `city` | **Keep** | Bootstrap job input | Application |
| `poi_a_id` | **Keep** | FK → poi | Application |
| `poi_b_id` | **Keep** | FK → poi | Application |
| `transport_mode` | **Keep** | Limited to `walking` (OSRM `foot`) and `car` (OSRM `driving`); `public_transit` is **MISSING** — OSRM does not support transit | OSRM Table API |
| `travel_time_minutes` | **Keep** | `durations[i][j] / 60.0`; skip row if OSRM returns `null` | OSRM Table API |
| `last_updated` | **Keep** | Application timestamp | Application |

---

### Table: `itinerary_days`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `day_id` | **Keep** | Application UUID | Application |
| `trip_id` | **Keep** | FK | Application |
| `day_number` | **Keep** | 1-indexed integer | Application |
| `date` | **Keep** | Derived from `trips.departure_date + day_number - 1` | Application |
| `daily_budget_used` | **Keep** | Computed from route_points `estimated_cost` sum | Application |
| `route_points` | **Keep** | JSONB array of `RoutePoint` objects | Application |
| `replan_version` | **Keep** | Incremented by `PartialReplanner.replan()` | Application |

---

### Table: `disruption_events`

| Column | Status | Reason | Data Source |
|---|---|---|---|
| `event_id` | **Keep** | Application UUID | Application |
| `trip_id` | **Keep** | FK | Application |
| `day_number` | **Keep** | Session state | Application |
| `event_type` | **Keep** | Enumerated application event | Application |
| `trigger_time` | **Keep** | Session clock `HH:MM` | Application |
| `severity` | **Keep** | Weather: derived from OpenWeather response; Traffic: derived from Google Routes ratio; User events: `0.0` | OpenWeather / Google Routes / Application |
| `impacted_stops` | **Keep** | Session state | Application |
| `action_taken` | **Keep** | Session event handler output | Application |
| `user_response` | **Keep** | Approval gate output | Application |
| `s_pti_affected` | **Keep** | Computed S_pti at event time | Application |
| `metadata` | **Keep** | Type-specific JSONB; weather fields from OpenWeather; traffic fields from Google Routes | OpenWeather / Google Routes / Application |
| `recorded_at` | **Keep** | Application timestamp | Application |

---

## PART 2 — Simplified S_pti Formulation

### Removed SC dimensions (no API backing)

| Original SC | Reason for removal |
|---|---|
| SC_1 (optimal visit time proximity) | `optimal_visit_time` removed — no API source |
| SC_5 (activity intensity match) | `intensity_level` removed — no API source |

### Surviving SC dimensions

| Dimension | Symbol | Source field | Range | Default weight |
|---|---|---|---|---|
| Rating quality | SC_r | `poi.rating` (Google Places) | [0, 1] | 0.40 |
| User interest match | SC_p | `poi.category` ∩ `user_memory_profile.interests` | [0, 1] | 0.35 |
| Outdoor preference match | SC_o | `poi.is_outdoor` vs `user_memory_profile.pace_preference` + `avoid_crowds` | [0, 1] | 0.25 |

**Weight vector:** `[W_r, W_p, W_o]` where `W_r + W_p + W_o = 1.0`

Default values: `[0.40, 0.35, 0.25]`

**Revised S_pti formula:**

$$S_{pti} = HC_{pti} \times \left( W_r \cdot SC_r + W_p \cdot SC_p + W_o \cdot SC_o \right)$$

### Dimension computation rules

**SC_r — Rating:**

$$SC_r = \begin{cases} \frac{rating - 1}{4} & \text{if } rating \in [1, 5] \\ 0.5 & \text{if } rating = \text{NULL} \end{cases}$$

**SC_p — Interest match:**

$$SC_p = \begin{cases} 1.0 & \text{if } poi.category \in user.interests \\ 0.0 & \text{otherwise} \end{cases}$$

Where `user.interests` is the `TEXT[]` array from `user_memory_profile.interests`.

**SC_o — Outdoor preference match:**

| `poi.is_outdoor` | `pace_preference` | `avoid_crowds` | SC_o |
|---|---|---|---|
| TRUE | `relaxed` or `moderate` | any | 0.8 |
| TRUE | `packed` | any | 0.5 |
| FALSE | `relaxed` | TRUE | 0.6 |
| FALSE | `relaxed` | FALSE | 0.7 |
| FALSE | `moderate` or `packed` | any | 0.9 |

### ACO heuristic (unchanged form)

$$\eta_{ij} = \frac{S_{pti}}{D_{ij}}$$

$$P_{ij} = \frac{\tau_{ij}^\alpha \cdot \eta_{ij}^\beta}{\sum_{k \in \text{feasible}} \tau_{ik}^\alpha \cdot \eta_{ik}^\beta}$$

Where all variables retain definitions from `config.py`: `α=2.0, β=3.0`.

---

## PART 3 — Simplified Hard Constraints

### Retained HC (real-data enforceable)

| HC | Name | Enforcement rule | Data Source |
|---|---|---|---|
| HC_1 | Opening hours | `current_time` (HH:MM) must fall within `poi.opening_hours` (HH:MM-HH:MM); if `poi.opening_hours` is NULL → pass (conservative) | Google Places API |
| HC_2 | Wheelchair accessibility | If `trips.requires_wheelchair = TRUE` → `poi.wheelchair_accessible` MUST be `TRUE` | Google Places API |
| HC_3 | Budget limit | Cumulative route cost ≤ `trips.total_budget`; cost estimated from `budget_allocation` proportions (no per-POI numeric cost) | User input |
| HC_4 | Daily time window (Tmax) | `Σ (visit_duration_minutes + Dij) ≤ Tmax`; all times in minutes | OSRM (Dij) + Category-default (STi) |
| HC_5 | Weather safety | `weather_severity < HC_UNSAFE_THRESHOLD (0.75)` → POI not blocked; derived from OpenWeather response by `ConditionMonitor._derive_thresholds()` | OpenWeather API |

### Removed HC (no API backing)

| Removed HC | Original purpose | Reason |
|---|---|---|
| HC hc4 (min_age) | Block POI if traveler age below minimum | `min_age` removed — no API source |
| HC hc5 (ticket_required) | Enforce pre-booking constraint | `ticket_required` removed — unreliable from `priceLevel` |
| HC hc6 (group size bounds) | Block POI if group too small or too large | `min_group_size`, `max_group_size` removed — no API source |
| HC hc7 (seasonal availability) | Block POI if out of season | `seasonal_open_months` removed — no reliable API source |

**HC_pti:**

$$HC_{pti} = \prod_{c \in \{HC_1, HC_2, HC_3, HC_4, HC_5\}} hc_c$$

Where each $hc_c \in \{0, 1\}$; result is 0 if ANY retained constraint is violated.

---

## PART 4 — Simplified Optimization Inputs

### Graph

| Symbol | Definition | Source |
|---|---|---|
| V | Set of `poi_id` values for the destination city | `SELECT poi_id FROM poi WHERE city = {city}` |
| E | Set of directed edges `(poi_a_id, poi_b_id, transport_mode)` | `poi_graph_edges` table |

### D_ij — Travel time matrix

| Property | Value |
|---|---|
| Unit | Minutes (FLOAT) |
| Transport modes | `walking`, `car` only; `public_transit` MISSING |
| Primary source | OSRM Table API → `poi_graph_edges.travel_time_minutes` |
| Hot-path source | Redis key `dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}` |
| On Redis miss | `SELECT travel_time_minutes FROM poi_graph_edges WHERE city=? AND poi_a_id=? AND poi_b_id=? AND transport_mode=?` |
| NULL handling | If OSRM returns `null` for a pair → edge not stored → pair treated as unreachable |

### S_i — Composite stop score

| Property | Value |
|---|---|
| Formula | $S_i = HC_{pti} \times (W_r \cdot SC_r + W_p \cdot SC_p + W_o \cdot SC_o)$ |
| Range | [0, 1] |
| Inputs | `poi.rating`, `poi.category`, `poi.is_outdoor`, `user_memory_profile.*` |
| Disruption flag overlay | If `weather_severity ≥ HC_UNSAFE_THRESHOLD` → $HC_{pti} = 0$, $S_i = 0$ |

### ST_i — Stop service time (visit duration)

| Property | Value |
|---|---|
| Source | `poi.visit_duration_minutes` |
| Derivation | Category-default table below (no API provides this value) |
| Unit | Minutes |

**Category-default ST_i table:**

| `poi.category` | `visit_duration_minutes` (ST_i) | `min_visit_duration_minutes` |
|---|---|---|
| `museum` | 90 | 30 |
| `park` | 60 | 20 |
| `landmark` | 45 | 15 |
| `temple` / `place_of_worship` | 30 | 15 |
| `market` | 60 | 20 |
| `art_gallery` | 75 | 30 |
| `aquarium` / `zoo` | 120 | 45 |
| `amusement_park` | 180 | 60 |
| `natural_feature` / `campground` | 90 | 30 |
| `restaurant` | 60 | 30 |
| `hotel` | MISSING | MISSING |
| All others | 60 | 20 |

### T_max — Daily time budget

| Property | Value |
|---|---|
| Unit | Minutes |
| Source | User-provided trip start/end times, or default window |
| Default | 600 minutes (10:00–20:00) if not user-specified |
| Application | `Σ (ST_i + D_ij) ≤ T_max` across all stops in a DayPlan |

---

## PART 5 — Final Simplified Data Model

### `users`

| Column | Type | Constraint |
|---|---|---|
| `user_id` | UUID | PK |
| `email` | VARCHAR(320) | UNIQUE NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `last_active_at` | TIMESTAMPTZ | |
| `preferred_currency` | CHAR(3) | **MISSING** |

---

### `user_memory_profile`

| Column | Type | Constraint |
|---|---|---|
| `user_id` | UUID | PK FK → users |
| `sc_weights` | JSONB | 3-key: `{"sc_r": 0.40, "sc_p": 0.35, "sc_o": 0.25}` |
| `learning_rate` | FLOAT | NOT NULL DEFAULT 0.1 |
| `interests` | TEXT[] | NOT NULL DEFAULT '{}' |
| `dietary_preferences` | TEXT[] | NOT NULL DEFAULT '{}' |
| `travel_preferences` | TEXT[] | NOT NULL DEFAULT '{}' |
| `character_traits` | TEXT[] | NOT NULL DEFAULT '{}' |
| `pace_preference` | VARCHAR(16) | CHECK IN ('relaxed','moderate','packed') |
| `avoid_crowds` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `preferred_transport_mode` | TEXT[] | NOT NULL DEFAULT '{}' |
| `rest_interval_minutes` | INT | |
| `heavy_travel_penalty` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `avoid_consecutive_same_category` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `novelty_spread` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `last_updated` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Removed from original:** `commonsense_rules`

---

### `trips`

| Column | Type | Constraint |
|---|---|---|
| `trip_id` | UUID | PK |
| `user_id` | UUID | NOT NULL FK → users |
| `destination_city` | VARCHAR(255) | NOT NULL |
| `departure_city` | VARCHAR(255) | NOT NULL |
| `departure_date` | DATE | NOT NULL |
| `return_date` | DATE | NOT NULL |
| `num_adults` | SMALLINT | NOT NULL DEFAULT 1 |
| `num_children` | SMALLINT | NOT NULL DEFAULT 0 |
| `group_size` | SMALLINT | NOT NULL DERIVED: num_adults + num_children |
| `requires_wheelchair` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `restaurant_preference` | VARCHAR(255) | |
| `fixed_appointments` | JSONB | NOT NULL DEFAULT '[]' |
| `total_budget` | NUMERIC(12,2) | NOT NULL CHECK ≥ 0 |
| `currency` | CHAR(3) | **MISSING** |
| `status` | VARCHAR(16) | CHECK IN ('planned','active','completed','cancelled') |
| `generated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `budget_allocation` | JSONB | NOT NULL DEFAULT '{}' |

**Removed from original:** `traveler_ages`, `visa_restricted_countries`

---

### `poi`

| Column | Type | Source / Status |
|---|---|---|
| `poi_id` | UUID | PK — Application |
| `city` | VARCHAR(255) | NOT NULL — Bootstrap input |
| `name` | VARCHAR(255) | NOT NULL — Google Places `displayName.text` |
| `location_lat` | DOUBLE PRECISION | NOT NULL — Google Places `location.latitude` |
| `location_lon` | DOUBLE PRECISION | NOT NULL — Google Places `location.longitude` |
| `opening_hours` | VARCHAR(32) | Google Places `regularOpeningHours`; normalized HH:MM-HH:MM |
| `rating` | FLOAT | Google Places `rating`; NULL if absent |
| `visit_duration_minutes` | SMALLINT | DERIVED — category-default table |
| `min_visit_duration_minutes` | SMALLINT | DERIVED — category-default table |
| `category` | VARCHAR(64) | DERIVED — from Google Places `types[0]` |
| `wheelchair_accessible` | BOOLEAN | NOT NULL DEFAULT TRUE — Google Places `accessibilityOptions` |
| `is_outdoor` | BOOLEAN | NOT NULL DEFAULT FALSE — DERIVED from Google Places `types[]` |
| `historical_importance` | TEXT | Google Places `editorialSummary.text`; NULL if absent |
| `source_api` | VARCHAR(32) | Application — CHECK IN ('serpapi','manual','stub') |
| `raw_api_response` | JSONB | Full Google Places response |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Removed from original:** `entry_cost`, `optimal_visit_time`, `min_age`, `ticket_required`, `min_group_size`, `max_group_size`, `seasonal_open_months`, `intensity_level`

**Required indexes (unchanged):**
- `GIN` on `to_tsvector('english', coalesce(historical_importance, ''))`
- Composite `(city, category)`
- Composite `(city, location_lat, location_lon)`

---

### `poi_graph_edges`

| Column | Type | Source / Status |
|---|---|---|
| `edge_id` | BIGSERIAL | PK |
| `city` | VARCHAR(255) | NOT NULL — Bootstrap input |
| `poi_a_id` | UUID | NOT NULL FK → poi |
| `poi_b_id` | UUID | NOT NULL FK → poi |
| `transport_mode` | VARCHAR(32) | NOT NULL CHECK IN ('walking','car') — `public_transit` MISSING |
| `travel_time_minutes` | FLOAT | NOT NULL ≥ 0 — OSRM Table `durations[i][j] / 60.0` |
| `last_updated` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**UNIQUE constraint:** `(city, poi_a_id, poi_b_id, transport_mode)`

---

### `itinerary_days`

| Column | Type | Notes |
|---|---|---|
| `day_id` | UUID | PK |
| `trip_id` | UUID | NOT NULL FK → trips |
| `day_number` | SMALLINT | NOT NULL CHECK ≥ 1 |
| `date` | DATE | |
| `daily_budget_used` | NUMERIC(10,2) | NOT NULL DEFAULT 0.0 |
| `route_points` | JSONB | NOT NULL DEFAULT '[]' |
| `replan_version` | SMALLINT | NOT NULL DEFAULT 0 |

**UNIQUE constraint:** `(trip_id, day_number)`

---

### `disruption_events`

| Column | Type | Notes |
|---|---|---|
| `event_id` | UUID | PK |
| `trip_id` | UUID | NOT NULL FK → trips |
| `day_number` | SMALLINT | NOT NULL |
| `event_type` | VARCHAR(32) | NOT NULL CHECK IN ('weather','traffic','crowd','hunger','fatigue','venue_closed','user_skip','user_replace','user_reorder','manual_reopt','generic') |
| `trigger_time` | VARCHAR(5) | HH:MM |
| `severity` | FLOAT | NOT NULL DEFAULT 0.0 |
| `impacted_stops` | TEXT[] | NOT NULL DEFAULT '{}' |
| `action_taken` | VARCHAR(64) | |
| `user_response` | VARCHAR(16) | CHECK IN ('APPROVE','REJECT','MODIFY','accepted','skipped') |
| `s_pti_affected` | FLOAT | |
| `metadata` | JSONB | NOT NULL DEFAULT '{}' |
| `recorded_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

---

### Redis keys (unchanged)

| Key | Type | TTL |
|---|---|---|
| `tripstate:{trip_id}:{user_id}` | Hash | 86400 s |
| `dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}` | String (float) | MISSING |

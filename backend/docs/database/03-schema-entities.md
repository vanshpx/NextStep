# Database Architecture — Schema Entities

> System: Travel Itinerary Optimizer (TravelAgent + ICDM + FTRM + ACO + Re-optimization Engine)
> Created: 2026-02-23
> Storage: PostgreSQL with JSONB | Redis (TripState / Dij cache)

---

## `users`

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID PK | |
| `email` | VARCHAR UNIQUE | MISSING in codebase — required for auth |
| `created_at` | TIMESTAMPTZ | |
| `last_active_at` | TIMESTAMPTZ | |
| `preferred_currency` | CHAR(3) | MISSING in codebase — ISO 4217 |

---

## `user_memory_profile`

Maps to: `LongTermMemory._user_profiles` + `SoftConstraints` + Wv weight vector

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID PK FK → users | |
| `sc_weights` | JSONB | `{"sc1":0.25,"sc2":0.20,"sc3":0.30,"sc4":0.15,"sc5":0.10}` |
| `learning_rate` | FLOAT | λ — default 0.1 |
| `interests` | TEXT[] | activity categories |
| `dietary_preferences` | TEXT[] | vegan, halal, etc. |
| `travel_preferences` | TEXT[] | adventure, relaxed, cultural… |
| `character_traits` | TEXT[] | avoids_crowds, budget_conscious… |
| `pace_preference` | VARCHAR | `relaxed\|moderate\|packed` |
| `avoid_crowds` | BOOLEAN | |
| `preferred_transport_mode` | TEXT[] | walking, public_transit, taxi… |
| `rest_interval_minutes` | INT | max consecutive activity minutes |
| `heavy_travel_penalty` | BOOLEAN | penalise high-intensity on arrival/departure days |
| `avoid_consecutive_same_category` | BOOLEAN | |
| `novelty_spread` | BOOLEAN | |
| `commonsense_rules` | TEXT[] | promoted from session CommonsenseConstraints |
| `last_updated` | TIMESTAMPTZ | |

---

## `trips`

Maps to: `HardConstraints` + `Itinerary` header + `BudgetAllocation`

| Column | Type | Notes |
|---|---|---|
| `trip_id` | UUID PK | = `Itinerary.trip_id` |
| `user_id` | UUID FK → users | |
| `destination_city` | VARCHAR | |
| `departure_city` | VARCHAR | |
| `departure_date` | DATE | |
| `return_date` | DATE | |
| `num_adults` | SMALLINT | |
| `num_children` | SMALLINT | |
| `group_size` | SMALLINT | derived: num_adults + num_children |
| `traveler_ages` | SMALLINT[] | for HC hc4 (min_age check) |
| `requires_wheelchair` | BOOLEAN | HC hc3 across all POI types |
| `restaurant_preference` | VARCHAR | cuisine / dietary string from Phase 1 |
| `fixed_appointments` | JSONB | `[{name, date, time, duration_minutes, type}]` |
| `visa_restricted_countries` | CHAR(2)[] | ISO country codes |
| `total_budget` | NUMERIC(12,2) | |
| `currency` | CHAR(3) | MISSING in codebase |
| `status` | VARCHAR | `planned\|active\|completed\|cancelled` |
| `generated_at` | TIMESTAMPTZ | Stage 4 output timestamp |
| `budget_allocation` | JSONB | embedded `BudgetAllocation` — 6 float fields: Accommodation, Attractions, Restaurants, Transportation, Other_Expenses, Reserve_Fund |

---

## `poi`

Maps to: `AttractionRecord`

| Column | Type | Notes |
|---|---|---|
| `poi_id` | UUID PK | |
| `city` | VARCHAR | |
| `name` | VARCHAR | |
| `location_lat` | DOUBLE PRECISION | |
| `location_lon` | DOUBLE PRECISION | |
| `opening_hours` | VARCHAR | `HH:MM-HH:MM` |
| `rating` | FLOAT | 1–5 |
| `visit_duration_minutes` | SMALLINT | typical duration |
| `min_visit_duration_minutes` | SMALLINT | HC hc8 |
| `entry_cost` | NUMERIC(8,2) | per person |
| `category` | VARCHAR | museum, park, landmark, temple, market… |
| `optimal_visit_time` | VARCHAR | `HH:MM-HH:MM` — SC sc1 |
| `wheelchair_accessible` | BOOLEAN | HC hc3 |
| `min_age` | SMALLINT | HC hc4 — 0 = no restriction |
| `ticket_required` | BOOLEAN | HC hc5 |
| `min_group_size` | SMALLINT | HC hc6 |
| `max_group_size` | SMALLINT | HC hc6 — 999 = unlimited |
| `seasonal_open_months` | SMALLINT[] | HC hc7 — empty = open all year |
| `is_outdoor` | BOOLEAN | SC sc4/sc5 |
| `intensity_level` | VARCHAR | `low\|medium\|high` — SC sc5 |
| `historical_importance` | TEXT | Full-text indexed — HistoricalInsightTool priority source |
| `source_api` | VARCHAR | `serpapi\|manual\|stub` |
| `raw_api_response` | JSONB | unprocessed external API response |
| `fetched_at` | TIMESTAMPTZ | used for cache TTL invalidation |

**Required indexes:**
- `GIN` on `to_tsvector('english', historical_importance)` — HistoricalInsightTool
- Composite `(city, category)` — recommender filtering
- Composite `(city, location_lat, location_lon)` — proximity / cluster

---

## `poi_graph_edges`

Maps to: `DistanceTool` output / Dij matrix used by ACO

| Column | Type | Notes |
|---|---|---|
| `edge_id` | BIGSERIAL PK | |
| `city` | VARCHAR | |
| `poi_a_id` | UUID FK → poi | |
| `poi_b_id` | UUID FK → poi | |
| `transport_mode` | VARCHAR | `walking\|public_transit\|taxi\|car` |
| `travel_time_minutes` | FLOAT | Dij — CONFIRMED unit: minutes |
| `last_updated` | TIMESTAMPTZ | |

**Required indexes:**
- UNIQUE `(city, poi_a_id, poi_b_id, transport_mode)` — prevents duplicates, drives point lookups
- Redis mirror key: `dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}` → float, with TTL

---

## `itinerary_days`

Maps to: `DayPlan` + embedded `RoutePoint[]`

| Column | Type | Notes |
|---|---|---|
| `day_id` | UUID PK | |
| `trip_id` | UUID FK → trips | |
| `day_number` | SMALLINT | 1-indexed |
| `date` | DATE | |
| `daily_budget_used` | NUMERIC(10,2) | |
| `route_points` | JSONB | Array of `{sequence, name, lat, lon, arrival_time, departure_time, visit_duration_minutes, activity_type, estimated_cost, notes}` |
| `replan_version` | SMALLINT | incremented on each PartialReplanner replan — full audit trail |

---

## `disruption_events`

Maps to: `DisruptionMemory` — WeatherRecord, TrafficRecord, ReplacementRecord, HungerRecord, FatigueRecord, record_generic()

| Column | Type | Notes |
|---|---|---|
| `event_id` | UUID PK | |
| `trip_id` | UUID FK → trips | |
| `day_number` | SMALLINT | |
| `event_type` | VARCHAR | `weather\|traffic\|crowd\|hunger\|fatigue\|venue_closed\|user_skip\|user_replace\|user_reorder\|manual_reopt\|generic` |
| `trigger_time` | VARCHAR | `HH:MM` — 24h trip-clock time |
| `severity` | FLOAT | 0.0 for user-triggered actions |
| `impacted_stops` | TEXT[] | stop names affected |
| `action_taken` | VARCHAR | e.g. `meal_inserted`, `reschedule_same_day`, `APPROVE`, `REJECT` |
| `user_response` | VARCHAR | `APPROVE\|REJECT\|MODIFY\|accepted\|skipped` |
| `s_pti_affected` | FLOAT | avg S_pti of impacted stops at event time |
| `metadata` | JSONB | type-specific fields (e.g. `{condition, threshold, blocked_count}` for weather; `{traffic_level, delay_minutes, deferred_stops}` for traffic) |
| `recorded_at` | TIMESTAMPTZ | wall-clock timestamp |

---

## Redis Key Schema (TripState)

Active TripState stored as a Redis Hash, key: `tripstate:{trip_id}:{user_id}`

| Hash Field | Type | Source |
|---|---|---|
| `current_time` | STRING | `HH:MM` |
| `current_lat` | FLOAT | |
| `current_lon` | FLOAT | |
| `current_day` | INT | 1-indexed |
| `visited_stops` | JSON array | `TripState.visited_stops` |
| `skipped_stops` | JSON array | `TripState.skipped_stops` |
| `deferred_stops` | JSON array | `TripState.deferred_stops` |
| `hunger_level` | FLOAT | 0.0–1.0 |
| `fatigue_level` | FLOAT | 0.0–1.0 |
| `last_meal_time` | STRING | `HH:MM` |
| `last_rest_time` | STRING | `HH:MM` |
| `minutes_on_feet` | INT | |
| `replan_pending` | BOOLEAN | |
| `pending_decision` | JSON blob | serialized `PendingDecision` or null |
| `budget_spent` | JSON object | 6-key budget category map |
| `disruption_memory_snapshot` | JSON blob | `DisruptionMemory.serialize()` output |

**TTL:** 24 hours from last write. AOF persistence enabled to survive process restarts.

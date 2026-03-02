-- =============================================================================
-- Travel Itinerary Optimizer — Full Database Implementation
-- Source: docs/database/01-data-categories.md
--         docs/database/02-polyglot-persistence.md
--         docs/database/03-schema-entities.md
--         docs/database/04-data-exclusions.md
-- =============================================================================


-- =============================================================================
-- PART 1 — PostgreSQL DDL
-- =============================================================================

-- ---------------------------------------------------------------------------
-- PART 4 prerequisite: Required extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- GIN trigram (future use on names)
-- Note: tsvector GIN indexes use built-in text search; no extra extension needed.


-- ---------------------------------------------------------------------------
-- TABLE: users
-- Source: schema-entities.md § users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    user_id           UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    email             VARCHAR(320)  NOT NULL UNIQUE,   -- MISSING in codebase — added per doc requirement
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    last_active_at    TIMESTAMPTZ,
    preferred_currency CHAR(3)                         -- MISSING in codebase — ISO 4217
);


-- ---------------------------------------------------------------------------
-- TABLE: user_memory_profile
-- Source: schema-entities.md § user_memory_profile
-- Maps to: LongTermMemory._user_profiles + SoftConstraints + Wv weight vector
-- ---------------------------------------------------------------------------
CREATE TABLE user_memory_profile (
    user_id                          UUID          PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    sc_weights                       JSONB,        -- {"sc1":0.25,"sc2":0.20,"sc3":0.30,"sc4":0.15,"sc5":0.10}
    learning_rate                    FLOAT         NOT NULL DEFAULT 0.1,   -- λ
    interests                        TEXT[]        NOT NULL DEFAULT '{}',
    dietary_preferences              TEXT[]        NOT NULL DEFAULT '{}',
    travel_preferences               TEXT[]        NOT NULL DEFAULT '{}',
    character_traits                 TEXT[]        NOT NULL DEFAULT '{}',
    pace_preference                  VARCHAR(16)   CHECK (pace_preference IN ('relaxed', 'moderate', 'packed')),
    avoid_crowds                     BOOLEAN       NOT NULL DEFAULT FALSE,
    preferred_transport_mode         TEXT[]        NOT NULL DEFAULT '{}',
    rest_interval_minutes            INT,
    heavy_travel_penalty             BOOLEAN       NOT NULL DEFAULT TRUE,
    avoid_consecutive_same_category  BOOLEAN       NOT NULL DEFAULT TRUE,
    novelty_spread                   BOOLEAN       NOT NULL DEFAULT TRUE,
    commonsense_rules                TEXT[]        NOT NULL DEFAULT '{}',
    last_updated                     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- TABLE: trips
-- Source: schema-entities.md § trips
-- Maps to: HardConstraints + Itinerary header + BudgetAllocation
-- ---------------------------------------------------------------------------
CREATE TABLE trips (
    trip_id                  UUID           PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                  UUID           NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    destination_city         VARCHAR(255)   NOT NULL,
    departure_city           VARCHAR(255)   NOT NULL,
    departure_date           DATE           NOT NULL,
    return_date              DATE           NOT NULL,
    num_adults               SMALLINT       NOT NULL DEFAULT 1 CHECK (num_adults >= 0),
    num_children             SMALLINT       NOT NULL DEFAULT 0 CHECK (num_children >= 0),
    group_size               SMALLINT       NOT NULL CHECK (group_size >= 1),  -- derived: num_adults + num_children; stored for query performance
    traveler_ages            SMALLINT[]     NOT NULL DEFAULT '{}',             -- HC hc4
    requires_wheelchair      BOOLEAN        NOT NULL DEFAULT FALSE,             -- HC hc3
    restaurant_preference    VARCHAR(255),
    fixed_appointments       JSONB          NOT NULL DEFAULT '[]',             -- [{name, date, time, duration_minutes, type}]
    visa_restricted_countries CHAR(2)[]    NOT NULL DEFAULT '{}',             -- ISO country codes
    total_budget             NUMERIC(12,2)  NOT NULL CHECK (total_budget >= 0),
    currency                 CHAR(3),                                          -- MISSING in codebase
    status                   VARCHAR(16)    NOT NULL DEFAULT 'planned'
                                            CHECK (status IN ('planned', 'active', 'completed', 'cancelled')),
    generated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    budget_allocation        JSONB          NOT NULL DEFAULT '{}'              -- BudgetAllocation: 6 float fields
);

CREATE INDEX idx_trips_user_id ON trips(user_id);
CREATE INDEX idx_trips_status  ON trips(status);


-- ---------------------------------------------------------------------------
-- TABLE: poi
-- Source: schema-entities.md § poi
-- Maps to: AttractionRecord
-- ---------------------------------------------------------------------------
CREATE TABLE poi (
    poi_id                     UUID           PRIMARY KEY DEFAULT uuid_generate_v4(),
    city                       VARCHAR(255)   NOT NULL,
    name                       VARCHAR(255)   NOT NULL,
    location_lat               DOUBLE PRECISION NOT NULL,
    location_lon               DOUBLE PRECISION NOT NULL,
    opening_hours              VARCHAR(32),                                 -- HH:MM-HH:MM
    rating                     FLOAT          CHECK (rating >= 1 AND rating <= 5),
    visit_duration_minutes     SMALLINT       NOT NULL DEFAULT 60,
    min_visit_duration_minutes SMALLINT       NOT NULL DEFAULT 15,          -- HC hc8
    entry_cost                 NUMERIC(8,2)   NOT NULL DEFAULT 0.0,
    category                   VARCHAR(64),
    optimal_visit_time         VARCHAR(32),                                 -- HH:MM-HH:MM, SC sc1
    wheelchair_accessible      BOOLEAN        NOT NULL DEFAULT TRUE,        -- HC hc3
    min_age                    SMALLINT       NOT NULL DEFAULT 0,           -- HC hc4; 0 = no restriction
    ticket_required            BOOLEAN        NOT NULL DEFAULT FALSE,       -- HC hc5
    min_group_size             SMALLINT       NOT NULL DEFAULT 1,           -- HC hc6
    max_group_size             SMALLINT       NOT NULL DEFAULT 999,         -- HC hc6; 999 = unlimited
    seasonal_open_months       SMALLINT[]     NOT NULL DEFAULT '{}',        -- HC hc7; empty = open all year
    is_outdoor                 BOOLEAN        NOT NULL DEFAULT FALSE,       -- SC sc4/sc5
    intensity_level            VARCHAR(8)     NOT NULL DEFAULT 'low'
                                               CHECK (intensity_level IN ('low', 'medium', 'high')),  -- SC sc5
    historical_importance      TEXT,                                        -- Full-text indexed
    source_api                 VARCHAR(32)    CHECK (source_api IN ('serpapi', 'manual', 'stub')),
    raw_api_response           JSONB,                                       -- unprocessed external API response
    fetched_at                 TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Required indexes (source: schema-entities.md § poi)
CREATE INDEX idx_poi_fts_historical
    ON poi USING GIN (to_tsvector('english', coalesce(historical_importance, '')));

CREATE INDEX idx_poi_city_category
    ON poi(city, category);

CREATE INDEX idx_poi_city_latlon
    ON poi(city, location_lat, location_lon);


-- ---------------------------------------------------------------------------
-- TABLE: poi_graph_edges
-- Source: schema-entities.md § poi_graph_edges
-- Maps to: DistanceTool output / Dij matrix used by ACO
-- ---------------------------------------------------------------------------
CREATE TABLE poi_graph_edges (
    edge_id             BIGSERIAL      PRIMARY KEY,
    city                VARCHAR(255)   NOT NULL,
    poi_a_id            UUID           NOT NULL REFERENCES poi(poi_id) ON DELETE CASCADE,
    poi_b_id            UUID           NOT NULL REFERENCES poi(poi_id) ON DELETE CASCADE,
    transport_mode      VARCHAR(32)    NOT NULL
                                       CHECK (transport_mode IN ('walking', 'public_transit', 'taxi', 'car')),
    travel_time_minutes FLOAT          NOT NULL CHECK (travel_time_minutes >= 0),  -- Dij, unit: minutes
    last_updated        TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_poi_graph_edges UNIQUE (city, poi_a_id, poi_b_id, transport_mode)
);

-- Required index (source: schema-entities.md § poi_graph_edges)
-- UNIQUE constraint above implicitly creates the required index.


-- ---------------------------------------------------------------------------
-- TABLE: itinerary_days
-- Source: schema-entities.md § itinerary_days
-- Maps to: DayPlan + embedded RoutePoint[]
-- ---------------------------------------------------------------------------
CREATE TABLE itinerary_days (
    day_id             UUID           PRIMARY KEY DEFAULT uuid_generate_v4(),
    trip_id            UUID           NOT NULL REFERENCES trips(trip_id) ON DELETE CASCADE,
    day_number         SMALLINT       NOT NULL CHECK (day_number >= 1),
    date               DATE,
    daily_budget_used  NUMERIC(10,2)  NOT NULL DEFAULT 0.0,
    route_points       JSONB          NOT NULL DEFAULT '[]',
    -- Each element: {sequence, name, lat, lon, arrival_time, departure_time,
    --                visit_duration_minutes, activity_type, estimated_cost, notes}
    replan_version     SMALLINT       NOT NULL DEFAULT 0,  -- incremented on each PartialReplanner replan

    CONSTRAINT uq_itinerary_days_trip_day UNIQUE (trip_id, day_number)
);

CREATE INDEX idx_itinerary_days_trip_id ON itinerary_days(trip_id);


-- ---------------------------------------------------------------------------
-- TABLE: disruption_events
-- Source: schema-entities.md § disruption_events
-- Maps to: DisruptionMemory records (all 5 types + record_generic)
-- ---------------------------------------------------------------------------
CREATE TABLE disruption_events (
    event_id        UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    trip_id         UUID          NOT NULL REFERENCES trips(trip_id) ON DELETE CASCADE,
    day_number      SMALLINT      NOT NULL,
    event_type      VARCHAR(32)   NOT NULL
                                  CHECK (event_type IN (
                                      'weather', 'traffic', 'crowd', 'hunger', 'fatigue',
                                      'venue_closed', 'user_skip', 'user_replace',
                                      'user_reorder', 'manual_reopt', 'generic'
                                  )),
    trigger_time    VARCHAR(5),                                              -- HH:MM 24h trip-clock time
    severity        FLOAT         NOT NULL DEFAULT 0.0,                     -- 0.0 for user-triggered actions
    impacted_stops  TEXT[]        NOT NULL DEFAULT '{}',
    action_taken    VARCHAR(64),
    user_response   VARCHAR(16)
                                  CHECK (user_response IN (
                                      'APPROVE', 'REJECT', 'MODIFY', 'accepted', 'skipped'
                                  )),
    s_pti_affected  FLOAT,                                                   -- avg S_pti of impacted stops
    metadata        JSONB         NOT NULL DEFAULT '{}',                     -- type-specific fields
    recorded_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_disruption_events_trip_id    ON disruption_events(trip_id);
CREATE INDEX idx_disruption_events_event_type ON disruption_events(event_type);


-- =============================================================================
-- PART 2 — Redis Data Model
-- =============================================================================

/*
All Redis definitions are non-executable documentation.
Prefix format and TTL rules are specified below.
Apply via application code (hset / expire / set / setex).
*/

-- ---------------------------------------------------------------------------
-- 2.1  TripState Hash
-- Source: schema-entities.md § Redis Key Schema (TripState)
-- ---------------------------------------------------------------------------
--
-- Key:    tripstate:{trip_id}:{user_id}
-- Type:   Hash
-- TTL:    86400 seconds (24 hours from last write)
-- Config: AOF persistence enabled (appendonly yes)
--
-- Hash fields:
--
--   current_time                STRING      "HH:MM"
--   current_lat                 FLOAT       e.g. "28.6139"
--   current_lon                 FLOAT       e.g. "77.2090"
--   current_day                 INT         "1"  (1-indexed)
--   visited_stops               JSON array  '["City Museum","Riverfront Park"]'
--   skipped_stops               JSON array  '["Heritage Fort"]'
--   deferred_stops              JSON array  '[]'
--   hunger_level                FLOAT       "0.0" – "1.0"
--   fatigue_level               FLOAT       "0.0" – "1.0"
--   last_meal_time              STRING      "HH:MM"
--   last_rest_time              STRING      "HH:MM"
--   minutes_on_feet             INT         "120"
--   replan_pending              BOOLEAN     "0" | "1"
--   pending_decision            JSON blob   serialized PendingDecision or "null"
--   budget_spent                JSON object '{"Accommodation":0.0,"Attractions":45.0,...}'
--   disruption_memory_snapshot  JSON blob   output of DisruptionMemory.serialize()
--
-- Example HSET (pseudo-commands):
--
--   HSET tripstate:a1b2c3d4:u9e8f7a6
--       current_time        "09:30"
--       current_lat         "28.6139"
--       current_lon         "77.2090"
--       current_day         "1"
--       visited_stops       '[]'
--       skipped_stops       '[]'
--       deferred_stops      '[]'
--       hunger_level        "0.0"
--       fatigue_level       "0.0"
--       last_meal_time      "09:00"
--       last_rest_time      "09:00"
--       minutes_on_feet     "0"
--       replan_pending      "0"
--       pending_decision    "null"
--       budget_spent        '{"Accommodation":0.0,"Attractions":0.0,"Restaurants":0.0,"Transportation":0.0,"Other_Expenses":0.0,"Reserve_Fund":0.0}'
--       disruption_memory_snapshot "null"
--   EXPIRE tripstate:a1b2c3d4:u9e8f7a6 86400
--

-- ---------------------------------------------------------------------------
-- 2.2  Dij Edge Cache
-- Source: data-categories.md #9 / schema-entities.md § poi_graph_edges
-- ---------------------------------------------------------------------------
--
-- Key:    dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}
-- Type:   String (float value)
-- TTL:    MISSING: cache TTL duration not specified in source docs
--
-- Example:
--
--   SET dij:delhi:uuid-poi-a:uuid-poi-b:walking "18.5"
--   EXPIRE dij:delhi:uuid-poi-a:uuid-poi-b:walking <TTL>
--
-- Cache-aside pattern:
--   1. ACO inner loop: GET dij:{city}:{a}:{b}:{mode}
--   2. On miss: SELECT travel_time_minutes FROM poi_graph_edges WHERE ...
--   3. On hit from DB: SET + EXPIRE
--


-- =============================================================================
-- PART 3 — Storage Separation Rules
-- =============================================================================

/*
  Rule 1 — ACO PHEROMONE MATRIX (τ_ij)
  ──────────────────────────────────────
  STORED IN:   Python in-process memory only (dict or numpy 2D array inside
               aco_optimizer.py).
  DISCARDED:   Immediately after optimizer.run() returns.
  NEVER IN:    PostgreSQL, Redis, or any log store.
  REASON:      Source doc (02-polyglot-persistence.md §ACO Pheromone Matrix):
               "ACO pheromone state MUST NEVER leave the optimizer process."

  Rule 2 — SHORT-TERM MEMORY (ShortTermMemory)
  ─────────────────────────────────────────────
  STORED IN:   Python in-process memory for the duration of the session.
  PERSISTED:   Only get_feedback_summary() output is promoted to
               user_memory_profile at session end.
  NEVER IN:    Raw conversation turns are never written to any DB.
  REASON:      Source doc (04-data-exclusions.md §Promotion Rules):
               "ShortTermMemory raw conversation turns — Not promoted —
               too granular, no retrieval use case."

  Rule 3 — DISALLOWED DATA CATEGORIES
  ──────────────────────────────────────
  The following are NEVER written to any storage layer:

  | Item                                             | Source rule      |
  |--------------------------------------------------|------------------|
  | ACO pheromone matrix (τ_ij)                      | 04-exclusions #1 |
  | Intermediate ant tour snapshots                  | 04-exclusions #2 |
  | S_pti score map for unselected POIs              | 04-exclusions #3 |
  | Raw LLM API keys / tokens                        | 04-exclusions #4 |
  | LLM prompt text containing user PII              | 04-exclusions #5 |
  | Hunger/fatigue level time-series beyond session  | 04-exclusions #6 |
  | TripState.deferred_stops/skipped_stops post-trip | 04-exclusions #7 |
  | Full serialized ConstraintBundle per run         | 04-exclusions #8 |
  | Hotel/Restaurant/Flight raw API responses        | 04-exclusions #9 |
  | Session-to-session pheromone history             | 04-exclusions #10|
  | User authentication tokens / session cookies     | 04-exclusions #11|
  | LLM commonsense rules without user confirmation  | 04-exclusions #12|
*/


-- =============================================================================
-- PART 4 — Minimal Migration Plan
-- =============================================================================

/*
  Step 1 — Enable extensions (run once on target DB):

      CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
      CREATE EXTENSION IF NOT EXISTS "pg_trgm";

  Step 2 — Create tables in dependency order
  (parent tables before child tables with FK references):

      1.  users
      2.  user_memory_profile      (FK → users)
      3.  trips                    (FK → users)
      4.  poi
      5.  poi_graph_edges          (FK → poi × 2)
      6.  itinerary_days           (FK → trips)
      7.  disruption_events        (FK → trips)

  Step 3 — Create indexes in this order after all tables exist:

      -- trips
      CREATE INDEX idx_trips_user_id ON trips(user_id);
      CREATE INDEX idx_trips_status  ON trips(status);

      -- poi
      CREATE INDEX idx_poi_fts_historical ON poi
          USING GIN (to_tsvector('english', coalesce(historical_importance, '')));
      CREATE INDEX idx_poi_city_category  ON poi(city, category);
      CREATE INDEX idx_poi_city_latlon    ON poi(city, location_lat, location_lon);

      -- poi_graph_edges
      -- Covered by UNIQUE constraint (uq_poi_graph_edges) created inline.

      -- itinerary_days
      CREATE INDEX idx_itinerary_days_trip_id ON itinerary_days(trip_id);
      -- UNIQUE constraint (uq_itinerary_days_trip_day) created inline.

      -- disruption_events
      CREATE INDEX idx_disruption_events_trip_id    ON disruption_events(trip_id);
      CREATE INDEX idx_disruption_events_event_type ON disruption_events(event_type);

  Step 4 — Redis configuration (redis.conf):

      appendonly        yes           -- AOF persistence for TripState survival
      appendfsync       everysec      -- balance durability vs. performance
      -- TTL for tripstate keys: 86400 seconds (set per-key at write time)
      -- TTL for dij keys: MISSING — not specified in source docs

  Step 5 — Validate:

      SELECT table_name FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name;
      -- Expected: disruption_events, itinerary_days, poi, poi_graph_edges,
      --           trips, user_memory_profile, users

      SELECT indexname FROM pg_indexes
      WHERE schemaname = 'public'
      ORDER BY tablename, indexname;
*/

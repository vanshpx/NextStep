# TravelAgent — Integrated System Architecture

> Combines: **TravelAgent** · **ICDM** · **FTRM** · **ACO** · **Re-optimization Engine**
> Generated: 2026-02-21 | Updated: 2026-02-22

---

## 1. Module Diagram

```
TravelAgent System
│
├── [INPUT]  python main.py --chat  ←─ Chat mode
│   └── Input Module                    modules/input/chat_intake.py
│       └── ChatIntake.run()
│           │
│           ├── Phase 1 — Structured Form  (Hard Constraints — NO LLM)
│           │     Explicit input() prompts for precise fields:
│           │       departure_city, destination_city
│           │       departure_date, return_date
│           │       num_adults, num_children, group_size (derived)
│           │       traveler_ages (comma-separated, for age-restriction HC)
│           │       restaurant_preference, total_budget
│           │       requires_wheelchair (yes/no)
│           │     → Populates HardConstraints directly, no hallucination risk
│           │
│           └── Phase 2 — Free-form Chat  (Soft Constraints via NLP)
│                 User types freely: interests, dislikes, travel style,
│                   dietary preferences, pace, crowd/energy preferences
│                 Single LLM call at end → JSON extraction
│                 _apply_sc() maps JSON → SoftConstraints
│                                      → CommonsenseConstraints
│
│   python main.py  (default — hardcoded constraints, backward-compatible)
│
├── ICDM  (Item Constraints Data Model)
│   ├── HardConstraints          schemas/constraints.py
│   │     Core: departure_city, destination_city, departure_date, return_date,
│   │           num_adults, num_children, group_size, restaurant_preference
│   │     Accessibility: requires_wheelchair
│   │     Group & Age:   traveler_ages (list[int]), group_size (int)
│   │     Pre-booked:    fixed_appointments (list[dict])
│   │     Legal:         visa_restricted_countries (list[str])
│   ├── SoftConstraints          schemas/constraints.py
│   │     Existing: interests, travel_preferences, character_traits,
│   │               spending_power
│   │     Food:     dietary_preferences (vegan/vegetarian/halal/local_cuisine…)
│   │     Timing:   preferred_time_of_day (morning/afternoon/evening),
│   │               meal_lunch_window, meal_dinner_window
│   │     Comfort:  avoid_crowds, pace_preference (relaxed/moderate/packed),
│   │               rest_interval_minutes
│   │     Routing:  preferred_transport_mode
│   │     Energy:   heavy_travel_penalty
│   │     Variety:  avoid_consecutive_same_category, novelty_spread
│   ├── CommonsenseConstraints   schemas/constraints.py
│   └── ConstraintBundle         schemas/constraints.py
│
├── Tool-usage Module
│   ├── AttractionTool           → external API  (SERPAPI / MISSING)
│   │     AttractionRecord fields:
│   │       HC: opening_hours, visit_duration_minutes, min_visit_duration_minutes,
│   │           wheelchair_accessible, min_age, ticket_required,
│   │           min_group_size, max_group_size, seasonal_open_months
│   │       SC: optimal_visit_time, category, is_outdoor, intensity_level
│   ├── HotelTool                → external API  (MISSING)
│   ├── RestaurantTool           → external API  (MISSING)
│   │     RestaurantRecord fields:
│   │       HC: cuisine_type, cuisine_tags, opening_hours,
│   │           avg_price_per_person, wheelchair_accessible
│   │       SC: rating, cuisine_tags, accepts_reservations
│   ├── FlightTool               → external API  (MISSING)
│   ├── CityTool                 → external API  (MISSING)
│   ├── DistanceTool             → local haversine
│   └── TimeTool                 → local arithmetic
│
├── Recommendation Module
│   ├── BaseRecommender          (abstract)
│   │   ├── AttractionRecommender   HC → SC → Spti sort
│   │   ├── HotelRecommender        HC(4) → SC(amenity match, value-for-money,
│   │   │                               star rating) → Spti sort
│   │   ├── RestaurantRecommender   HC(4) → SC(rating, cuisine-tag match,
│   │   │                               reservation bonus) → Spti sort
│   │   ├── FlightRecommender       HC → SC → Spti sort
│   │   ├── BudgetRecommender       LLM → BudgetAllocation
│   │   └── CityRecommender         LLM → ranked cities
│   └── LLM client               (GeminiClient — google-genai SDK)
│
├── FTRM  (Flexible Travel Recommender Model)
│   ├── satisfaction.py
│   │   ├── compute_HC()         Eq 1: HCpti = Π hcm_pti
│   │   ├── compute_SC()         Eq 2: SCpti = agg(Wv, scv)
│   │   ├── compute_S()          Eq 4: Spti = HCpti × SCpti
│   │   └── evaluate_satisfaction()  full chain
│   ├── constraint_registry.py   HC evaluators per POI type
│   │     ATTRACTION: hc1 opening_hours · hc2 Tmax feasibility
│   │                 hc3 wheelchair · hc4 age · hc5 ticket
│   │                 hc6 group_size · hc7 seasonal · hc8 min_visit_duration
│   │     HOTEL:      hc1 price · hc2 availability · hc3 wheelchair · hc4 stars
│   │     RESTAURANT: hc1 dietary/cuisine · hc2 opening_hours
│   │                 hc3 per_meal_budget · hc4 wheelchair
│   │     FLIGHT:     hc1 price · hc2 travel_mode · hc3 departure_window
│   └── attraction_scoring.py    produces S_pti map for ACO
│         5 SC dimensions with weights [0.25, 0.20, 0.30, 0.15, 0.10]:
│           sc1(0.25) optimal_visit_time window
│           sc2(0.20) remaining-time efficiency  (S_left,i)
│           sc3(0.30) category × user interests  (highest weight)
│           sc4(0.15) preferred_time_of_day alignment
│           sc5(0.10) crowd avoidance + energy management
│
├── ACO  (Ant Colony Optimization)
│   └── aco_optimizer.py
│       ├── ACOParams            α, β, ρ, Q, τ_init, ants, iters
│       ├── AntState             visited, t_cur, elapsed, cost, tour
│       ├── _compute_eta()       ηij = Spti / Dij
│       ├── _select_next()       Pij = (τij^α × ηij^β) / Σ
│       ├── _local_pheromone_update()   Eq 15
│       └── _global_pheromone_update()  Eq 16  (best-ant)
│
├── Planning Module
│   ├── BudgetPlanner            wraps BudgetRecommender
│   └── RoutePlanner             calls ACO per day
│         passes constraints → AttractionScorer for full HC+SC evaluation
│         tracks: trip_month, group_size, traveler_ages,
│                 is_arrival_or_departure_day (energy management)
│
├── Memory Module
│   ├── ShortTermMemory          interaction log, session insights
│   ├── LongTermMemory           Wv weight learning (λ update)
│   └── DisruptionMemory         modules/memory/disruption_memory.py
│         record_weather() / record_traffic() / record_replacement()
│         weather_tolerance_level() · delay_tolerance_minutes()
│         common_replacements() · serialize() / deserialize()
│
└── Re-optimization Module      modules/reoptimization/
    ├── TripState                trip_state.py
    │     visited_stops / skipped_stops / deferred_stops (set[str])
    │     mark_visited() · mark_skipped() · defer_stop() · undefer_stop()
    │     remaining_minutes_today() · remaining_budget()
    ├── EventHandler             event_handler.py
    │     EventType enum (all event types — see Section 9)
    │     Returns ReplanDecision{should_replan, urgency, reason, metadata}
    ├── ConditionMonitor         condition_monitor.py
    │     _derive_thresholds() from SoftConstraints (never hard-code)
    │     check() → list[ReplanDecision]
    ├── PartialReplanner         partial_replanner.py
    │     replan() → filters visited ∪ skipped ∪ deferred → RoutePlanner
    ├── CrowdAdvisory            crowd_advisory.py
    │     build() → CrowdAdvisoryResult (3 strategies + panel data)
    ├── WeatherAdvisor           weather_advisor.py
    │     classify() → WeatherAdvisoryResult
    │       BLOCKED  (severity ≥ 0.75): HC_pti = 0
    │       DEFERRED (threshold ≤ s < 0.75): duration ×0.75
    │       SAFE     (indoor): ranked by η_ij = S_pti / Dij
    ├── TrafficAdvisor           traffic_advisor.py
    │     assess() → TrafficAdvisoryResult
    │       Dij_new = Dij_base × (1 + traffic_level)
    │       η_ij_new = S_pti / Dij_new
    │       DEFER   (S_pti ≥ 0.65): high value — keep for later
    │       REPLACE (S_pti < 0.65): low value — geo-clustered alternative
    ├── UserEditHandler          user_edit_handler.py
    │     dislike_next_poi()  → DislikeResult   (advisory only, no mutation)
    │     replace_poi()       → ReplaceResult   (validate + swap + recompute times)
    │     skip_current_poi()  → SkipResult      (memory signal + replan trigger)
    │     HIGH_SPTI_MEMORY_THRESHOLD = 0.70
    └── ReOptimizationSession    session.py
          Orchestrates: TripState · EventHandler · ConditionMonitor
                        PartialReplanner · CrowdAdvisory · WeatherAdvisor
                        TrafficAdvisor · UserEditHandler · DisruptionMemory
          event() — routes by metadata key:
            crowd_action      → _handle_crowd_action()
            weather_action    → _handle_weather_action()
            traffic_action    → _handle_traffic_action()
            user_edit_action  → _handle_user_edit_action()
          check_conditions()  — feeds ConditionMonitor; auto-routes above
          advance_to_stop()   — moves clock + position + marks visited
          summary()           — snapshot including disruption_memory```

---

## 2. Data Flow Sequence

```
Stage 0 — Chat Intake  (--chat mode only)
    python main.py --chat

    [· Phase 1 — Structured Form (Hard Constraints) ·]
      Prompts user for exact values via input():
        departure_city, destination_city, departure_date, return_date
        num_adults, num_children
        traveler_ages  (comma-separated — feeds min_age HC check)
        group_size     (derived: num_adults + num_children)
        restaurant_preference
        requires_wheelchair  (yes/no)
        total_budget
      NO LLM — values captured directly into HardConstraints

    [· Phase 2 — Free-form Chat (Soft Constraints via NLP) ·]
      User types freely about preferences, dislikes, travel style
      LLM extracts full JSON covering:
        interests, travel_preferences, spending_power, character_traits
        dietary_preferences, preferred_time_of_day, avoid_crowds
        pace_preference, preferred_transport_mode
        rest_interval_minutes, heavy_travel_penalty
        avoid_consecutive_same_category, novelty_spread
        commonsense.rules
      _apply_sc() maps JSON → SoftConstraints + CommonsenseConstraints

    → Returns ConstraintBundle + total_budget → passed to Stage 1

Stage 1 — Constraint Modeling
    --chat mode : ConstraintBundle already populated from Stage 0
    default mode: build HardConstraints/SoftConstraints/CommonsenseConstraints
                  from hardcoded values + LongTermMemory history
    → ConstraintBundle assembled

Stage 2 — Budget Planning
    ConstraintBundle
    → BudgetRecommender._call_llm(prompt)
    → LLM returns budget JSON
    → BudgetPlanner validates + fills BudgetAllocation

Stage 3 — Information Gathering + Recommendation
    ConstraintBundle + BudgetAllocation
    → Tool-usage Module: fetch raw POI records (Attraction/Hotel/Restaurant/Flight)
    → Per record:
        constraint_registry.evaluate_hc()  →  hcm_pti list
          ATTRACTION (8 checks): opening_hours, Tmax, wheelchair, age,
            ticket, group_size, seasonal_closure, min_visit_duration
          HOTEL      (4 checks): price/night, availability, wheelchair, stars
          RESTAURANT (4 checks): dietary/cuisine match, opening_hours,
            per_meal_budget, wheelchair
          FLIGHT     (3 checks): price, travel_mode, departure_window
        compute_HC()                        →  HCpti ∈ {0,1}
        compute_SC(sc_values, Wv, method)   →  SCpti ∈ [0,1]
        compute_S()                         →  Spti = HCpti × SCpti
    → Sort descending by Spti
    → ShortTermMemory.log_interaction(feedback)
    → LLM: generate explanations (optional)

Stage 4 — Route Planning (per day)
    ranked AttractionRecords + ConstraintBundle
    → AttractionScorer(constraints, trip_month, group_size, traveler_ages)
        Per attraction — full HC+SC pipeline:
          HC(8): opening_hours · Tmax · wheelchair · age · ticket
                 group_size · seasonal · min_visit_duration
          SC(5): sc1 optimal_window · sc2 remaining_time · sc3 interest_match
                 sc4 time_of_day_pref · sc5 crowd_energy
                 (is_arrival_or_departure_day → heavy_travel_penalty applied)
        → {node_id: Spti} = S_pti map
    → RoutePlanner calls ACOOptimizer.optimize(S_pti, graph)
        For each ant, each step:
            _get_feasible_nodes()             → infeasibility filter
            _compute_eta()                    → ηij = Spti / Dij
            _select_next()                    → Pij roulette-wheel
            _local_pheromone_update()         → τij update (Eq 15)
        End iteration:
            _global_pheromone_update()        → best-ant τij (Eq 16)
    → best_tour → DayPlan → Itinerary

Stage 5 — Output + Continuous Learning
    Itinerary
    → JSON output
    → ShortTermMemory.record_feedback()
    → LongTermMemory.update_soft_weights(Wv, λ)

Stage 6 — Mid-Trip Re-optimization  (runtime, optional)
    ReOptimizationSession.from_itinerary(itinerary, constraints)

    [· Environmental Triggers (auto via ConditionMonitor) ·]
      check_conditions(crowd_level, traffic_level, weather_condition, ...)
        ConditionMonitor._derive_thresholds()  ← from SoftConstraints
          crowd threshold    = f(avoid_crowds, pace_preference)
          traffic threshold  = f(preferred_transport_mode)
          weather threshold  = f(character_traits, pace_preference)
        If crowd_level > crowd_threshold:
          → ENV_CROWD_HIGH → _handle_crowd_action() — 3 strategies:
            1. reschedule_same_day  : defer + replan + undefer
            2. reschedule_future_day: move to current_day + 1
            3. inform_user          : HC cannot save it; advisory + user veto
        If traffic_level > traffic_threshold:
          → ENV_TRAFFIC_HIGH → _handle_traffic_action()
            TrafficAdvisor.assess():
              Dij_new = Dij_base × (1 + traffic_level)    [Eq 12 variant]
              η_ij_new = S_pti / Dij_new
              S_pti ≥ 0.65 → DEFER (high value — keep for later)
              S_pti <  0.65 → REPLACE (geo-clustered nearby alternative)
        If weather severity > weather_threshold:
          → ENV_WEATHER_BAD → _handle_weather_action()
            WeatherAdvisor.classify():
              severity ≥ HC_UNSAFE_THRESHOLD (0.75) → BLOCKED (HC_pti = 0)
              threshold ≤ severity < 0.75            → DEFERRED (STi ×0.75)
              indoor pool ranked by η_ij = S_pti / Dij

    [· User-reported Events (direct API) ·]
      session.event(EventType.USER_SKIP,   {"stop_name": str})
        → show WHAT YOU WILL MISS + BEST ALTERNATIVES advisory
        → mark_skipped() + replan
      session.event(EventType.USER_DELAY,  {"delay_minutes": int})
        → advance clock; replan if delay ≥ 20 min
      session.event(EventType.USER_PREFERENCE_CHANGE, {"field": str, "value": Any})
        → apply to SoftConstraints; rebuild ConditionMonitor; replan
      session.event(EventType.USER_ADD_STOP, {"attraction": AttractionRecord})
        → inject into remaining pool; replan
      session.event(EventType.VENUE_CLOSED, {"stop_name": str})
        → mark_skipped() + immediate high-urgency replan

    [· User-Edit Events (direct API — new) ·]
      session.event(EventType.USER_DISLIKE_NEXT, {...position...})
        → UserEditHandler.dislike_next_poi()
            peek next unvisited RoutePoint
            score remaining pool (full HC+SC) excluding visited ∪ skipped
            ∪ deferred ∪ {disliked_stop}
            filter: HC_pti > 0 AND STi ≤ remaining_minutes
            rank: S_pti DESC, Dij ASC (tiebreak)
            → print DISLIKE ADVISORY panel (no state mutation)
      session.event(EventType.USER_REPLACE_POI, {"replacement_record": AttractionRecord})
        → UserEditHandler.replace_poi()
            validate in order (fail-fast):
              1. not already visited/skipped
              2. HC_pti > 0
              3. Dij + STi ≤ remaining_minutes
              4. entry_cost ≤ budget_remaining
              5. no duplicate in future plan
              6. total plan time ≤ Tmax (DAY_END_TIME = 20:00)
            on accept: swap RoutePoint + walk downstream to recompute
              arrival_time = prev.departure + Dij
              departure_time = arrival + STi
            → record to DisruptionMemory; commit plan; trigger replan
      session.event(EventType.USER_SKIP_CURRENT, {"stop_name": str})
        → UserEditHandler.skip_current_poi()
            mark_skipped() (permanent — distinct from USER_SKIP which
              targets the NEXT stop; SKIP_CURRENT aborts an ongoing visit)
            replan from same lat/lon (no travel cost consumed)
            if S_pti ≥ HIGH_SPTI_MEMORY_THRESHOLD (0.70):
              → write preference signal to DisruptionMemory

    [· Replan execution ·]
      PartialReplanner.replan():
        candidate pool = remaining_attractions
                         − visited_stops − skipped_stops − deferred_stops
        → RoutePlanner._plan_single_day() (full FTRM+ACO pipeline)
        → update state.current_day_plan
        → append to session.replan_history

    [· Memory persistence ·]
      DisruptionMemory updated after every weather / traffic / replace event
      summary()  surfaced in session.summary()["disruption_memory"]
      serialize() / deserialize()  enable multi-day persistence
```

---

## 3. LLM Usage Locations

| Location | Module | Purpose |
|---|---|---|
| `ChatIntake` | Input | Constraint extraction from conversation |
| `BudgetRecommender` | Recommendation | Budget allocation JSON |
| `AttractionRecommender` | Recommendation | Explanation text |
| `HotelRecommender` | Recommendation | Explanation text |
| `RestaurantRecommender` | Recommendation | Explanation text |
| `FlightRecommender` | Recommendation | Explanation text |
| `CityRecommender` | Recommendation | City selection rationale |

> **Note:** LLM is NOT used for HC/SC scoring or ACO — purely generative/explanatory.

---

## 4. Optimization Usage Locations

| Location | Module | Purpose |
|---|---|---|
| `satisfaction.py` | FTRM | HC × SC → Spti (all POI types) |
| `constraint_registry.py` | FTRM | HC binary gate per POI type |
| `attraction_scoring.py` | Planning | S_pti map → ACO input (5 SC dims) |
| `aco_optimizer.py` | ACO | Tour construction per day |
| `long_term_memory.py` | Memory | Wv weight update (λ learning) |
| `SC_AGGREGATION_METHOD` | config.py | Selects: sum / least_misery / most_pleasure / multiplicative |

---

## 5. APIs / Tools Usage Locations

| Tool | API Provider | Stage | Module |
|---|---|---|---|
| `ChatIntake` | GeminiClient | Stage 0 | Input Module |
| `AttractionTool` | SERPAPI *(MISSING)* | Stage 3 | Tool-usage |
| `HotelTool` | *(MISSING)* | Stage 3 | Tool-usage |
| `RestaurantTool` | *(MISSING)* | Stage 3 | Tool-usage |
| `FlightTool` | *(MISSING)* | Stage 3 | Tool-usage |
| `CityTool` | *(MISSING)* | Stage 3 | Tool-usage |
| `DistanceTool` | Local haversine | Stage 4 | Tool-usage / ACO |
| `TimeTool` | Local arithmetic | Stage 4 | Tool-usage / ACO |
| `GeminiClient` | Google AI Studio (`google-genai` SDK) | Stage 0–3 | main.py |
| Google Maps API | *(MISSING)* | Stage 4 | DistanceTool (road distance not wired) |

---

## 6. Hard Constraint Registry

### ATTRACTION  (`constraint_registry._hc_attraction`)
| # | Name | Field on AttractionRecord | Context key | Violation |
|---|---|---|---|---|
| hc1 | Opening hours | `opening_hours` | `t_cur` | Place closed at visit time |
| hc2 | Tmax feasibility | `visit_duration_minutes` | `elapsed_min`, `Tmax_min`, `Dij_minutes` | Not enough day left |
| hc3 | Wheelchair access | `wheelchair_accessible` | `requires_wheelchair` | Inaccessible venue |
| hc4 | Age restriction | `min_age` | `traveler_ages` (youngest) | Youngest traveler under minimum |
| hc5 | Ticket / permit | `ticket_required` | `permit_available` | Permit not available |
| hc6 | Group size | `min_group_size`, `max_group_size` | `group_size` | Group too large or too small for venue |
| hc7 | Seasonal closure | `seasonal_open_months` | `trip_month` | Attraction closed in trip month |
| hc8 | Min visit duration | `min_visit_duration_minutes` | `elapsed_min`, `Tmax_min`, `Dij_minutes` | Too little time for a meaningful visit |

### HOTEL  (`constraint_registry._hc_hotel`)
| # | Name | Field on HotelRecord | Context key |
|---|---|---|---|
| hc1 | Nightly price | `price_per_night` | `nightly_budget` |
| hc2 | Availability | `available` | — |
| hc3 | Wheelchair access | `wheelchair_accessible` | `requires_wheelchair` |
| hc4 | Star rating | `star_rating` | `min_star_rating` |

### RESTAURANT  (`constraint_registry._hc_restaurant`)
| # | Name | Field on RestaurantRecord | Context key |
|---|---|---|---|
| hc1 | Dietary / cuisine match | `cuisine_type`, `cuisine_tags` | `dietary_preferences` (set[str]) |
| hc2 | Opening hours | `opening_hours` | `t_cur` |
| hc3 | Per-meal budget | `avg_price_per_person` | `per_meal_budget` |
| hc4 | Wheelchair access | `wheelchair_accessible` | `requires_wheelchair` |

### FLIGHT  (`constraint_registry._hc_flight`)
| # | Name | Field on FlightRecord | Context key |
|---|---|---|---|
| hc1 | Price | `price` | `flight_budget` |
| hc2 | Travel mode | `stops_type` | `allowed_modes` |
| hc3 | Departure window | `departure_time` | `earliest_dep`, `latest_dep` |

---

## 7. Soft Constraint Dimensions

### Attraction SC  (`attraction_scoring.AttractionScorer`)

Default SC aggregation method: **sum** (config `SC_AGGREGATION_METHOD`).

| sc | Weight | Name | Source field | Description |
|---|---|---|---|---|
| sc1 | 0.25 | Optimal visit window | `AttractionRecord.optimal_visit_time` | 1.0 inside window · 0.5 no data · 0.0 outside |
| sc2 | 0.20 | Remaining-time efficiency | derived from `Tmax`, `elapsed`, `Dij` | (Tmax − elapsed − Dij − STi) / Tmax |
| sc3 | 0.30 | Category–interest match | `AttractionRecord.category` × `SoftConstraints.interests` | 1.0 match · 0.5 no pref · 0.2 mismatch |
| sc4 | 0.15 | Time-of-day preference | `SoftConstraints.preferred_time_of_day` | 1.0 aligned · 0.2 opposite · outdoor morning bonus |
| sc5 | 0.10 | Crowd avoidance + energy | `is_outdoor`, `intensity_level`, `avoid_crowds`, `pace_preference`, `heavy_travel_penalty` | Composite: outdoor midday penalty · high-intensity penalty on boundary days |

**sc5 logic summary:**
- `avoid_crowds=True` + outdoor + 10:00–15:00 → 0.3
- `heavy_travel_penalty=True` + `intensity_level="high"` + arrival/departure day → 0.1
- `pace_preference="relaxed"` + `intensity_level="high"` → capped at 0.4

### Hotel SC  (`hotel_recommender.HotelRecommender`)
| sc | Weight | Description |
|---|---|---|
| sc1 | 0.40 | Normalised star rating (`star_rating / 5.0`) |
| sc2 | 0.35 | Amenity match fraction (requested amenities present / total requested) |
| sc3 | 0.25 | Value-for-money (`1 − price_after_discount / nightly_budget`, capped 0–1) |

### Restaurant SC  (`restaurant_recommender.RestaurantRecommender`)
| sc | Weight | Description |
|---|---|---|
| sc1 | 0.50 | Normalised rating (`rating / 5.0`) |
| sc2 | 0.35 | Cuisine-tag preference match (tags ∩ `dietary_preferences` / total user prefs) |
| sc3 | 0.15 | Reservation bonus (`+0.2` if `accepts_reservations=True`) |

---

## 8. SoftConstraints Field Reference

| Field | Type | Default | Captured in |
|---|---|---|---|
| `interests` | `list[str]` | `[]` | Phase 2 chat |
| `travel_preferences` | `list[str]` | `[]` | Phase 2 chat |
| `character_traits` | `list[str]` | `[]` | Phase 2 chat |
| `spending_power` | `str` | `""` | Phase 2 chat |
| `dietary_preferences` | `list[str]` | `[]` | Phase 2 chat |
| `preferred_time_of_day` | `str` | `""` | Phase 2 chat |
| `avoid_crowds` | `bool` | `False` | Phase 2 chat |
| `pace_preference` | `str` | `"moderate"` | Phase 2 chat |
| `preferred_transport_mode` | `list[str]` | `[]` | Phase 2 chat |
| `meal_lunch_window` | `tuple` | `("12:00","14:00")` | Default (configurable) |
| `meal_dinner_window` | `tuple` | `("19:00","21:00")` | Default (configurable) |
| `rest_interval_minutes` | `int` | `120` | Phase 2 chat |
| `heavy_travel_penalty` | `bool` | `True` | Phase 2 chat |
| `avoid_consecutive_same_category` | `bool` | `True` | Phase 2 chat |
| `novelty_spread` | `bool` | `True` | Phase 2 chat |

---

## 9. Re-optimization System

### 9.1 EventType Taxonomy

```
modules/reoptimization/event_handler.py — EventType
```

| EventType | Value | Description | should_replan | Handler |
|---|---|---|---|---|
| `USER_SKIP` | `user_skip` | Skip the next planned stop | ✓ | `_handle_skip` — mark_skipped + replan; pre-show advisory |
| `USER_DELAY` | `user_delay` | Running behind schedule | cond. | `_handle_delay` — advance clock; replan if delay ≥ 20 min |
| `USER_PREFERENCE_CHANGE` | `user_pref` | Update soft constraints mid-trip | ✓ | `_handle_preference_change` — rebuild monitor + replan |
| `USER_ADD_STOP` | `user_add` | Insert stop into remaining pool | ✓ | `_handle_add_stop` — inject + replan |
| `USER_REPORT_DISRUPTION` | `user_report` | Free-text disruption report | ✓ | `_handle_user_report` — heuristic urgency + replan |
| `USER_DISLIKE_NEXT` | `user_dislike_next` | Dislike next stop; request alternatives | ✗ | `_handle_dislike_next` → session `_handle_user_edit_action` |
| `USER_REPLACE_POI` | `user_replace_poi` | Replace next stop with chosen alternative | ✓ | `_handle_replace_poi` → session `_handle_user_edit_action` |
| `USER_SKIP_CURRENT` | `user_skip_current` | Abort currently active stop mid-visit | ✓ | `_handle_skip_current` → session `_handle_user_edit_action` |
| `ENV_CROWD_HIGH` | `env_crowd` | Crowd level > tolerance threshold | cond. | `_handle_env_crowd` — 3-strategy tree |
| `ENV_TRAFFIC_HIGH` | `env_traffic` | Traffic level > tolerance threshold | cond. | `_handle_env_traffic` — TrafficAdvisor |
| `ENV_WEATHER_BAD` | `env_weather` | Weather severity > tolerance threshold | cond. | `_handle_env_weather` — WeatherAdvisor |
| `VENUE_CLOSED` | `venue_closed` | Planned stop unexpectedly closed | ✓ | `_handle_venue_closed` — mark_skipped + immediate replan |

### 9.2 Crowd Disruption — Three-Strategy Tree

```
_handle_env_crowd (event_handler.py) → session._handle_crowd_action()

Inputs: stop_name, crowd_level, threshold, total_days,
        remaining_minutes, min_visit_duration, place_importance

time_for_later = remaining_minutes − min_visit_duration − 60  [60-min buffer]

Strategy 1 — reschedule_same_day
    CONDITION: time_for_later ≥ min_visit_duration
    ACTION   : defer_stop(stop) → replan (stop excluded) → undefer_stop(stop)
    ADVISORY : BEST ALTERNATIVES | SYSTEM DECISION

Strategy 2 — reschedule_future_day
    CONDITION: current_day < total_days
    ACTION   : defer_stop(stop) → future_deferred[stop] = current_day + 1
    ADVISORY : BEST ALTERNATIVES | SYSTEM DECISION

Strategy 3 — inform_user  (last day or no capacity)
    CONDITION: fallthrough
    ACTION   : no auto-replan; crowd_pending_decision set; user decides
    ADVISORY : WHAT YOU WILL MISS | BEST ALTERNATIVES | SYSTEM DECISION | YOUR CHOICE
    USER CAN : visit despite crowds (do nothing) OR
               session.event(EventType.USER_SKIP, {"stop_name": stop_name})
```

### 9.3 Weather Disruption

```
WeatherAdvisor.classify() → WeatherAdvisoryResult

Constants:
    HC_UNSAFE_THRESHOLD   = 0.75  (hard — blocks outdoor stops)
    DURATION_SCALE_FACTOR = 0.75  (risky — visit duration ×0.75)
    AVG_TRAVEL_SPEED_KMH  = 4.0   (walking speed for Dij re-estimate)

Threshold derivation:
    weather_threshold ← ConditionMonitor._derive_thresholds() from SoftConstraints
    NEVER hard-code — always derived

Classification tree (per remaining outdoor POI):
    severity ≥ 0.75           → BLOCKED  (state.defer_stop()  |  HC_pti = 0)
    threshold ≤ s < 0.75      → DEFERRED (visit_duration ×= 0.75)
    any severity — indoor pool → SAFE     (ranked by η_ij = S_pti / Dij)

Advisory panel:
    BLOCKED OUTDOOR STOPS       — always shown when present
    DEFERRED RISKY STOPS        — with adjusted duration
    INDOOR ALTERNATIVES (η_ij)  — always shown
    SYSTEM DECISION

Post-classify:
    all BLOCKED stops → state.defer_stop()
    DisruptionMemory.record_weather()
    _do_replan(deprioritize_outdoor=True)
```

### 9.4 Traffic Disruption

```
TrafficAdvisor.assess() → TrafficAdvisoryResult

Constants:
    HIGH_PRIORITY_THRESHOLD = 0.65  (S_pti threshold: defer vs replace)
    CLUSTER_RADIUS_MIN      = 30    (minutes — geo-cluster radius)

Equations:
    Dij_new  = Dij_base × (1 + traffic_level)     [Eq 12 variant]
    η_ij_new = S_pti / Dij_new                     [Eq 12 updated]
    delay_factor = 1 + traffic_level

Decision per stop:
    Dij_new + STi ≤ remaining_minutes:
        S_pti ≥ 0.65  →  DEFER   (high value — keep for later)
        S_pti < 0.65  →  REPLACE (low value — geo-clustered nearby alternative)
    else (infeasible): skip from today's plan

Advisory panel:
    DEFERRED stops (S_pti ≥ 0.65)
    REPLACED stops (S_pti < 0.65)
    NEARBY ALTERNATIVES (η_ij_new, clustered flag)
    START-TIME ADJUSTMENT (if clock advanced)
    SYSTEM DECISION

Post-assess:
    deferred stops → state.defer_stop()
    DisruptionMemory.record_traffic() + record_replacement() per replaced stop
    _do_replan()
```

### 9.5 User-Edit Actions

```
UserEditHandler  (modules/reoptimization/user_edit_handler.py)

Constants (defined in user_edit_handler.py):
    HIGH_SPTI_MEMORY_THRESHOLD = 0.70  [memory signal threshold]
    DEFAULT_TOP_N_ALTERNATIVES = 5
    TRAVEL_SPEED_KMH           = 5.0
    DAY_END_TIME               = "20:00"  [Tmax for time recomputation]

── A: dislike_next_poi() → DislikeResult ────────────────────────────────────────
    Entry event : USER_DISLIKE_NEXT
    State change: NONE  (advisory only)
    Algorithm:
      next_stop ← first RoutePoint not in visited ∪ skipped
      pool      ← remaining_pool − visited − skipped − deferred − {next_stop}
      score all candidates: full AttractionScorer (HC+SC, 5 SC dims)
      filter:  HC_pti > 0  AND  STi ≤ remaining_minutes
      rank:    S_pti DESC, Dij ASC (tiebreak)
      return:  DislikeResult(disliked_stop, current_S_pti, alternatives[:top_n])
    Advisory panel:
      BEST ALTERNATIVES (ranked by S_pti)
      TO REPLACE → instruct caller to fire USER_REPLACE_POI

── B: replace_poi() → ReplaceResult ─────────────────────────────────────────────
    Entry event : USER_REPLACE_POI  {"replacement_record": AttractionRecord}
    Validation  (fail-fast, in order):
      1. replacement not in visited ∪ skipped
      2. HC_pti(replacement) > 0
      3. Dij + STi ≤ remaining_minutes
      4. entry_cost ≤ budget_remaining
      5. replacement name not in future route_points
      6. total plan time after recompute ≤ DAY_END_TIME
    On accept:
      swap RoutePoint fields (name, lat/lon, duration, cost)
      recompute downstream times (walk route_points from swap index):
        arrival_i   = prev.departure + Dij(prev → i)
        departure_i = arrival_i + STi
      commit to state.current_day_plan
      budget_spent["Attractions"] += budget_delta
      DisruptionMemory.record_replacement(reason="user_replace")
      _do_replan() from new position
    Advisory panel:
      ✓ ACCEPTED — budget delta + updated stop list
      ✗ REJECTED — precise rejection reason

── C: skip_current_poi() → SkipResult ───────────────────────────────────────────
    Entry event : USER_SKIP_CURRENT  {"stop_name": str}
    Distinction :
      USER_SKIP         → skips the NEXT stop (before arrival)
      USER_SKIP_CURRENT → aborts CURRENT stop mid-visit (already there)
                          replans from SAME lat/lon (traveler stays in place)
    State change: mark_skipped(stop_name)  [permanent — not deferred]
    Algorithm:
      compute S_pti(skipped stop) via AttractionScorer
      if S_pti ≥ HIGH_SPTI_MEMORY_THRESHOLD:
        DisruptionMemory.record_replacement(
            original=stop_name, replacement="",
            reason="user_skip_current_high_spti")
      trigger _do_replan() from current lat/lon (no position change)
```

### 9.6 Advisory Panel Display Rules

The table below shows **which sections appear in each handler's own output**.  
The `✗ MISSED EXPERIENCE` panel (Section 9.8) fires **in addition** to these — see the trigger table.

| Panel section | Crowd S1&S2 | Crowd S3 (inform) | Weather | Traffic | Dislike | Replace |
|---|---|---|---|---|---|---|
| **WHAT YOU WILL MISS** | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| **BEST ALTERNATIVES** | ✓ | ✓ | ✓ indoor η | ✓ nearby η | ✓ S_pti | — |
| **SYSTEM DECISION** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **YOUR CHOICE** | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| **BLOCKED STOPS** | — | — | ✓ | ✗ | ✗ | ✗ |
| **DEFERRED STOPS** | — | — | ✓ | ✓ | ✗ | ✗ |
| **ACCEPT / REJECT** | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

**`✗ MISSED EXPERIENCE` panel trigger matrix:**

| Trigger | Fires? | Reason constant | S_pti_i passed |
|---|---|---|---|
| `VENUE_CLOSED` event | ✓ | `REASON_CLOSURE` | `0.0` |
| `USER_SKIP` event | ✓ | `REASON_CLOSURE` | `0.0` |
| Crowd S3 `inform_user` (auto) | ✓ | `REASON_CLOSURE` | `0.0` |
| Crowd S1 `reschedule_same_day` | ✗ | — | — |
| Crowd S2 `reschedule_future_day` | ✗ | — | — |
| Weather — each BLOCKED stop | ✓ | `REASON_WEATHER` | `0.0` |
| Weather — DEFERRED stops | ✗ | — | — |
| Traffic — each REPLACED stop | ✓ | `REASON_TRAFFIC` | `fi.S_pti` |
| Traffic — DEFERRED stops | ✗ | — | — |
| `USER_DISLIKE_NEXT` | ✗ | — | — |
| `USER_REPLACE_POI` | ✗ | — | — |
| `USER_SKIP_CURRENT` | ✗ | — | — |

**`✗ MISSED EXPERIENCE` panel always contains:**

| Section | Condition |
|---|---|
| POI name · reason · MissedUtility · infeasibility class | always |
| WHAT YOU WILL MISS (experience type · category impact · rarity · historical snippet · time window) | always |
| SATISFACTION PROTECTION notice | only if `defer_preferred = True` (MissedUtility ≥ 0.65) |
| BEST ALTERNATIVES (TradeoffScore = S_pti_j + 0.20 × category_match) | always; quality-floor warning if none qualify |

### 9.7 DisruptionMemory

```
modules/memory/disruption_memory.py

Record types:
    WeatherRecord     — condition, severity, threshold, blocked, deferred, alternatives
    TrafficRecord     — traffic_level, threshold, delay_minutes, delay_factor,
                        deferred[], replaced[]
    ReplacementRecord — original, replacement, reason, S_orig, S_rep, timestamp

Learning signals:
    weather_tolerance_level()  → rolling avg of severities the traveller accepted
    delay_tolerance_minutes()  → rolling avg of traffic delays tolerated
    common_replacements()      → most frequent replacement patterns

Persistence:
    serialize()   → dict  (JSON-safe)
    deserialize() → DisruptionMemory  (used at session start for multi-day trips)

Integration:
    Written after: every weather event · every traffic event ·
                   every accepted replace · every high-S_pti skip
    Read in:       session.summary()["disruption_memory"]
```

### 9.8 TripState Stop-Set Semantics

| Set | Mutation | Semantics | Can re-enter pool? |
|---|---|---|---|
| `visited_stops` | `mark_visited()` | Successfully completed stop | No |
| `skipped_stops` | `mark_skipped()` | Permanently removed — user skip, venue closed, USER_SKIP_CURRENT | No |
| `deferred_stops` | `defer_stop()` / `undefer_stop()` | Temporary exclusion — crowded, weather-blocked, traffic-delayed | Yes — `undefer_stop()` re-admits |

> `PartialReplanner.replan()` always filters `visited ∪ skipped ∪ deferred` before
> delegating to `RoutePlanner._plan_single_day()`.

---

### 9.9 MissedExperienceAdvisor

Surfaces a **"WHAT YOU WILL MISS"** panel whenever the traveller permanently loses
access to a high-importance stop (crowd `inform_user` strategy or a `USER_SKIP`).

**Data flow:**
```
stop_name
  → HistoricalInsightTool.get_insight(stop_name, city)
      → AttractionRecord.historical_importance  (priority 1 — rich text)
      → LLM stub / real Gemini                  (priority 2)
      → "No additional information."            (fallback)
  → CrowdAdvisory.build(strategy="inform_user") → CrowdAdvisoryResult.missed_experience_text
  → session._print_crowd_advisory() → panel header "WHAT YOU WILL MISS"
```

**Advisory panel display rules:**

| Panel section | inform_user | reschedule_same_day | reschedule_future_day |
|---|---|---|---|
| WHAT YOU WILL MISS | ✓ | ✗ | ✗ |
| BEST ALTERNATIVES | ✓ | ✓ | ✓ |
| YOUR CHOICE | ✓ | ✗ | ✗ |

---

### 9.10 HungerFatigueAdvisor

**File:** `modules/reoptimization/hunger_fatigue_advisor.py`

#### User-state variables (stored in TripState)

| Field | Type | Default | Semantics |
|---|---|---|---|
| `hunger_level` | float | 0.0 | 0 = satiated, 1 = urgent |
| `fatigue_level` | float | 0.0 | 0 = fresh, 1 = exhausted |
| `last_meal_time` | str | "09:00" | reset on `on_meal_completed()` |
| `last_rest_time` | str | "09:00" | reset on `on_rest_completed()` |
| `minutes_on_feet` | int | 0 | cumulative active minutes since last rest |

#### Accumulation mechanisms

**Mechanism 1 — Deterministic (after every `advance_to_stop`):**
```
hunger_level  ← min(1, hunger  + ΔT × HUNGER_RATE)        HUNGER_RATE = 1/180 /min
fatigue_level ← min(1, fatigue + ΔT × FATIGUE_RATE × k)   FATIGUE_RATE = 1/420 /min
  k = 1.8 (high) | 1.3 (medium) | 1.0 (low)
```

**Mechanism 2 — NLP trigger (inside `session.event()` for `USER_REPORT_DISRUPTION`):**
```
hunger keywords  → hunger_level  = max(hunger_level,  0.72)
fatigue keywords → fatigue_level = max(fatigue_level, 0.78)
```

**Mechanism 3 — Behavioural inference:**
```
user skips high-intensity stop → fatigue_level += 0.10
user sets pace → "relaxed"    → fatigue_level += 0.08
```

#### Disruption triggers

| EventType | Threshold | Action |
|---|---|---|
| `HUNGER_DISRUPTION` | `hunger_level ≥ 0.70` | Insert meal stop, advance clock +45 min, reset hunger, LocalRepair |
| `FATIGUE_DISRUPTION` | `fatigue_level ≥ 0.75` | Insert rest break, advance clock +20 min, reduce fatigue by 0.40, LocalRepair |

Cooldown: If `current_time − last_meal_time < 40 min`, suppress re-trigger.

#### SC5 adjustment

```
hunger_penalty  = 0.40 if (hungry AND visit_duration > 90 min)
                = 0.10 if (hungry AND visit_duration ≤ 90 min)
                = 0     if stop is a RestaurantRecord
fatigue_penalty = 0.50 if (fatigued AND intensity == "high")
                = 0.20 if (fatigued AND intensity == "medium")

sc5_adjusted    = max(0, sc5_base − hunger_penalty − fatigue_penalty)
restaurant_bonus = +0.30 on SCpti when hungry AND stop is RestaurantRecord

SCpti_adjusted = Σ Wv × scv  where sc5 := sc5_adjusted (+ restaurant_bonus)
Spti_adjusted  = HCpti × SCpti_adjusted                  (Eq 4 variant)
η_ij_adjusted  = Spti_adjusted / Dij                      (Eq 12 variant)
```

#### Advisory panels

- **HUNGER DISRUPTION** — ASCII level bar, ranked meal options with S_pti and Dij, action line.
- **FATIGUE DISRUPTION** — ASCII level bar, rest duration, affected stops, fatigue
  reduction shown.

---

### 9.11 Optimization Trigger Map (Hunger / Fatigue)

| Trigger | EventType | ActionType | Replanner policy |
|---|---|---|---|
| `hunger_level ≥ 0.70` | `HUNGER_DISRUPTION` | `INSERT_MEAL_STOP` | LocalRepair |
| `fatigue_level ≥ 0.75` | `FATIGUE_DISRUPTION` | `INSERT_REST_BREAK` | LocalRepair |
| NLP hunger keyword | `USER_REPORT_DISRUPTION` → NLP hook | `INSERT_MEAL_STOP` | LocalRepair |
| NLP fatigue keyword | `USER_REPORT_DISRUPTION` → NLP hook | `INSERT_REST_BREAK` | LocalRepair |
| User skips high-intensity | behavioural inference | `fatigue_level += 0.10` | No replan (state update only) |
| Pace → relaxed | behavioural inference | `fatigue_level += 0.08` | No replan (state update only) |
| Meal stop visited | `advance_to_stop` + `on_meal_completed` | `hunger_level = 0` | No replan (state update only) |
| Rest break completed | `advance_clock_for_rest` + `on_rest_completed` | `fatigue_level -= 0.40` | LocalRepair already triggered |

**LocalRepair:** Uses `_do_replan()` — same PartialReplanner infrastructure. Clock is
advanced before replanning, so all downstream arrival/departure times are automatically
recomputed from the new `current_time`.

**DisruptionMemory records:** `record_hunger()` and `record_fatigue()` called after each
event with `trigger_time`, level, `action_taken`, `restaurant_name` / `rest_duration`,
and `user_response`. Included in `serialize()` / `deserialize()` for cross-session
persistence.


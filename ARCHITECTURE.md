# TravelAgent — Integrated System Architecture

> Combines: **TravelAgent** · **ICDM** · **FTRM** · **ACO**
> Generated: 2026-02-21 | Updated: 2026-02-21

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
└── Memory Module
    ├── ShortTermMemory          interaction log, session insights
    └── LongTermMemory           Wv weight learning (λ update)
```

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

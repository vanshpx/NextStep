# TravelAgent — Integrated System Architecture

> Stack: **TravelAgent** · **ICDM** · **FTRM** · **ACO** · **Real-Time Re-Optimizer** · **Multi-Agent Orchestrator** · **Observability Layer**
> Last updated: 2026-03-15 (Phase 30 — correctness fixes, observability, multi-agent orchestration)

---

## 1. Project Structure

```
backend/                                    (Python — FTRM + ACO + Re-optimizer)
├── main.py                    Pipeline entry point (1367 lines)
├── config.py                  All env-var configuration
├── ARCHITECTURE.md            This file
├── test_full_pipeline.py      8-part regression suite (Parts 1–8)
├── demo_reoptimizer.py        Standalone re-optimizer demo
├── api/
│   ├── server.py              FastAPI app factory
│   └── routes/
│       ├── health.py          GET /health
│       ├── itinerary.py       POST /itinerary/generate
│       └── reoptimize.py      POST /itinerary/reoptimize
├── db/
│   ├── connection.py          PostgreSQL connection (SQLAlchemy)
│   ├── redis_client.py        Redis session cache
│   ├── promoter.py            STM → LTM promotion logic
│   └── repositories/          ORM repositories (user, itinerary, ...)
├── schemas/
│   ├── constraints.py         HardConstraints / SoftConstraints / CommonsenseConstraints / PassengerDetails / ConstraintBundle
│   ├── itinerary.py           Itinerary / DayPlan / RoutePoint / BudgetAllocation
│   └── ftrm.py                FTRMParameters (α, β, ρ, Wv, SC method)
├── modules/
│   ├── input/
│   │   └── chat_intake.py     Three-phase intake (form → chat NLP → passenger details)
│   ├── tool_usage/
│   │   ├── attraction_tool.py    AttractionRecord + fetch()  (Google Places live / stub)
│   │   ├── hotel_tool.py         HotelRecord + fetch()       (TBO Hotel API live / stub)
│   │   ├── restaurant_tool.py    RestaurantRecord + fetch()
│   │   ├── flight_tool.py        FlightRecord + fetch()      (TBO Air API live / stub)
│   │   ├── booking_manager.py    BookingManager — full TBO hotel + flight booking flows
│   │   ├── city_tool.py          CityRecord + fetch()
│   │   ├── weather_tool.py       WeatherRecord + fetch()  [re-optimizer]
│   │   ├── traffic_tool.py       TrafficRecord + fetch()  [re-optimizer]
│   │   ├── historical_tool.py    HistoricalRecord + fetch()
│   │   ├── distance_tool.py      Haversine local calc
│   │   └── time_tool.py          Time arithmetic local calc
│   ├── recommendation/
│   │   ├── base_recommender.py   Abstract: recommend() + rerank()
│   │   ├── attraction_recommender.py
│   │   ├── hotel_recommender.py
│   │   ├── restaurant_recommender.py
│   │   ├── flight_recommender.py
│   │   ├── budget_recommender.py  LLM → BudgetAllocation
│   │   └── city_recommender.py    LLM → ranked cities
│   ├── optimization/
│   │   ├── satisfaction.py        compute_HC / compute_SC / compute_S / evaluate_satisfaction
│   │   ├── constraint_registry.py evaluate_hc() dispatch per POI type
│   │   ├── aco_optimizer.py       ACOOptimizer + ACOParams + AntState
│   │   └── heuristic.py           compute_eta(S_pti, Dij)
│   ├── planning/
│   │   ├── budget_planner.py      BudgetPlanner.distribute() / validate() / post_itinerary_rebalance()
│   │   ├── route_planner.py       RoutePlanner.plan() → calls ACO per day
│   │   └── attraction_scoring.py  AttractionScorer → S_pti map
│   ├── memory/
│   │   ├── short_term_memory.py   Session log, feedback, insights (in-memory)
│   │   ├── long_term_memory.py    User profile, Wv weights, commonsense rules (file/db)
│   │   └── disruption_memory.py   DisruptionMemory — weather/traffic/replacement learning
│   ├── observability/                                          ← NEW
│   │   ├── logger.py             StructuredLogger — JSONL per-session event log
│   │   └── replay.py             replay_session() — deterministic log replay + hash verification
│   ├── reoptimization/
│   │   ├── session.py             ReOptimizationSession — top-level facade (2351 lines)
│   │   ├── trip_state.py          TripState — live position + visited tracking
│   │   ├── event_handler.py       EventHandler + EventType + ReplanDecision
│   │   ├── condition_monitor.py   ConditionMonitor + ConditionThresholds (≥ comparison)
│   │   ├── partial_replanner.py   PartialReplanner — ACO re-run from current position
│   │   ├── local_repair.py        LocalRepair (963 lines) — 8 invariants, is_user_skip exemption
│   │   ├── alternative_generator.py  AlternativeGenerator — 7-criteria composite scoring   ← NEW
│   │   ├── crowd_advisory.py      CrowdAdvisory + CrowdAdvisoryResult
│   │   ├── weather_advisor.py     WeatherAdvisor + WeatherAdvisoryResult
│   │   ├── traffic_advisor.py     TrafficAdvisor + TrafficAdvisoryResult
│   │   ├── hunger_fatigue_advisor.py  HungerFatigueAdvisor + meal/break injection
│   │   ├── user_edit_handler.py   UserEditHandler — skip/dislike/replace/delay
│   │   ├── agent_action.py        ActionType enum + AgentAction dataclass
│   │   ├── agent_controller.py    AgentController (observe → evaluate → AgentAction)
│   │   ├── execution_layer.py     ExecutionLayer (guardrails → state hash → dispatch → mutation)
│   │   └── agents/                Multi-Agent Orchestrator                                ← NEW
│   │       ├── __init__.py        Re-exports all agent classes
│   │       ├── base_agent.py      BaseAgent (ABC) + AgentContext (read-only)
│   │       ├── orchestrator_agent.py  Pure router → specialist selection
│   │       ├── disruption_agent.py    Crowd/weather/traffic severity classification
│   │       ├── planning_agent.py      Strategy selection (FULL/LOCAL/REORDER/NO_CHANGE)
│   │       ├── budget_agent.py        Financial state evaluation (OK/OVERRUN/UNDERUTILIZED)
│   │       ├── preference_agent.py    Preference extraction (interests/pace/tolerance)
│   │       ├── memory_agent.py        Memory-store routing (LTM vs STM)
│   │       ├── explanation_agent.py   Human-readable trip explanation generation
│   │       └── agent_dispatcher.py    End-to-end pipeline: route → evaluate → execute
│   └── validation/
│       └── ingestion_validator.py  POI data schema validation before pipeline
├── logs/                       JSONL session logs (generated by observability layer)
└── docs/                       Design documents and ADRs

frontend/                                   (Next.js — Agent Dashboard + Client View)
├── src/
│   ├── app/                    Next.js App Router pages
│   │   ├── page.tsx            Landing page (/)
│   │   ├── layout.tsx          Root layout — ItineraryProvider wrapper
│   │   ├── dashboard/
│   │   │   ├── page.tsx        Agent dashboard — OpsPanel + ItineraryTable
│   │   │   ├── layout.tsx      Sidebar + TopBar layout
│   │   │   ├── create/page.tsx Create itinerary → ItineraryBuilderForm
│   │   │   └── edit/[id]/page.tsx  Edit itinerary → ItineraryBuilderForm
│   │   ├── view/[id]/page.tsx  Client-facing trip view (timeline + map)
│   │   └── api/itineraries/    REST API (GET/POST/PATCH/DELETE)
│   ├── components/
│   │   ├── landing/            HeroSection, FeatureCards, ProductPreview, FinalCTA
│   │   ├── dashboard/          Sidebar, TopBar, StatsGrid, OpsPanel, ItineraryTable
│   │   ├── builder/            ItineraryBuilderForm, ClientDetailsForm, TravelDetails,
│   │   │                       HotelStays, DayBuilder, ActivityBlock, LocationPickerModal
│   │   ├── client/             ClientMap (Google Maps), DisruptionModal, DayTimeline
│   │   └── ui/                 Button, Input, AutocompleteInput (CVA + Tailwind)
│   ├── context/
│   │   └── ItineraryContext.tsx Global state — CRUD + auto-activation
│   └── lib/
│       ├── prisma.ts           Singleton PrismaClient
│       ├── googleMaps.ts       useGoogleMaps() hook
│       ├── locationService.ts  OSM Nominatim fallback geocoding
│       ├── mockLocations.ts    Static airport/city/attraction arrays
│       ├── sortActivities.ts   Chronological activity ordering
│       └── utils.ts            cn() + formatLocation()
├── prisma/
│   ├── schema.prisma           5 tables: Itinerary, Flight, HotelStay, Day, Activity
│   └── seed.ts                 Demo itineraries with real GPS coordinates
└── package.json                Next.js 16 + React 19 + Prisma 6 + Tailwind 4
```

---

## 2. Module Diagram

```
TravelAgent System
│
├── [INPUT]  python main.py --chat
│   └── Input Module                    modules/input/chat_intake.py
│       └── ChatIntake.run()
│           ├── Phase 1 — Structured Form  (Hard Constraints — NO LLM)
│           │     Explicit input() prompts:
│           │       departure_city, destination_city, departure_date, return_date
│           │       num_adults, num_children, restaurant_preference, total_budget
│           │       guest_nationality (ISO-2 — used by TBO hotel search)
│           │     → HardConstraints directly — zero hallucination risk
│           │
│           ├── Phase 2 — Free-form Chat  (Soft Constraints via NLP)
│           │     User types naturally about preferences / dislikes
│           │     Single LLM call at end → JSON extraction
│           │     → SoftConstraints + CommonsenseConstraints
│           │
│           └── Phase 3 — Passenger Details  (TBO booking — NO LLM)
│                 Collects per-passenger: title, name, DOB, gender,
│                 email, mobile, nationality_code, id_number/expiry
│                 One set per adult, then per child
│                 → list[PassengerDetails] in ConstraintBundle.passengers
│
│   python main.py           (default — hardcoded constraints)
│   python main.py --reoptimize  (runs pipeline then live re-optimizer demo)
│
├── ICDM  (Item Constraints Data Model)          schemas/constraints.py
│   ├── HardConstraints
│   │   departure/destination city, dates, num_adults, num_children,
│   │   restaurant_preference, requires_wheelchair, fixed_appointments[],
│   │   guest_nationality (ISO-2, e.g. "IN")  ← used in TBO hotel search
│   ├── SoftConstraints
│   │   interests[], travel_preferences[], character_traits[], spending_power
│   │   dietary_preferences[], preferred_time_of_day, avoid_crowds
│   │   pace_preference, preferred_transport_mode[], meal windows,
│   │   rest_interval_minutes, heavy_travel_penalty,
│   │   avoid_consecutive_same_category, novelty_spread
│   ├── CommonsenseConstraints
│   │   rules[]  (free-text from LLM extraction + memory)
│   ├── PassengerDetails  (per-passenger — collected in Phase 3)
│   │   title, first_name, last_name, date_of_birth, gender,
│   │   email, mobile, mobile_country_code, nationality_code,
│   │   passenger_type (1=Adult 2=Child 3=Infant), id_number, id_expiry
│   └── ConstraintBundle  (HC + SC + CC + passengers[] aggregated)
│
├── Tool-usage Module
│   ├── AttractionTool   → Google Places API (live) / stub (USE_STUB_ATTRACTIONS)
│   ├── HotelTool        → TBO Hotel API (live) / stub (USE_STUB_HOTELS)
│   │     Live chain: CityList → TBOHotelCodeList → Hoteldetails + search
│   │     Auth: HTTP Basic (TBO_USERNAME : TBO_PASSWORD)
│   ├── RestaurantTool   → external API (stubbed; USE_STUB_RESTAURANTS)
│   ├── FlightTool       → TBO India Air API (live) / stub (USE_STUB_FLIGHTS)
│   │     Live chain: Authenticate/ValidateAgency → Search/
│   │     IsDomestic auto-detected from _CITY_TO_IATA (40 India IATA codes)
│   │     Token cached per process; reused by BookingManager
│   ├── BookingManager   → TBO full booking flows (new)
│   │     Hotel: prebook_hotel() → book_hotel()
│   │     Flight: fare_quote() → fare_rule() → book_flight() → ticket_flight()
│   │     Convenience: book_flight_full() (FareQuote→FareRule→Book→Ticket)
│   ├── CityTool         → external API (stubbed; CITY_API_URL)
│   ├── WeatherTool      → weather API   (used by re-optimizer)
│   ├── TrafficTool      → traffic API   (used by re-optimizer)
│   ├── HistoricalTool   → visit history (used by re-optimizer)
│   ├── DistanceTool     → local haversine (no API)
│   └── TimeTool         → local arithmetic (no API)
│
├── Validation Module
│   └── ingestion_validator.py  — validates POI records before pipeline entry
│
├── Recommendation Module
│   ├── BaseRecommender          (abstract: recommend() + rerank())
│   │   ├── AttractionRecommender   HC→SC→Spti sort + LLM explanations
│   │   ├── HotelRecommender        HC→SC→Spti sort
│   │   ├── RestaurantRecommender   HC→SC→Spti sort
│   │   ├── FlightRecommender       HC→SC→Spti sort
│   │   ├── BudgetRecommender       LLM → preliminary BudgetAllocation
│   │   └── CityRecommender         LLM → ranked city suggestions
│   └── LLM client  (GeminiClient — google-genai SDK / StubLLMClient for dev)
│
├── FTRM  (Flexible Travel Recommender Model)
│   ├── satisfaction.py
│   │   ├── compute_HC()   Eq 1: HCpti = Π hcm_pti  (binary conjunction)
│   │   ├── compute_SC()   Eq 2: SCpti = agg(Wv, scv)
│   │   │     Methods: sum | least_misery | most_pleasure | multiplicative
│   │   ├── compute_S()    Eq 4: Spti = HCpti × SCpti
│   │   └── evaluate_satisfaction() full chain 1→2→4
│   ├── constraint_registry.py   HC evaluators per POI type:
│   │     ATTRACTION: opening_hours, Tmax, wheelchair, min_age, permit
│   │     HOTEL:      price/night≤budget, availability, wheelchair, star_rating
│   │     RESTAURANT: price/meal≤budget, opening_hours, wheelchair
│   │     FLIGHT:     price≤budget, travel_mode, departure_time_window
│   └── attraction_scoring.py   AttractionScorer → {node_id: Spti} for ACO
│
├── ACO  (Ant Colony Optimization)
│   └── aco_optimizer.py
│       ├── ACOParams      α, β, ρ, Q_deposit, τ_init, n_ants, n_iterations
│       ├── AntState       visited[], t_cur, elapsed_min, cost, tour[]
│       ├── _compute_eta()             ηij = Spti / Dij            (Eq 12)
│       ├── _get_feasible_nodes()      infeasibility filter
│       ├── _select_next()             Pij roulette-wheel          (Eq 13)
│       ├── _local_pheromone_update()  τij ← (1−ρ)τij + δij       (Eq 15)
│       └── _global_pheromone_update() τij ← ρτij + (1−ρ)δij      (Eq 16, best-ant)
│
├── Planning Module
│   ├── BudgetPlanner
│   │   ├── distribute()            Preliminary + post-Stage3 recompute
│   │   ├── validate()              Sum ≤ total_budget check
│   │   └── post_itinerary_rebalance()  Adjusts with real hotel/flight/restaurant costs
│   └── RoutePlanner
│       ├── plan()                  Calls ACO per day, returns Itinerary
│       └── _inject_meals_smart()   Adaptive lunch+dinner insertion (Rules 3,5,6)
│
├── Memory Module
│   ├── ShortTermMemory    Session: interaction log, feedback signals, insights
│   ├── LongTermMemory     Persistent: user profile, Wv weights (λ update), commonsense rules
│   └── DisruptionMemory   In-session: weather tolerance, delay tolerance, replacement patterns
│         5 record types: WeatherRecord, TrafficRecord, ReplacementRecord, HungerRecord, FatigueRecord
│         Inferred metrics: weather_tolerance_level(), delay_tolerance_minutes(), common_replacements()
│         Cross-session: serialize() / deserialize() (JSON)
│
├── Observability Layer          modules/observability/                               ← NEW
│   ├── StructuredLogger         Append-only JSONL per session (thread-safe)
│   │     log(session_id, event_type, payload) → backend/logs/<session_id>.jsonl
│   │     Event types: USER_COMMAND, AGENT_DECISION, GUARDRAIL_CHECK,
│   │                  GUARDRAIL_BLOCK, STATE_MUTATION, PERFORMANCE, SESSION_END
│   └── replay_session()         Deterministic log replay
│         Filters: USER_COMMAND + AGENT_DECISION + STATE_MUTATION
│         Verification: compares after_hash of last STATE_MUTATION →
│                        raises REPLAY_DIVERGENCE on mismatch
│
├── Re-Optimization Module       modules/reoptimization/
│   ├── ReOptimizationSession    Top-level facade; triggered by --reoptimize (2351 lines)
│   │     PendingDecision gate — blocks new disruptions while one is pending
│   │     _handle_empty_day() — calls AlternativeGenerator for 0-POI days
│   ├── TripState                Live position, visited set, elapsed cost
│   ├── EventHandler             Handles: USER_SKIP, USER_DELAY, USER_PREFERENCE_CHANGE
│   ├── ConditionMonitor         Threshold checks: crowd / weather / traffic (≥ comparison)
│   │     ConditionThresholds    Learned from SoftConstraints (avoid_crowds, pace)
│   │     WEATHER_SEVERITY dict  17 mapped conditions (incl. fog=0.40, cold=0.30)
│   ├── PartialReplanner         Runs ACO from current position on remaining pool
│   ├── LocalRepair              Fast swap/insert/remove — 8 invariants, 5 repair strategies
│   │     is_user_skip param     Threads through repair→_repair_inner→_finalise→InvariantChecker
│   │     Inv4 exemption         Stop count ±1 skipped when is_user_skip=True
│   │     Fragile day guard      Rejects meal-only days (0 non-meal POIs)
│   ├── AlternativeGenerator     Context-aware 7-criteria composite scoring               ← NEW
│   │     Weights: distance(0.25), category(0.15), crowd(0.20), weather(0.15),
│   │              timing(0.10), ftrm(0.10), meal(0.05)
│   │     Includes restaurants during meal windows; hard 5 km radius filter
│   ├── CrowdAdvisory            crowd_level ≥ threshold → replan advisory
│   ├── WeatherAdvisor           rainy/stormy → prefer indoor alternatives
│   ├── TrafficAdvisor           traffic delay → resequence or drop
│   ├── HungerFatigueAdvisor     ≥3h sightseeing → inject meal break
│   ├── UserEditHandler          skip/dislike/replace/delay commands (interactive)
│   ├── AgentController          Deterministic rule engine (observe → decide)
│   │     observe(state,…)       Build read-only AgentObservation snapshot
│   │     evaluate(obs)          6-rule chain → AgentAction
│   │     Reads: ConditionMonitor, DisruptionMemory, ShortTermMemory
│   │     Tools: WeatherTool, TrafficTool (read-only)
│   │     CANNOT call: RoutePlanner — only ExecutionLayer may trigger replans
│   │     Logs: AGENT_DECISION events via StructuredLogger
│   ├── ExecutionLayer           Only component that mutates itinerary state
│   │     compute_state_hash()   SHA-256 of TripState (excludes transient fields)
│   │     Guardrails: no multi-stop delete, no hotel/city/budget change
│   │     Logs: GUARDRAIL_CHECK, GUARDRAIL_BLOCK, STATE_MUTATION (before/after hash)
│   │     Dispatch: NO_ACTION → noop
│   │              REQUEST_USER_DECISION → AlternativeGenerator → alternatives
│   │              DEFER_POI → LocalRepair.repair()
│   │              REPLACE_POI → AlternativeGenerator.generate()
│   │              RELAX_CONSTRAINT → parameter relaxation (e.g. max_travel_min)
│   │              REOPTIMIZE_DAY → PartialReplanner.replan() → full ACO rerun
│   └── agents/                  Multi-Agent Orchestrator                                 ← NEW
│         OrchestratorAgent      Pure router — maps event/observation → specialist
│         DisruptionAgent        Classifies severity (LOW/MEDIUM/HIGH) → strategy
│         PlanningAgent          Strategy selection: FULL_PLAN / LOCAL_REPAIR / REORDER
│         BudgetAgent            Financial state: OK / OVERRUN / UNDERUTILIZED
│         PreferenceAgent        Extracts interests, pace, tolerance from context
│         MemoryAgent            LTM vs STM routing based on disruption count
│         ExplanationAgent       2-4 sentence human-readable trip explanation
│         AgentDispatcher        Pipeline: route → evaluate → execute (5-step)
│         All agents extend BaseAgent(ABC); NEVER mutate state — return AgentAction only
│
└── API Layer                    api/
    ├── server.py                FastAPI app
    └── routes/
        ├── health.py            GET  /health
        ├── itinerary.py         POST /itinerary/generate
        └── reoptimize.py        POST /itinerary/reoptimize
```

---

## 3. Data Flow — Full Pipeline

```
Stage 0 — Chat Intake  (--chat mode only)
    [Phase 1 — Structured Form]
      input() prompts → HardConstraints (NO LLM)
      Fields: departure_city, destination_city, dates, adults, children,
              restaurant_preference, wheelchair, total_budget, guest_nationality
    [Phase 2 — Free-form Chat]
      User types preferences → single LLM call → SoftConstraints + CommonsenseRules
    [Phase 3 — Passenger Details]  ← NEW (TBO booking requirement)
      Collects per-passenger: title, name, DOB, gender, email, mobile,
      nationality, ID number — one set per adult + child
      → list[PassengerDetails] stored in ConstraintBundle.passengers
    → ConstraintBundle (hard + soft + commonsense + passengers) + total_budget

Stage 1 — Constraint Modeling
    --chat mode : ConstraintBundle from Stage 0
    default mode: hardcoded HC + LongTermMemory for SC + commonsense
    → ConstraintBundle assembled

Stage 2 — Budget Planning
    ConstraintBundle
    → BudgetRecommender._call_llm()  → preliminary BudgetAllocation (LLM)
    → BudgetPlanner.distribute()     → validated preliminary allocation

Stage 3 — Info Gathering + Recommendation
    Tools fetch raw POI records:
      AttractionTool / HotelTool / RestaurantTool / FlightTool
    → ingestion_validator validates each record
    Per record, FTRM chain runs:
      constraint_registry.evaluate_hc() → hcm_pti[]
      compute_HC()                       → HCpti ∈ {0,1}
      compute_SC(sc_values, Wv, method)  → SCpti ∈ [0,1]
      compute_S()                        → Spti = HCpti × SCpti
    → Sort descending by Spti → ranked recommendations
    → ShortTermMemory.log_interaction(feedback)
    → BudgetPlanner.distribute() recomputed with real prices (Stage 3 data)

Stage 4 — Route Planning
    AttractionScorer → {node_id: Spti} S_pti map
    RoutePlanner.plan() per day:
      ACOOptimizer.optimize():
        _get_feasible_nodes()            → HC + Tmax filter
        _compute_eta()                   → ηij = Spti / Dij
        _select_next()                   → Pij roulette-wheel
        _local_pheromone_update()        → Eq 15
        _global_pheromone_update()       → Eq 16 (best-ant)
      → best_tour → DayPlan
    _inject_meals_smart()                → adaptive lunch + dinner RoutePoints
    → Itinerary
    BudgetPlanner.post_itinerary_rebalance()  → final cost-validated allocation
    itinerary.budget = final allocation

[Optional] Stage 4.5 — TBO Booking  (requires USE_STUB_HOTELS/FLIGHTS=false + passengers in bundle)
    BookingManager.book_hotel(booking_code, fare, passengers, email, phone)
      → POST /PreBook  → POST /Book  → ConfirmationNumber
    BookingManager.book_flight_full(trace_id, result_index, passengers)
      → POST /FareQuote/  → POST /FareRule/  → POST /Booking/Book  → POST /Booking/Ticket  → PNR

Stage 5 — Memory Update
    ltm.promote_from_short_term(stm insights)
    ltm.update_soft_weights(Wv, feedback_summary)  → λ learning
    stm.clear()
    → Updated user profile persisted

[Optional] Real-Time Re-Optimization  (triggered live during trip / --reoptimize)
    ReOptimizationSession.from_itinerary()
    ── No scripted steps; every command is user-initiated ──
    session.check_conditions(crowd_level, traffic_level, weather_condition)
      → builds PendingDecision if threshold exceeded; returns None
      CrowdAdvisory  → crowd > θ_crowd (0.35/0.70) → defer/replace/inform
      WeatherAdvisor → severity > θ_weather → defer outdoor / block unsafe
      TrafficAdvisor → traffic > θ_traffic → DEFER (S≥0.65) or REPLACE (S<0.65)
    session.event(EventType.*) → for skip/replace/preference/hunger/fatigue
      USER_SKIP / USER_DISLIKE_NEXT → approval gate → PendingDecision
      USER_PREFERENCE_CHANGE / HUNGER_DISRUPTION / FATIGUE_DISRUPTION → immediate
    session.resolve_pending("WAIT"|"REPLACE [n]"|"SKIP"|"KEEP")
      → state mutation + replan only after explicit user confirmation
    session.advance_to_stop() → mark visited, update TripState clock
    → Updated DayPlan returned; session.pending_decision cleared

[Optional] Agent Controller  (triggered by `agent` command in --reoptimize CLI)
    session.agent_evaluate(crowd_level, weather_condition, traffic_level, traffic_delay)
    1. AgentController.observe(state, constraints, …) → AgentObservation (read-only snapshot)
       Fields: current_day_plan, remaining_stops, current_time, lat/lon,
               remaining_minutes, budget/spent, crowd/weather/traffic readings,
               thresholds, next_stop context (name, is_outdoor, spti_proxy),
               preferences, disruptions_today count
    2. AgentController.evaluate(obs) → AgentAction  (deterministic 6-rule chain)
       Rule 1: Weather unsafe (severity ≥ HC_UNSAFE 0.75 → REPLACE; moderate → DEFER outdoor)
       Rule 2: Crowd exceeded → DEFER (high-value S_pti ≥ 0.65) or REQUEST_USER_DECISION
       Rule 3: Traffic exceeded → DEFER (high-value) or REPLACE (low-value)
       Rule 4: ≥3 disruptions today → REOPTIMIZE_DAY
       Rule 5: <60 min remaining + >1 stop → RELAX_CONSTRAINT (max_travel_min 60→120)
       Rule 6: No disruption → NO_ACTION
    3. ExecutionLayer.execute(action, state, …) → ExecutionResult
       _check_guardrails(action) — blocks forbidden params (change_hotel, change_city, etc.)
       Dispatch to deterministic module (LocalRepair / AlternativeGenerator / PartialReplanner)
    4. ShortTermMemory.log_interaction() — stores action + result for session continuity
    5. If alternatives generated → build PendingDecision (user must approve/reject/modify)
    → ExecutionResult (new_plan, alternatives, relaxed_constraint, error)
```

---

## 4. FTRM Satisfaction Chain

| Equation | Formula | Implementation |
|---|---|---|
| Eq 1 | `HCpti = Π hcm_pti` | `compute_HC()` in `satisfaction.py` |
| Eq 2 | `SCpti = agg(Wv, scv)` | `compute_SC()` — 4 methods |
| Eq 4 | `Spti = HCpti × SCpti` | `compute_S()` |
| Eq 12 | `ηij = Spti / Dij` | `compute_eta()` in `heuristic.py` |
| Eq 13 | `Pij = (τij^α × ηij^β) / Σ` | `_select_next()` in `aco_optimizer.py` |
| Eq 15 | `τij ← (1−ρ)τij + δij` | `_local_pheromone_update()` |
| Eq 16 | `τij ← ρτij + (1−ρ)δij` | `_global_pheromone_update()` (best-ant) |

**SC Aggregation methods** (config: `SC_AGGREGATION_METHOD`):

| Method | Formula | Use case |
|---|---|---|
| `sum` | `Σ Wv × scv` | Default — smooth blending |
| `least_misery` | `min(scv)` | Pessimistic — bottleneck-driven |
| `most_pleasure` | `max(scv)` | Optimistic — best-feature-driven |
| `multiplicative` | `Π scv^Wv` | Strong penalty for any weak criterion |

---

## 5. Hard Constraint Registry

| POI Type | HC Checks |
|---|---|
| **Attraction** | opening_hours gate, Tmax feasibility (elapsed+Dij+STi≤Tmax), wheelchair, min_age, permit/ticket |
| **Hotel** | price/night≤nightly_budget, availability, wheelchair, min_star_rating |
| **Restaurant** | price/meal≤per_meal_budget, opening_hours, wheelchair |
| **Flight** | price≤flight_budget, travel_mode compatibility, departure_time_window |

---

## 6. Soft Constraints Implemented

| SC Field | Where Used |
|---|---|
| `interests[]` | AttractionRecommender SC scoring |
| `spending_power` | BudgetPlanner budget ratios |
| `dietary_preferences[]` | RestaurantRecommender SC bonus |
| `preferred_time_of_day` | AttractionScorer `_score_optimal_window()` (sc1) |
| `avoid_crowds` | Re-optimizer ConditionThresholds; crowd threshold ↓ |
| `pace_preference` | ConditionThresholds, ACO Tmax per day |
| `preferred_transport_mode[]` | FlightRecommender SC signal |
| `meal_lunch_window` / `meal_dinner_window` | `_inject_meals_smart()` |
| `rest_interval_minutes` | Fatigue check before meal injection |
| `heavy_travel_penalty` | SC penalty on arrival/departure days |
| `avoid_consecutive_same_category` | Route planner SC (back-to-back same type) |
| `novelty_spread` | Route planner SC (culture/nature/food mix) |
| `character_traits[]` | LLM extracted → CommonsenseRules |

---

## 7. LLM Usage Locations

| Location | Module | Purpose | LLM involvement |
|---|---|---|---|
| `ChatIntake._phase2_chat()` | Input | SC extraction from free-form chat | YES — single call at end |
| `BudgetRecommender` | Recommendation | Preliminary budget allocation JSON | YES |
| `CityRecommender` | Recommendation | Ranked city suggestions | YES |
| `AttractionRecommender` | Recommendation | Attraction explanations | YES (optional) |
| `HotelRecommender` | Recommendation | Hotel explanations | YES (optional) |
| `RestaurantRecommender` | Recommendation | Restaurant explanations | YES (optional) |
| `FlightRecommender` | Recommendation | Flight explanations | YES (optional) |
| HC/SC scoring | FTRM | Constraint evaluation | **NO — deterministic only** |
| ACO | Optimization | Route construction | **NO — deterministic only** |

> `StubLLMClient` returns `"[stub response]"` for all calls when `USE_STUB_LLM=true` in config.

---

## 8. Re-Optimization Module

Triggered during live trip or via `python main.py --reoptimize`.

| Component | Role |
|---|---|
| `ReOptimizationSession` | Top-level facade (2351 lines); owns TripState + all advisors + AgentController + agents |
| `TripState` | Tracks current position, visited stops, elapsed cost/time, deferred/skipped sets |
| `EventHandler` | Routes EventType → appropriate handler |
| `ConditionMonitor` | Evaluates crowd/weather/traffic against learned thresholds (≥ comparison) |
| `ConditionThresholds` | Derived from `SoftConstraints` (avoid_crowds, pace_preference) — never hard-coded |
| `WEATHER_SEVERITY` | 17-entry dict mapping conditions to [0,1] severity (incl. fog=0.40, cold=0.30) |
| `PartialReplanner` | Runs full ACO from current position on remaining attraction pool |
| `LocalRepair` | Fast swap/insert/remove — 8 invariants, 5 repair strategies, is_user_skip exemption |
| `AlternativeGenerator` | Context-aware 7-criteria composite scoring within 5 km radius |
| `CrowdAdvisory` | crowd_level ≥ threshold → suggest alternatives |
| `WeatherAdvisor` | rainy/stormy → rerank toward indoor venues |
| `TrafficAdvisor` | delay_minutes ≥ threshold → resequence or drop |
| `HungerFatigueAdvisor` | ≥3h sightseeing block → inject meal/rest |
| `UserEditHandler` | Handles: skip, dislike, replace, delay commands |
| `AgentController` | Deterministic 6-rule engine: observe → evaluate → AgentAction |
| `ExecutionLayer` | Guardrails + state hashing + dispatch (only component that mutates state) |
| `AgentAction` | Typed action schema: action_type, target_poi, reasoning, parameters |
| `ActionType` | Enum: NO_ACTION, REQUEST_USER_DECISION, DEFER_POI, REPLACE_POI, RELAX_CONSTRAINT, REOPTIMIZE_DAY |
| `DisruptionMemory` | In-session learning: weather tolerance, delay tolerance, replacement patterns |

### Correctness Guarantees (Phase 30)

| Guard | Description |
|---|---|
| **Threshold ≥ comparison** | `ConditionMonitor` uses `>=` (not `>`): values equal to threshold trigger disruption |
| **Input validation whitelist** | CLI rejects weather conditions not in `_VALID_WEATHER_CONDITIONS`; crowd/traffic clamped 0–100 |
| **Fragile day guard** | `_finalise()` rejects meal-only days (0 non-meal POIs); prevents degenerate plans |
| **Inv4 USER_SKIP exemption** | `is_user_skip` flag threads through repair chain; Inv4 (count ±1) skipped for user-initiated skips |
| **Empty day handler** | `_handle_empty_day()` calls `AlternativeGenerator` for top-3 suggestions when repair yields 0 POIs |

### Interactive commands (via `--reoptimize` CLI — fully user-driven, no scripted steps):

| Command | Action |
|---|---|
| `crowd <percent>` | Check crowd level (e.g. `crowd 80`) |
| `traffic <percent>` | Check traffic level (e.g. `traffic 65`) |
| `weather <condition>` | Report weather (must be in: `clear`, `rainy`, `stormy`, `hot`, `cold`, `fog`) |
| `skip` | Skip next planned stop immediately |
| `replace` | Replace next stop with best pool alternative |
| `slower` | Switch to relaxed pace; recalculate thresholds |
| `faster` | Switch to fast pace; recalculate thresholds |
| `hungry` | Set hunger 0.80 → fire `HUNGER_DISRUPTION` |
| `tired` | Set fatigue 0.82 → fire `FATIGUE_DISRUPTION` |
| `show options` | List top-5 pool alternatives for next stop |
| `agent [crowd N] [weather C] [traffic N]` | Run Agent Controller (observe → decide → execute) |
| `continue` | Mark next stop visited, advance clock |
| `approve` | Apply disruption action + replan (context-aware: SKIP or REPLACE) |
| `reject` | Keep current plan unchanged (`KEEP`) |
| `modify <n>` | Apply alternative #n (1-based) from pending decision |
| `summary` | Print full session JSON summary |
| `end` / `q` | Exit session, print final summary |

**Approval gate rule**: `crowd`, `traffic`, `weather`, `skip`, `replace`, `hungry`, `tired`
are blocked while a `PendingDecision` is outstanding — resolve with `approve` / `reject` / `modify <n>` first.

**State display** (printed after every command):
`Current Location | Current Time | Next Stop | Remaining Stops | Remaining Budget`

**`resolve_pending()` tokens**: `WAIT` (defer) · `REPLACE [n]` (swap with alt n) · `SKIP` (remove stop permanently) · `KEEP` (no change)
Legacy aliases: `APPROVE` → `REPLACE` (or `SKIP` when event is skip-type) · `REJECT` → `KEEP` · `MODIFY` → `REPLACE`

---

## 9. Multi-Agent Orchestrator

The multi-agent system provides a higher-level abstraction over the `AgentController`.
All agents are **deterministic** and **read-only** — they return `AgentAction` objects but
never mutate state. Only `ExecutionLayer` can modify the itinerary.

### Agent Hierarchy

```
AgentDispatcher.dispatch(context, state, …)
│
├── OrchestratorAgent.route(context) → OrchestratorResult
│     Step 1: Explicit event-type match via _EVENT_ROUTING dict
│     Step 2: Auto-detect from observation thresholds/disruption count
│     Step 3: Fallback → NONE
│
├── Specialist Agent (one of 6):
│   ├── DisruptionAgent.evaluate()    → LOW/MEDIUM/HIGH × IGNORE/ASK/DEFER/REPLACE
│   ├── PlanningAgent.evaluate()      → FULL_PLAN/LOCAL_REPAIR/REORDER/NO_CHANGE
│   ├── BudgetAgent.evaluate()        → OK/OVERRUN/UNDERUTILIZED
│   ├── PreferenceAgent.evaluate()    → extract interests/pace/tolerance
│   ├── MemoryAgent.evaluate()        → LTM (≥3 disruptions) / STM (1-2) / none
│   └── ExplanationAgent.evaluate()   → 2-4 sentence trip explanation
│
├── ExecutionLayer.execute(action, state, …)
│     _check_guardrails() → SafetyViolation if forbidden
│     compute_state_hash() before + after
│     Dispatch to LocalRepair / AlternativeGenerator / PartialReplanner
│     Log STATE_MUTATION event
│
└── ShortTermMemory.log_interaction() → session trace
```

### Key Constants (Agent Layer)

| Constant | Value | Agent |
|---|---|---|
| HC_UNSAFE_WEATHER | 0.75 | DisruptionAgent, AgentController |
| HIGH_VALUE_CUTOFF | 0.65 | DisruptionAgent, AgentController |
| _HIGH_CROWD | 0.85 | DisruptionAgent |
| _HIGH_TRAFFIC | 0.80 | DisruptionAgent |
| MULTI_DISRUPTION_TRIGGER | 3 | PlanningAgent, MemoryAgent |
| TIME_PRESSURE_MINUTES | 60 | PlanningAgent, AgentController |
| OVERRUN_THRESHOLD | 0.90 | BudgetAgent |
| UNDERUTILIZED_THRESHOLD | 0.40 | BudgetAgent |
| TIME_PROGRESS_GATE | 0.60 | BudgetAgent |

---

## 10. Observability Layer

All logging goes to `backend/logs/<session_id>.jsonl` in append-only JSONL format.

### Event Types

| Event | Source | Payload |
|---|---|---|
| `USER_COMMAND` | `main.py` CLI loop | `{command, raw_input}` |
| `AGENT_DECISION` | `AgentController`, agents | `{agent_name, action_type, target, reasoning}` |
| `GUARDRAIL_CHECK` | `ExecutionLayer` | `{action_type, target, result: pass/block}` |
| `GUARDRAIL_BLOCK` | `ExecutionLayer` | `{action_type, violation_reason}` |
| `STATE_MUTATION` | `ExecutionLayer` | `{before_hash, after_hash, action_type, delta}` |
| `PERFORMANCE` | `route_planner.py` | `{stage, elapsed_ms}` |
| `SESSION_END` | `main.py` | `{session_id, total_commands, disruptions}` |

### Session Replay

```bash
python main.py --replay <session_id>
```

Replays `USER_COMMAND + AGENT_DECISION + STATE_MUTATION` events chronologically.
Verifies integrity by comparing the `after_hash` from the last replayed `STATE_MUTATION`
against the last logged hash — raises `RuntimeError("REPLAY_DIVERGENCE")` on mismatch.

### State Hashing

`compute_state_hash(state)` in `execution_layer.py`:
- Serialises all `TripState` fields except transient (`current_day_plan`, `replan_pending`)
- Sets are sorted before hashing; uses `json.dumps(sort_keys=True, default=str)`
- Hash: SHA-256
- Logged as `before_hash` / `after_hash` in every `STATE_MUTATION` event

---

## 11. APIs / Tools

| Tool | Provider | Stage | Status |
|---|---|---|---|
| `ChatIntake` | GeminiClient (Phase 2 only) | Stage 0 | ✅ Implemented |
| `AttractionTool` | Google Places API (`USE_STUB_ATTRACTIONS=false`) | Stage 3 | ✅ Live + stub |
| `HotelTool` | **TBO Hotel API** (`USE_STUB_HOTELS=false`) | Stage 3 | ✅ Live + stub |
| `RestaurantTool` | Custom API | Stage 3 | ⚠️ Stubbed |
| `FlightTool` | **TBO India Air API** (`USE_STUB_FLIGHTS=false`) | Stage 3 | ✅ Live + stub |
| `BookingManager` | **TBO Hotel + Air booking flows** | Post Stage 4 | ✅ Implemented |
| `CityTool` | Custom API | Stage 3 | ⚠️ Stubbed |
| `WeatherTool` | Weather API | Re-optimizer | ⚠️ Stubbed |
| `TrafficTool` | Traffic API | Re-optimizer | ⚠️ Stubbed |
| `HistoricalTool` | Internal history | Re-optimizer | ⚠️ Stubbed |
| `DistanceTool` | Local haversine | Stages 3–4 | ✅ Implemented |
| `TimeTool` | Local arithmetic | Stages 3–4 | ✅ Implemented |
| `AgentController` | Deterministic rule engine (reads tools, never writes) | Re-optimizer | ✅ Implemented |
| `ExecutionLayer` | Guardrails + dispatch → LocalRepair / ACO / AlternativeGen | Re-optimizer | ✅ Implemented |
| `AlternativeGenerator` | 7-criteria composite scoring (read-only) | Re-optimizer | ✅ Implemented |
| `Multi-Agent Orchestrator` | 7 specialist agents + dispatcher | Re-optimizer | ✅ Implemented |
| `StructuredLogger` | JSONL file logging | All stages | ✅ Implemented |
| `GeminiClient` | Google AI Studio (`google-genai`) | Stages 0–3 | ✅ Implemented |
| PostgreSQL | SQLAlchemy | DB Layer | ✅ Schema defined |
| Redis | redis-py | Session cache | ✅ Client defined |
| Google Maps API | Road distance | Stage 4 | ❌ Not wired (haversine used) |

---

## 12. Configuration (config.py)

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | LLM backend | `"google"` |
| `LLM_MODEL_NAME` | Model name | `"gemini-1.5-flash"` |
| `LLM_API_KEY` | Gemini API key | env var |
| `USE_STUB_LLM` | Skip real LLM calls | `true` |
| `USE_STUB_ATTRACTIONS` | Use stub attraction data | `true` |
| `USE_STUB_HOTELS` | Use stub hotel data | `true` |
| `USE_STUB_RESTAURANTS` | Use stub restaurant data | `true` |
| `USE_STUB_FLIGHTS` | Use stub flight data | `true` |
| `GOOGLE_PLACES_API_KEY` | Google Places live key | env var |
| `GOOGLE_PLACES_SEARCH_RADIUS_M` | Nearby search radius | `10000` |
| `GOOGLE_PLACES_MAX_RESULTS` | Max attractions fetched | `20` |
| `TBO_USERNAME` | TBO API username (Hotels + Air) | env var |
| `TBO_PASSWORD` | TBO API password (Hotels + Air) | env var |
| `TBO_HOTEL_BASE_URL` | TBO Hotel API base URL | `http://api.tbotechnology.in/TBOHolidays_HotelAPI` |
| `TBO_AIR_BASE_URL` | TBO Air API base URL | `https://api.tbotechnology.in` |
| `TBO_REQUEST_TIMEOUT` | HTTP timeout (seconds) | `30` |
| `SC_AGGREGATION_METHOD` | SC aggregation | `"sum"` |
| `ACO_ALPHA` | Pheromone weight α | `2.0` |
| `ACO_BETA` | Heuristic weight β | `3.0` |
| `ACO_RHO` | Evaporation rate ρ | `0.1` |
| `ACO_TMAX_MINUTES` | Daily time budget | `600` |
| `MEMORY_BACKEND` | LTM storage | `"in_memory"` |
| `POSTGRES_HOST/PORT/DB` | PostgreSQL connection | env vars |
| `REDIS_HOST/PORT/DB` | Redis connection | env vars |

---

## 13. CLI Entry Points

```bash
# Default pipeline (hardcoded constraints)
python main.py

# Chat intake mode (form HC + NLP SC)
python main.py --chat

# Pipeline then interactive re-optimizer (user-driven, no auto steps)
python main.py --reoptimize

# Chat intake mode + re-optimizer combined
python main.py --chat --reoptimize

# Replay a previous session from JSONL logs (deterministic, no agents/LLM)
python main.py --replay <session_id>

# Standalone re-optimizer demo script
python demo_reoptimizer.py

# Full pipeline test suite (Parts 1–8, exit 0 = all pass)
python test_full_pipeline.py
```

---

## 14. Frontend Architecture (NexStep)

The frontend is a **Next.js 16** application with **React 19**, **Prisma ORM 6** (SQLite),
**Tailwind CSS 4**, and **Google Maps API** integration. It serves as the travel agent's
dashboard for creating, managing, and monitoring itineraries.

### Technology Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router) + React 19 |
| Language | TypeScript 5 |
| Database | SQLite via Prisma ORM 6 |
| Styling | Tailwind CSS 4 + CSS variables |
| Animation | Framer Motion 12 |
| Maps | Google Maps (`@react-google-maps/api`) |
| Icons | Lucide React |
| Location | Google Places Autocomplete + OSM Nominatim fallback |

### Pages (App Router)

| Route | Purpose |
|---|---|
| `/` | Landing page — Hero, Features, Product Preview, CTA |
| `/dashboard` | Agent dashboard — OpsPanel + ItineraryTable |
| `/dashboard/create` | Create itinerary — ItineraryBuilderForm |
| `/dashboard/edit/[id]` | Edit itinerary — ItineraryBuilderForm with initialData |
| `/view/[id]` | Client-facing trip view — timeline (60%) + map/bookings (40%) |

### Database Schema (Prisma)

5 tables with cascading deletes:

| Model | Key Fields |
|---|---|
| **Itinerary** | id, client, destination, dateRange, status (Draft/Upcoming/Active/Completed/Disrupted), origin, totalDays, agentName |
| **Flight** | type (Departure/Return), date, airline, flightNumber, airport, lat/lng |
| **HotelStay** | hotelName, checkIn, checkOut, notes, lat/lng |
| **Day** | dayNumber → has many Activity |
| **Activity** | time, duration, title, location, status (upcoming/completed/current/issue), lat/lng, order |

### State Management

`ItineraryContext` (React Context) wraps entire app:
- `itineraries[]` — in-memory array, fetched from API on mount
- CRUD methods: `addItinerary()`, `updateItinerary()`, `deleteItinerary()`
- **Auto-activation**: Upcoming itineraries with passed departure date → Active

### API Routes

| Endpoint | Methods | Strategy |
|---|---|---|
| `/api/itineraries` | GET, POST | Prisma findMany / create with nested relations |
| `/api/itineraries/[id]` | GET, PATCH, DELETE | Atomic transaction (delete-all + recreate on PATCH) |

### Key Data Flows

1. **Create**: ClientDetails → TravelDetails → HotelStays → DayBuilder → POST → Prisma create
2. **Edit**: GET → hydrate form → PATCH → atomic transaction replace all children
3. **View**: Timeline + Google Maps markers (green=completed, blue+pulse=current, amber=upcoming)
4. **Disruption**: DisruptionModal → status → "Disrupted" via PATCH

---

## 15. FTRM Model — Key Design Points

1. **Hard constraints are binary gates, not penalties.**
   `HC_pti = Π hcm` — if *any* hard constraint fails (venue closed, time budget exceeded, wheelchair inaccessible), the product collapses to 0 and the attraction is removed from the ACO candidate pool entirely. No soft score can rescue a hard-failed stop.

2. **Soft constraints are weighted and fully configurable.**
   `SC_pti = Σ Wv · scv` aggregates three dimensions — rating quality (0.40), interest/category match (0.35), and outdoor preference (0.25) — into a single [0, 1] score. The aggregation method (`sum`, `least_misery`, `most_pleasure`, `multiplicative`) and the weights themselves are learned per user via the long-term memory λ update rule, so the model personalises over time without retraining.

3. **The unified score `S_pti = HC_pti × SC_pti` directly drives ACO.**
   It feeds the heuristic desirability `η_ij = S_pti / D_ij` (Eq 12), which biases ant selection toward high-value, close attractions. This means route quality and constraint satisfaction are optimised *simultaneously* in a single pass — there is no separate feasibility filter after the ACO run.

4. **Threshold comparisons use ≥ (greater-than-or-equal).**
   `ConditionMonitor` triggers disruptions when readings are **equal to or above** the threshold. This ensures deterministic, boundary-inclusive behaviour. The `describe()` method displays `≥ θ` in all human-readable threshold summaries.

5. **LocalRepair invariants protect plan integrity.**
   8 invariants enforce: visited POIs immutable, completed time blocks locked, no duplicate POIs/meals, geographic cluster ≤5 km. Inv4 (stop count ±1) is **exempted** for user-initiated skips via the `is_user_skip` flag chain. The fragile day guard prevents meal-only degenerate plans.

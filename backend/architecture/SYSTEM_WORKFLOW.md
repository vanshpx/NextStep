# System Workflow — Travel Itinerary Optimizer

> End-to-end system workflow covering the backend pipeline, real-time re-optimization,
> multi-agent orchestration, observability, and frontend integration.
> Last updated: 2026-03-15

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Backend Pipeline (Stages 0–5)](#2-backend-pipeline-stages-05)
3. [Real-Time Re-Optimization](#3-real-time-re-optimization)
4. [Multi-Agent Orchestrator](#4-multi-agent-orchestrator)
5. [Observability & Replay](#5-observability--replay)
6. [Frontend Application](#6-frontend-application)
7. [Data Model & Schemas](#7-data-model--schemas)
8. [Integration Points](#8-integration-points)
9. [Complete Request Lifecycle](#9-complete-request-lifecycle)

---

## 1. System Overview

The system is a two-tier travel planning platform:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 16)                        │
│   Landing Page → Agent Dashboard → Itinerary Builder → Client View  │
│   State: React Context │ DB: SQLite/Prisma │ Maps: Google Maps API  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ REST API (planned integration)
┌───────────────────────────────▼─────────────────────────────────────┐
│                        BACKEND (Python)                              │
│                                                                      │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐    │
│   │  ICDM    │──▶│  FTRM    │──▶│   ACO    │──▶│  Itinerary   │    │
│   │Constraint│   │Scoring   │   │Optimizer │   │  Output      │    │
│   │  Model   │   │HC×SC=S   │   │RoutePlan │   │              │    │
│   └──────────┘   └──────────┘   └──────────┘   └──────┬───────┘    │
│                                                         │            │
│   ┌─────────────────────────────────────────────────────▼──────┐    │
│   │              REAL-TIME RE-OPTIMIZER                          │    │
│   │  ConditionMonitor → Advisors → LocalRepair/PartialReplanner │    │
│   │  AgentController → ExecutionLayer (guardrails + state hash)  │    │
│   │  Multi-Agent Orchestrator (7 specialists + dispatcher)       │    │
│   └──────────────────────────┬──────────────────────────────────┘    │
│                               │                                      │
│   ┌───────────────────────────▼──────────────────────────────────┐   │
│   │  OBSERVABILITY: StructuredLogger → JSONL → replay_session()  │   │
│   └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Memory: STM (session) + LTM (persistent) + DisruptionMemory       │
│   API: FastAPI (health, generate, reoptimize)                        │
│   DB: PostgreSQL (SQLAlchemy) + Redis (session cache)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Backend Pipeline (Stages 0–5)

### Stage 0 — Chat Intake (`--chat` mode)

```
User ──────────────────────────────────────────────────────▶ ConstraintBundle
       │                                                          ▲
       ▼                                                          │
  ┌─Phase 1─┐    ┌─Phase 2──────────┐    ┌─Phase 3──────────┐    │
  │Structured│    │Free-form Chat    │    │Passenger Details  │    │
  │Form (HC) │    │NLP → SC + CC     │    │TBO booking fields │    │
  │NO LLM   │    │Single LLM call   │    │NO LLM            │    │
  └────┬─────┘    └────┬──────────────┘    └────┬──────────────┘    │
       │               │                        │                  │
       └───────────────┴────────────────────────┴──────────────────┘
```

**Phase 1 — Structured Form (NO LLM)**
- `input()` prompts for: departure_city, destination_city, dates, adults, children,
  restaurant_preference, wheelchair, total_budget, guest_nationality
- Directly populates `HardConstraints` — zero hallucination risk

**Phase 2 — Free-form Chat (Single LLM call)**
- User types naturally about preferences/dislikes
- `_extract_interests_local()` runs keyword extraction (40+ keyword→category mappings)
- Single LLM call at end → JSON extraction → `SoftConstraints` + `CommonsenseConstraints`
- `_apply_local_sc_fallbacks()` fills missing SC fields from keyword/budget heuristics

**Phase 3 — Passenger Details (NO LLM)**
- Per-passenger: title, name, DOB, gender, email, mobile, nationality, ID
- Required for TBO hotel + flight booking flows
- → `list[PassengerDetails]` in `ConstraintBundle.passengers`

**Output**: `ConstraintBundle` (HC + SC + CC + passengers) + `total_budget`

### Stage 1 — Constraint Modeling

```
--chat mode:  ConstraintBundle from Stage 0
default mode: Hardcoded HC + LongTermMemory for SC + commonsense
→ ConstraintBundle assembled
```

**TRACE block** (printed after Stage 1):
```
[TRACE] UserDestination / ConstraintDestination / UserBudget / ConstraintBudget / SoftInterests
```

### Stage 2 — Budget Planning

```
ConstraintBundle
  → BudgetRecommender._call_llm()    → Preliminary BudgetAllocation (LLM)
  → BudgetPlanner.distribute()       → Validated preliminary allocation
```

Budget categories: Accommodation, Restaurants, Attractions, Transportation, Other, Reserve.
All have caps (see MATH.md §9). Reserve floor: 5% of total budget.

### Stage 3 — Info Gathering + Recommendation

```
                    Tools fetch raw POI records
                    ┌──────────────────────────┐
                    │ AttractionTool.fetch()    │──── Google Places / stub
                    │ HotelTool.fetch()         │──── TBO Hotel API / stub
                    │ RestaurantTool.fetch()    │──── stub
                    │ FlightTool.fetch()        │──── TBO Air API / stub
                    └────────────┬─────────────┘
                                 ▼
                    ingestion_validator validates each record
                                 ▼
                    ┌──────────────────────────┐
                    │ FTRM chain per record:   │
                    │  evaluate_hc() → hcm[]   │
                    │  compute_HC()  → HCpti   │  Eq 1: Π hcm
                    │  compute_SC()  → SCpti   │  Eq 2: Σ Wv·scv
                    │  compute_S()   → Spti    │  Eq 4: HC × SC
                    └────────────┬─────────────┘
                                 ▼
                    Sort descending by Spti
                    → ranked_attractions, ranked_hotels, etc.
                    → BudgetPlanner.distribute() recomputed with real prices
```

**Pre-Stage 4 Pipeline Guard** (4 checks — raises `RuntimeError` on failure):

| Guard | Check |
|---|---|
| PIPELINE_GUARD[1] | `ranked_attractions` must not be empty |
| PIPELINE_GUARD[2] | Every `a.city == destination_city` |
| PIPELINE_GUARD[3] | `has_chat_input` ⇒ interests not empty |
| PIPELINE_GUARD[4] | `total_budget > 0` and matches `constraints.total_budget` |

### Stage 4 — Route Planning

```
AttractionScorer → {node_id: Spti} map
                    │
                    ▼
        RoutePlanner.plan() per day:
        ┌───────────────────────────────────────┐
        │ _validate_hotel_anchor()              │ Hotel ≤ 50 km from city center
        │ K-means geographic clustering          │ Cluster radius ≤ 9.0 km
        │ ACOOptimizer.optimize():              │
        │   _compute_eta()   → ηij = Spti/Dij  │ Eq 12
        │   _get_feasible()  → HC + Tmax filter │
        │   _select_next()   → Pij roulette     │ Eq 13
        │   _local_pheromone_update()            │ Eq 15
        │   _global_pheromone_update()           │ Eq 16 (best-ant)
        │ → best_tour per day                   │
        └───────────────────┬───────────────────┘
                            ▼
        _inject_meals_smart() → adaptive lunch + dinner RoutePoints
        → Itinerary (list[DayPlan])
        → BudgetPlanner.post_itinerary_rebalance() → final allocation
```

**Three-pass retry** if `scheduled < 2` stops per day:
1. Normal: buffer=12 min, max_travel=60 min
2. Relax buffer → 0 min
3. Relax buffer + max_travel → 120 min

### Stage 4.5 — TBO Booking (Optional)

Requires `USE_STUB_HOTELS=false` + `USE_STUB_FLIGHTS=false` + passengers in bundle.

```
BookingManager.book_hotel()
  → POST /PreBook → POST /Book → ConfirmationNumber

BookingManager.book_flight_full()
  → POST /FareQuote → POST /FareRule → POST /Book → POST /Ticket → PNR
```

### Stage 5 — Memory Update

```
ltm.promote_from_short_term(stm insights)
ltm.update_soft_weights(Wv, feedback_summary)  → λ learning rule
stm.clear()
→ Updated user profile persisted
```

The λ update rule: $W_{v,new} = W_{v,old} + 0.1 \times feedback_v$, clamped ≥ 0, re-normalised.

---

## 3. Real-Time Re-Optimization

Triggered via `--reoptimize` CLI flag (after pipeline completes) or API endpoint.
**Fully user-driven** — no scripted steps. Every action requires explicit user confirmation.

### 3.1 Session Lifecycle

```
                Pipeline Output (Itinerary)
                         │
                         ▼
        ReOptimizationSession.from_itinerary()
        ┌────────────────────────────────────────┐
        │ TripState initialised                  │
        │ ConditionThresholds derived from SC    │
        │ DisruptionMemory created (empty)       │
        │ AgentController + ExecutionLayer ready  │
        │ Multi-Agent Orchestrator ready          │
        └────────────────┬───────────────────────┘
                         ▼
        ┌─────── Interactive Command Loop ───────┐
        │                                         │
        │  User types command (e.g. crowd 80)    │
        │         │                               │
        │         ▼                               │
        │  Parse + validate                      │
        │         │                               │
        │         ▼                               │
        │  [Disruption gate: blocked if           │
        │   PendingDecision is outstanding]       │
        │         │                               │
        │         ▼                               │
        │  check_conditions() / event() / ...    │
        │         │                               │
        │         ▼                               │
        │  PendingDecision created (if needed)   │
        │         │                               │
        │         ▼                               │
        │  User: approve / reject / modify <n>   │
        │         │                               │
        │         ▼                               │
        │  resolve_pending() → state mutation    │
        │         │                               │
        │         ▼                               │
        │  Print: Location | Time | Next | Budget │
        │                                         │
        └─────────────────────────────────────────┘
```

### 3.2 Disruption Handling Flow

```
User: "crowd 80"
  │
  ▼
Input validation: 0 ≤ percent ≤ 100
  │
  ▼
ConditionMonitor.check_crowd(crowd_level=0.80)
  │
  ├─ crowd_level < θ_crowd → No disruption
  │
  └─ crowd_level ≥ θ_crowd → Disruption triggered
       │
       ▼
  CrowdAdvisory → 3 strategies:
  ┌─────────────────────────────────────────────────┐
  │ 1. reschedule_same_day  (enough time today)     │
  │ 2. reschedule_future_day (move to day+1)        │
  │ 3. inform_user (HC cannot save; user decides)   │
  └──────────────────┬──────────────────────────────┘
                     ▼
  → PendingDecision with alternatives
  → User must resolve: WAIT | REPLACE [n] | SKIP | KEEP
```

### 3.3 Weather Disruption

```
User: "weather rainy"
  │
  ▼
_VALID_WEATHER_CONDITIONS check: {clear, rainy, stormy, hot, cold, fog}
  │
  ▼
WEATHER_SEVERITY lookup: rainy → 0.65
  │
  ├─ severity ≥ 0.75 (HC_UNSAFE) → HC_pti = 0, stop BLOCKED
  ├─ θ_weather ≤ severity < 0.75 → stop DEFERRED, ST × 0.75
  └─ severity < θ_weather → No action
```

### 3.4 Traffic Disruption

```
User: "traffic 70"
  │
  ▼
traffic_level ≥ θ_traffic?
  │
  ▼
D_ij_new = D_ij_base × (1 + traffic_level)
  │
  ├─ S_pti ≥ 0.65 → DEFER (high-value, keep for later)
  └─ S_pti < 0.65 → REPLACE (low-value, swap nearby)
```

### 3.5 User-Initiated Actions

```
skip    → permanent removal + LocalRepair (is_user_skip=True, Inv4 exempt)
replace → AlternativeGenerator top candidates → PendingDecision
slower  → pace = relaxed, θ_crowd/traffic/weather recalculated
faster  → pace = fast, thresholds recalculated
hungry  → hunger_level=0.80 → HUNGER_DISRUPTION → meal injection
tired   → fatigue_level=0.82 → FATIGUE_DISRUPTION → rest break
```

### 3.6 LocalRepair Strategy Chain

```
Disruption event
  │
  ▼
Step 1: Remove disrupted stop
  │
  ▼
Step 2: ShiftLater (±2 positions, crowd decay recheck)
  │ fail?
  ▼
Step 3: SwapWithNext
  │ fail?
  ▼
Step 4: ReplaceNearby (ACO η-ranked within 3 km)
  │ fail?
  ▼
Step 5: DeferToNextDay
  │ fail?
  ▼
Empty day result → _handle_empty_day() → AlternativeGenerator top-3

All strategies pass through:
  _finalise() → _validate_and_fix_meals()
             → Fragile day guard (non_meal_count > 0)
             → InvariantChecker.check() (8 invariants)
```

### 3.7 Empty Day Handler

When repair yields 0 non-meal POIs:

```
_handle_empty_day(repair_result)
  │
  ▼
AlternativeGenerator.generate(n_alternatives=3)
  │
  ▼
Print suggestions (NOT auto-injected)
  │
  ▼
User decides via approve/reject/modify
```

---

## 4. Multi-Agent Orchestrator

Higher-level abstraction over the `AgentController`. All agents are **deterministic**
and **read-only** — they return `AgentAction` objects but never mutate state.

### 4.1 Dispatch Pipeline

```
User: "agent crowd 80 weather rainy"
  │
  ▼
Build AgentContext (observation + event_type + parameters)
  │
  ▼
AgentDispatcher.dispatch()
  │
  ├─ Step 1: OrchestratorAgent.route()
  │    ├─ Explicit: _EVENT_ROUTING dict (11 keywords → agents)
  │    ├─ Auto-detect: threshold breach / disruption count / time pressure
  │    └─ Fallback: NONE
  │         → OrchestratorResult {invoke_agent, reason}
  │
  ├─ Step 2: Look up specialist from _specialists dict
  │
  ├─ Step 3: specialist.evaluate(context) → AgentAction
  │    ├─ DisruptionAgent:  LOW/MEDIUM/HIGH → IGNORE/ASK/DEFER/REPLACE
  │    ├─ PlanningAgent:    FULL_PLAN/LOCAL_REPAIR/REORDER/NO_CHANGE
  │    ├─ BudgetAgent:      OK/OVERRUN/UNDERUTILIZED
  │    ├─ PreferenceAgent:  Extract interests/pace/tolerance
  │    ├─ MemoryAgent:      LTM (≥3 disruptions) / STM (1-2) / none
  │    └─ ExplanationAgent: 2-4 sentence natural language explanation
  │
  ├─ Step 4: ExecutionLayer.execute(action, state, ...)
  │    ├─ _check_guardrails() → block if forbidden params
  │    ├─ compute_state_hash() → before_hash
  │    ├─ Dispatch: LocalRepair / AlternativeGen / PartialReplanner
  │    ├─ compute_state_hash() → after_hash
  │    └─ Log STATE_MUTATION event
  │
  └─ Step 5: ShortTermMemory.log_interaction() → session trace
       → DispatchResult {routing, specialist_name, action, execution_result}
```

### 4.2 Agent Decision Rules

**AgentController** (6-rule deterministic chain):

| Priority | Condition | Action |
|---|---|---|
| 1 | Weather severity ≥ 0.75 | REPLACE (outdoor) |
| 1b | Weather severity ≥ θ_weather | DEFER (outdoor) |
| 2 | Crowd > θ_crowd, S_pti ≥ 0.65 | DEFER |
| 2b | Crowd > θ_crowd, S_pti < 0.65 | REQUEST_USER_DECISION |
| 3 | Traffic > θ_traffic, S_pti ≥ 0.65 | DEFER |
| 3b | Traffic > θ_traffic, S_pti < 0.65 | REPLACE |
| 4 | ≥3 disruptions today | REOPTIMIZE_DAY |
| 5 | ≤60 min remaining + >1 stop | RELAX_CONSTRAINT |
| 6 | No disruption | NO_ACTION |

**Note**: AgentController uses `>` for crowd/traffic/weather checks (strictly greater),
while ConditionMonitor uses `≥` (greater-or-equal). This is intentional — the agent
is slightly more conservative than the condition monitor.

### 4.3 Guardrails

| Rule | Description |
|---|---|
| No multi-stop delete | `targets` list length must be ≤ 1 |
| Forbidden parameters | `change_hotel`, `change_city`, `modify_budget`, `delete_multiple`, `override_hc` |
| Logging | Every check logged as GUARDRAIL_CHECK; violations as GUARDRAIL_BLOCK |

---

## 5. Observability & Replay

### 5.1 Logging Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ main.py CLI │     │ AgentController  │     │ ExecutionLayer   │
│ USER_COMMAND│     │ AGENT_DECISION   │     │ GUARDRAIL_CHECK  │
│ SESSION_END │     │                  │     │ GUARDRAIL_BLOCK  │
│             │     │                  │     │ STATE_MUTATION   │
└──────┬──────┘     └────────┬─────────┘     └────────┬─────────┘
       │                      │                        │
       └──────────────────────┴────────────────────────┘
                              │
                              ▼
              StructuredLogger.log(session_id, event_type, payload)
                              │
                              ▼
              backend/logs/<session_id>.jsonl
              (append-only, thread-safe, one JSON object per line)
```

Each JSONL record:
```json
{
  "timestamp": "2026-03-15T10:30:00.000Z",
  "session_id": "abc123",
  "event_type": "STATE_MUTATION",
  "payload": {
    "before_hash": "a1b2c3...",
    "after_hash": "d4e5f6...",
    "action_type": "DEFER_POI",
    "delta": { ... }
  }
}
```

### 5.2 Session Replay

```bash
python main.py --replay <session_id>
```

```
Read <session_id>.jsonl
  │
  ▼
Filter to: USER_COMMAND + AGENT_DECISION + STATE_MUTATION
  │
  ▼
Print chronologically:
  Step 1: [USER_COMMAND] crowd 80
  Step 2: [AGENT_DECISION] DisruptionAgent → DEFER_POI
  Step 3: [STATE_MUTATION] hash a1b2→d4e5
  ...
  │
  ▼
Verify: last replayed after_hash == last logged after_hash
  ├─ Match → "Replay verified OK"
  └─ Mismatch → RuntimeError("REPLAY_DIVERGENCE")
```

### 5.3 State Hashing

SHA-256 of all `TripState` fields except transient (`current_day_plan`, `replan_pending`).
Sets sorted before hashing. Provides tamper detection and replay integrity.

### 5.4 Performance Measurement

`route_planner.py` logs `PERFORMANCE` events with `{stage, elapsed_ms}` for ACO timing.
`partial_replanner.py` and `local_repair.py` wrap core logic in timing decorators.

---

## 6. Frontend Application

### 6.1 Technology Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router) + React 19 |
| Language | TypeScript 5 |
| Database | SQLite via Prisma ORM 6 |
| Styling | Tailwind CSS 4 + Framer Motion 12 |
| Maps | Google Maps API + Leaflet (available) |
| Icons | Lucide React |

### 6.2 User Journey — Travel Agent

```
Agent opens NexStep
  │
  ▼
Landing Page (/)
  │ "Get Started"
  ▼
Dashboard (/dashboard)
  ┌─────────────────────────────────────────────────┐
  │  Sidebar: Dashboard, Create, All Trips, Logout  │
  │  TopBar: Search, Notifications, Profile          │
  │  StatsGrid: Total | Active | Upcoming | Done     │
  │  OpsPanel:                                       │
  │    NeedsAttention: disrupted, missing flights    │
  │    ActiveTrips: grouped by Today/Tomorrow/Later  │
  │  ItineraryTable: filterable, expandable rows     │
  └─────────────┬───────────────────────────────────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
  Create      Edit      View/Share
```

### 6.3 Itinerary Builder Flow

```
/dashboard/create (new) or /dashboard/edit/[id] (existing)
  │
  ▼
ItineraryBuilderForm
  │
  ├─ ClientDetailsForm
  │    Client name, age, contact, origin, destination, days
  │    AutocompleteInput (Google Places → static fallback → OSM)
  │
  ├─ TravelDetails
  │    Departure + Return flights/trains
  │    Airport autocomplete, dates, airline, times
  │    Auto-locks departure column if trip started
  │
  ├─ HotelStays
  │    Accordion-style hotel manager
  │    Google Places autocomplete for hotel name
  │    Check-in/out dates, notes, lat/lng
  │
  └─ DayBuilder
       Day-by-day schedule
       ├─ ActivityBlock per activity
       │    12h time picker, title, location
       │    GPS validation badge
       │    LocationPickerModal (Google Maps click-to-place)
       └─ Auto-schedules arrival/departure from flight info
  │
  ▼
Save: "Draft" or "Finalize"
  │
  ├─ Draft → status = "Draft"
  └─ Finalize → status = "Upcoming" (future) or "Active" (past departure)
  │
  ▼
POST /api/itineraries → Prisma create with nested relations
  → computeActivityOrder() sorts by chronological time
  → Redirect to /dashboard
```

### 6.4 Client Trip View

```
/view/[id]
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│                   Trip View (split layout)               │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │  Left Panel (60%)    │  │  Right Panel (40%)        │  │
│  │                      │  │                           │  │
│  │  Day-by-Day Timeline │  │  Google Maps (ClientMap)  │  │
│  │  - Animated progress │  │  - Green: completed       │  │
│  │  - Current stop pulse│  │  - Blue+pulse: current    │  │
│  │  - Activity cards    │  │  - Amber: upcoming        │  │
│  │  - "View on Map" btn │  │  - Click → info popup     │  │
│  │  - "Report Issue"    │  │                           │  │
│  │                      │  │  Booking Dashboard:       │  │
│  │                      │  │  - Arrival/Dept Flight    │  │
│  │                      │  │  - Hotel Stay             │  │
│  │                      │  │  - Emergency Contact      │  │
│  └──────────────────────┘  └──────────────────────────┘  │
│                                                          │
│  DisruptionModal:                                        │
│  Report: Delay, Cancellation, Missed Connection, etc.   │
│  → status changes to "Disrupted" via PATCH              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 6.5 Database Schema (Prisma/SQLite)

```
Itinerary (1)
  ├── Flight (0..N)      — Departure/Return, airline, times, GPS
  ├── HotelStay (0..N)   — name, check-in/out, GPS
  └── Day (0..N)
       └── Activity (0..N) — time, duration, title, location, status, GPS, order
```

All child relations use `onDelete: Cascade`.

Status enum: `Draft | Upcoming | Active | Completed | Disrupted`

**Auto-activation**: On page load, any "Upcoming" itinerary with departure date ≤ today
is automatically promoted to "Active" (local update + fire-and-forget PATCH).

### 6.6 API Routes

| Endpoint | Method | Operation |
|---|---|---|
| `/api/itineraries` | GET | List all with all relations |
| `/api/itineraries` | POST | Create with nested relations + `computeActivityOrder()` |
| `/api/itineraries/[id]` | GET | Get single by ID |
| `/api/itineraries/[id]` | PATCH | Atomic transaction: update scalars, delete-all children + recreate |
| `/api/itineraries/[id]` | DELETE | Cascade delete |

### 6.7 State Management

`ItineraryContext` (React Context) wraps entire application:

| Method | Description |
|---|---|
| `itineraries[]` | In-memory array of all itineraries |
| `addItinerary(data)` | POST → prepend to array |
| `updateItinerary(id, data)` | PATCH → replace in array |
| `deleteItinerary(id)` | DELETE → remove from array |
| `getItinerary(id)` | Local array lookup |
| `refreshItineraries()` | Re-fetch all from API |

### 6.8 Location Services Priority

```
1. Google Places Autocomplete (NEXT_PUBLIC_GOOGLE_MAPS_API_KEY)
   │ not available?
   ▼
2. Static mock data (21 airports, 19 cities, 10 attractions)
   │ not found?
   ▼
3. OpenStreetMap Nominatim geocoding (5s timeout, max 5 results)
```

---

## 7. Data Model & Schemas

### 7.1 Backend Schemas

| Schema | Module | Key Fields |
|---|---|---|
| `HardConstraints` | `schemas/constraints.py` | departure/destination city, dates, adults, children, wheelchair, guest_nationality |
| `SoftConstraints` | `schemas/constraints.py` | interests[], pace_preference, avoid_crowds, dietary_preferences[], spending_power |
| `CommonsenseConstraints` | `schemas/constraints.py` | rules[] (free-text) |
| `PassengerDetails` | `schemas/constraints.py` | Per-passenger: title, name, DOB, gender, email, mobile, nationality, ID |
| `ConstraintBundle` | `schemas/constraints.py` | HC + SC + CC + passengers[] + total_budget + has_chat_input |
| `AttractionRecord` | `tool_usage/attraction_tool.py` | name, city, category, location(lat,lng), rating, visit_duration, historical_importance |
| `HotelRecord` | `tool_usage/hotel_tool.py` | name, price_per_night, star_rating, location, booking_code |
| `RestaurantRecord` | `tool_usage/restaurant_tool.py` | name, cuisine, avg_price_per_person, location |
| `FlightRecord` | `tool_usage/flight_tool.py` | airline, departure/arrival time, price, result_index, trace_id |
| `Itinerary` | `schemas/itinerary.py` | days: list[DayPlan], budget: BudgetAllocation |
| `DayPlan` | `schemas/itinerary.py` | day_number, stops: list[RoutePoint] |
| `RoutePoint` | `schemas/itinerary.py` | attraction, arrival_time, departure_time, travel_time |
| `BudgetAllocation` | `schemas/itinerary.py` | accommodation, restaurants, attractions, transportation, other, reserve, total |
| `FTRMParameters` | `schemas/ftrm.py` | α, β, ρ, Q, τ_init, Wv[], sc_aggregation_method |

### 7.2 Re-optimization Schemas

| Schema | Module | Key Fields |
|---|---|---|
| `TripState` | `reoptimization/trip_state.py` | current_day, current_time, visited, skipped, deferred, budget_spent |
| `PendingDecision` | `reoptimization/session.py` | action, alternatives[], event_type |
| `AgentAction` | `reoptimization/agent_action.py` | action_type (ActionType enum), target_poi, reasoning, parameters |
| `AgentObservation` | `reoptimization/agent_controller.py` | current_day_plan, remaining_stops, crowd/weather/traffic, thresholds, budget |
| `RepairResult` | `reoptimization/local_repair.py` | new_plan, invariants_satisfied, error_code, strategy_used |
| `AlternativeOption` | `reoptimization/alternative_generator.py` | rank, name, category, distance_km, composite_score, why_suitable |
| `ExecutionResult` | `reoptimization/execution_layer.py` | new_plan, alternatives, relaxed_constraint, error |
| `DispatchResult` | `reoptimization/agents/agent_dispatcher.py` | routing, specialist_name, action, execution_result |
| `DisruptionMemory` | `memory/disruption_memory.py` | weather/traffic/replacement/hunger/fatigue records + inference methods |

### 7.3 Frontend Schemas

| Interface | Key Fields |
|---|---|
| `Itinerary` | id, c (client), d (destination), status, date, flights?, hotelStays?, itineraryDays? |
| `Activity` | id, time, duration?, title, location, notes, status, lat?, lng? |
| `Day` | id, dayNumber, activities[] |
| `Flight` | id, type, date?, airline?, flightNumber?, flightTime?, arrivalTime?, airport?, lat?, lng? |
| `HotelStay` | id, hotelName, checkIn?, checkOut?, notes?, lat?, lng? |

---

## 8. Integration Points

### 8.1 Backend ↔ External APIs

| Integration | Protocol | Auth | Status |
|---|---|---|---|
| Google Places (Attractions) | REST (places.googleapis.com) | API Key | ✅ Live + stub |
| Google Geocoding | REST (maps.googleapis.com) | API Key | ✅ Live (bypass via _CITY_CENTERS) |
| TBO Hotels | REST (api.tbotechnology.in) | HTTP Basic | ✅ Live + stub |
| TBO Air | REST (api.tbotechnology.in) | Bearer token | ✅ Live + stub |
| Gemini LLM | Python SDK (google-genai) | API Key | ✅ Live + stub |
| PostgreSQL | SQLAlchemy | Credentials | ✅ Schema defined |
| Redis | redis-py | Credentials | ✅ Client defined |

### 8.2 Frontend ↔ Backend (Planned)

Currently the frontend operates independently with its own SQLite database.
Planned integration:

```
Frontend (Next.js)
  │
  ├── POST /api/itinerary/generate
  │     body: { constraints, preferences }
  │     → Backend: run_pipeline() → Itinerary
  │
  ├── POST /api/itinerary/reoptimize
  │     body: { session_id, command, parameters }
  │     → Backend: session.check_conditions() / session.event()
  │
  └── GET /health
        → Backend: status check
```

### 8.3 Frontend ↔ External APIs

| Integration | Protocol | Status |
|---|---|---|
| Google Maps JS SDK | Client-side | ✅ (NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) |
| Google Places Autocomplete | Client-side | ✅ |
| OpenStreetMap Nominatim | REST (nominatim.openstreetmap.org) | ✅ Fallback |

---

## 9. Complete Request Lifecycle

### 9.1 New Trip — End to End

```
┌──────────────────────────────────────────────────────────────────┐
│                     INITIAL PLANNING                              │
│                                                                   │
│  Agent opens Dashboard → clicks "Create Itinerary"                │
│       │                                                           │
│       ▼ (Frontend)                                                │
│  ItineraryBuilderForm → fills client, travel, hotel, activities  │
│       │                                                           │
│       ▼ (Frontend API)                                            │
│  POST /api/itineraries → Prisma creates itinerary + children     │
│       │                                                           │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                                                   │
│       ▼ (Backend — when integrated)                               │
│  ChatIntake → ConstraintBundle                                    │
│  BudgetPlanner → BudgetAllocation                                 │
│  Tools → fetch attractions/hotels/restaurants/flights             │
│  FTRM → score all candidates (HC × SC = S_pti)                   │
│  ACO → optimise daily routes                                      │
│  RoutePlanner → Itinerary with concrete times                     │
│  BudgetPlanner.post_itinerary_rebalance()                         │
│  Memory update → persist weights                                  │
│       │                                                           │
│       ▼                                                           │
│  Itinerary stored → Agent shares link                             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     LIVE TRIP MONITORING                           │
│                                                                   │
│  Trip starts → auto-activated to "Active" on page load            │
│       │                                                           │
│       ▼ (Client View)                                             │
│  /view/[id] → timeline + map + booking cards                     │
│       │                                                           │
│       ├─ Normal: client follows timeline, views map               │
│       │                                                           │
│       └─ Disruption reported via DisruptionModal                  │
│            → status → "Disrupted" → appears in OpsPanel           │
│                                                                   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                                                   │
│       ▼ (Backend Re-optimizer)                                    │
│  ReOptimizationSession receives disruption                        │
│       │                                                           │
│       ▼                                                           │
│  ConditionMonitor evaluates (≥ threshold?)                        │
│       │                                                           │
│       ├─ Below threshold → No action                              │
│       │                                                           │
│       └─ Above threshold:                                         │
│            │                                                      │
│            ├─ AgentController decide → AgentAction                │
│            │   or                                                  │
│            ├─ Multi-Agent Orchestrator:                            │
│            │   OrchestratorAgent → specialist → ExecutionLayer     │
│            │                                                      │
│            ▼                                                      │
│       ExecutionLayer:                                              │
│         guardrails → state hash (before)                          │
│         dispatch → LocalRepair / PartialReplanner / AltGen        │
│         state hash (after) → log STATE_MUTATION                   │
│            │                                                      │
│            ▼                                                      │
│       PendingDecision → user approves/rejects                     │
│            │                                                      │
│            ▼                                                      │
│       resolve_pending() → state mutation                          │
│       DisruptionMemory updated                                    │
│       StructuredLogger records all events                         │
│            │                                                      │
│            ▼                                                      │
│       Updated itinerary → client sees new plan                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     POST-TRIP                                     │
│                                                                   │
│  Trip ends → itinerary marked "Completed"                         │
│       │                                                           │
│       ▼ (Backend)                                                 │
│  Memory Update (Stage 5):                                         │
│    LTM: update Wv weights via λ learning                          │
│    LTM: promote disruption patterns                               │
│    STM: clear session data                                        │
│       │                                                           │
│       ▼ (Observability)                                           │
│  Session logs available: python main.py --replay <session_id>     │
│  Replay verifies integrity via state hash comparison              │
│       │                                                           │
│       ▼ (Future trips)                                            │
│  Personalised weights influence next trip's scoring               │
│  Disruption patterns inform threshold derivation                  │
└──────────────────────────────────────────────────────────────────┘
```

### 9.2 CLI Entry Points Summary

| Command | Purpose |
|---|---|
| `python main.py` | Default pipeline (hardcoded constraints) |
| `python main.py --chat` | Chat intake (form HC + NLP SC) |
| `python main.py --reoptimize` | Pipeline + interactive re-optimizer |
| `python main.py --chat --reoptimize` | Full chat + re-optimizer |
| `python main.py --replay <session_id>` | Deterministic session replay |
| `python demo_reoptimizer.py` | Standalone re-optimizer demo |
| `python test_full_pipeline.py` | 8-part regression suite |

---

## Appendix A — Test Suite Coverage

| Part | Name | What It Verifies |
|---|---|---|
| 1 | Pipeline Runs | Stages 0–5 complete without error |
| 2 | Itinerary Structure | DayPlan count, RoutePoint fields, time ordering |
| 3 | FTRM Scores | S_pti > 0 for scheduled stops, HC gate correct |
| 4 | Budget Validation | Sum ≤ total, reserve ≥ 5%, category caps respected |
| 5 | Re-optimizer | Session init, condition checks, PendingDecision flow |
| 6 | LocalRepair | 8 invariants, meal scheduling, geographic bounds |
| 7 | Agent Controller | 6-rule chain, guardrails, state hashing |
| 8 | Multi-Agent | Orchestrator routing (8a-8k), specialist decisions, dispatcher pipeline |

All tests run via: `$env:USE_STUB_LLM="true"; python test_full_pipeline.py` → exit code 0.

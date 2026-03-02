# Multi-Agent Architecture — TravelAgent Re-Optimizer

> **14 files · 6 specialist agents · 1 orchestrator · deterministic dispatch pipeline**
> Last updated: 2025-07-24 (Phase 32)

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [System Overview](#2-system-overview)
3. [File Map](#3-file-map)
4. [Core Data Types](#4-core-data-types)
5. [Agent Hierarchy](#5-agent-hierarchy)
6. [Specialist Agents](#6-specialist-agents)
7. [AgentController (Legacy Rule Chain)](#7-agentcontroller-legacy-rule-chain)
8. [AgentDispatcher Pipeline](#8-agentdispatcher-pipeline)
9. [Execution Layer](#9-execution-layer)
10. [Alternative Generator](#10-alternative-generator)
11. [Inter-Agent Data Flow](#11-inter-agent-data-flow)
12. [Constants Reference](#12-constants-reference)

---

## 1. Design Principles

| Principle | Enforcement |
|---|---|
| **Deterministic** | Every agent is pure rules — zero LLM calls, zero randomness |
| **Read-only agents** | Agents NEVER mutate `TripState`. They emit `AgentAction` objects only |
| **Single mutator** | Only `ExecutionLayer` may apply state changes |
| **First-match wins** | Evaluation chains return on the first triggered rule |
| **Safety by schema** | `AgentAction` cannot represent multi-stop deletions, hotel/city changes, or budget mutations |
| **Composable** | Each specialist is a `BaseAgent` subclass with a single `evaluate()` entry point |

---

## 2. System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                    ReOptimizationSession                          │
│  (modules/reoptimization/session.py)                             │
│                                                                    │
│  ┌──────────────┐    AgentContext    ┌──────────────────────────┐  │
│  │ AgentController│ ──────────────→ │  AgentDispatcher          │  │
│  │ (legacy 6-rule │    (parallel)   │  ┌────────────────────┐   │  │
│  │  chain)        │                 │  │ OrchestratorAgent  │   │  │
│  └──────────────┘                   │  │  route() → agent   │   │  │
│                                      │  └────────┬───────────┘   │  │
│                                      │           │               │  │
│                                      │  ┌────────▼───────────┐   │  │
│                                      │  │ Specialist Agent   │   │  │
│                                      │  │  evaluate()→Action │   │  │
│                                      │  └────────┬───────────┘   │  │
│                                      │           │               │  │
│                                      │  ┌────────▼───────────┐   │  │
│                                      │  │ ExecutionLayer     │   │  │
│                                      │  │  execute()→Result  │   │  │
│                                      │  └────────────────────┘   │  │
│                                      └──────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

**Two decision paths coexist:**

| Path | Module | When Used |
|---|---|---|
| **Legacy** | `AgentController.evaluate()` | Direct 6-rule deterministic chain — takes action without user consultation |
| **Multi-Agent** | `AgentDispatcher.dispatch()` | Orchestrator routes to specialist — richer reasoning, advisory panels |

Both paths feed their resulting `AgentAction` into the same `ExecutionLayer`.

---

## 3. File Map

```
modules/reoptimization/
├── agent_action.py              ActionType enum + AgentAction dataclass
├── agent_controller.py          Legacy 6-rule decision chain + AgentObservation
├── execution_layer.py           State mutation + guardrails + state hashing
├── alternative_generator.py     7-criteria ranked replacement generator
│
├── agents/
│   ├── __init__.py              Package init — re-exports 11 symbols
│   ├── base_agent.py            BaseAgent ABC + AgentContext dataclass
│   ├── orchestrator_agent.py    3-phase routing → specialist selection
│   ├── disruption_agent.py      Weather / crowd / traffic classification
│   ├── planning_agent.py        Strategy selection (FULL_PLAN / LOCAL_REPAIR / REORDER)
│   ├── budget_agent.py          Spend ratio monitoring (OK / OVERRUN / UNDERUTILIZED)
│   ├── preference_agent.py      User preference extraction (pace / interests / tolerance)
│   ├── memory_agent.py          LTM / STM routing based on disruption count
│   ├── explanation_agent.py     4-sentence human-readable state explanation
│   └── agent_dispatcher.py      5-step end-to-end dispatch pipeline
```

---

## 4. Core Data Types

### 4.1 ActionType (Enum)

Defined in `agent_action.py`. Every agent emits exactly one of these.

| Member | Value | Semantics |
|---|---|---|
| `NO_ACTION` | `"NO_ACTION"` | Continue unchanged |
| `REQUEST_USER_DECISION` | `"REQUEST_USER_DECISION"` | Show alternatives, block until user decides |
| `DEFER_POI` | `"DEFER_POI"` | Temporarily remove POI from today's plan |
| `REPLACE_POI` | `"REPLACE_POI"` | Generate ranked alternatives for a POI |
| `RELAX_CONSTRAINT` | `"RELAX_CONSTRAINT"` | Loosen a soft constraint (e.g., travel time) |
| `REOPTIMIZE_DAY` | `"REOPTIMIZE_DAY"` | Bounded ACO re-run for the entire day |

### 4.2 AgentAction (Dataclass)

```python
@dataclass
class AgentAction:
    action_type: ActionType          # Required — one of the 6 types
    target_poi:  Optional[str]       # POI name (None for day-level actions)
    reasoning:   str = ""            # One-line deterministic explanation
    parameters:  dict = field({})    # KV context for ExecutionLayer
```

**Safety invariant:** Cannot represent multi-stop deletions, hotel changes, city changes, or budget mutations.

**Parameter examples by action type:**

| ActionType | Typical Parameters |
|---|---|
| `DEFER_POI` | `{"cause": "crowd", "crowd_level": 0.82}` |
| `REPLACE_POI` | `{"cause": "weather", "category_hint": "indoor"}` |
| `RELAX_CONSTRAINT` | `{"constraint": "max_travel_min", "old": 60, "new": 90}` |
| `REOPTIMIZE_DAY` | `{"deprioritize_outdoor": True}` |

### 4.3 AgentContext (Dataclass)

Passed to every specialist agent's `evaluate()`.

```python
@dataclass
class AgentContext:
    observation: AgentObservation     # Read-only snapshot of trip state
    event_type:  str = ""             # Triggering event keyword
    user_input:  str = ""             # Raw user text (if any)
    parameters:  dict = field({})     # Extra routing data
```

### 4.4 AgentObservation (Dataclass)

Built by `AgentController.observe()` — a read-only snapshot of the trip at decision time.

| Field | Type | Default | Description |
|---|---|---|---|
| `current_day_plan` | `Optional[DayPlan]` | `None` | Today's route |
| `remaining_stops` | `list[str]` | `[]` | Unvisited stops today |
| `current_time` | `str` | `"09:00"` | HH:MM |
| `current_lat` / `current_lon` | `float` | `0.0` | GPS position |
| `remaining_minutes` | `int` | `660` | Minutes left in day |
| `total_day_minutes` | `int` | `660` | Full day budget |
| `budget` | `Optional[BudgetAllocation]` | `None` | Allocated budget |
| `budget_spent` | `dict[str, float]` | `{}` | Category → amount spent |
| `crowd_level` | `Optional[float]` | `None` | 0.0–1.0 |
| `weather_condition` | `Optional[str]` | `None` | e.g. "rain", "clear" |
| `weather_severity` | `float` | `0.0` | 0.0–1.0 |
| `traffic_level` | `Optional[float]` | `None` | 0.0–1.0 |
| `traffic_delay_minutes` | `int` | `0` | Extra delay |
| `thresholds` | `Optional[ConditionThresholds]` | `None` | Derived from user prefs |
| `next_stop_name` | `str` | `""` | Name of upcoming POI |
| `next_stop_is_outdoor` | `bool` | `False` | Outdoor flag |
| `next_stop_spti_proxy` | `float` | `0.0` | S\_pti ≈ rating/5.0 |
| `avoid_crowds` | `bool` | `False` | User preference |
| `pace_preference` | `str` | `"moderate"` | relaxed / moderate / fast |
| `disruptions_today` | `int` | `0` | Count of disruptions |

---

## 5. Agent Hierarchy

### 5.1 BaseAgent (Abstract Base Class)

```python
class BaseAgent(ABC):
    AGENT_NAME:    str = "BaseAgent"
    SYSTEM_PROMPT: str = ""

    @abstractmethod
    def evaluate(self, context: AgentContext) -> AgentAction: ...
```

All 6 specialist agents inherit from `BaseAgent`.

### 5.2 OrchestratorAgent

**Purpose:** Routes an incoming `AgentContext` to the most appropriate specialist.

**Allowed agents:** `frozenset({"DisruptionAgent", "PlanningAgent", "BudgetAgent", "PreferenceAgent", "MemoryAgent", "ExplanationAgent"})`

**Event routing table (`_EVENT_ROUTING`):**

| Event Keywords | Target Agent |
|---|---|
| `crowd`, `weather`, `traffic` | `DisruptionAgent` |
| `budget` | `BudgetAgent` |
| `slower`, `faster`, `preference` | `PreferenceAgent` |
| `explain` | `ExplanationAgent` |
| `memory` | `MemoryAgent` |
| `plan`, `reoptimize` | `PlanningAgent` |

**`route(context) -> OrchestratorResult` — 3-phase algorithm:**

```
Phase 1 — Explicit match
  If context.event_type matches a key in _EVENT_ROUTING → return that agent.

Phase 2 — Auto-detect from observation
  Check observation thresholds in order:
    weather_severity > threshold  → DisruptionAgent
    crowd_level > threshold       → DisruptionAgent
    traffic_level > threshold     → DisruptionAgent
    disruptions_today ≥ 3        → PlanningAgent
    remaining_minutes ≤ 60       → PlanningAgent

Phase 3 — Fallback
  Return invoke_agent = "NONE" (no specialist needed).
```

**`OrchestratorResult` dataclass:**

| Field | Type | Description |
|---|---|---|
| `invoke_agent` | `str` | Agent name or `"NONE"` |
| `reason` | `str` | Human-readable routing explanation |

---

## 6. Specialist Agents

### 6.1 DisruptionAgent

**Purpose:** Classifies weather, crowd, and traffic disruptions by severity and recommends user-facing actions.

**Constants:**

| Constant | Value | Meaning |
|---|---|---|
| `HC_UNSAFE_WEATHER` | `0.75` | Weather severity at which HC gate blocks the stop |
| `HIGH_VALUE_CUTOFF` | `0.65` | S\_pti threshold — high-value stops get deferred, not replaced |
| `_HIGH_CROWD` | `0.85` | Crowd level considered "high" |
| `_HIGH_TRAFFIC` | `0.80` | Traffic level considered "high" |

**Action map:**

| Classification | Action |
|---|---|
| `IGNORE` | `NO_ACTION` |
| `ASK_USER` | `REQUEST_USER_DECISION` |
| `DEFER` | `DEFER_POI` |
| `REPLACE` | `REPLACE_POI` |

**`evaluate()` priority chain:** Weather → Crowd → Traffic (first breach wins).

**Classification methods:**

| Method | LOW | MEDIUM | HIGH |
|---|---|---|---|
| `_classify_weather(severity)` | < threshold | < 0.75 | ≥ 0.75 |
| `_classify_crowd(level)` | < threshold | < 0.85 | ≥ 0.85 |
| `_classify_traffic(level)` | < threshold | < 0.80 | ≥ 0.80 |

For MEDIUM and HIGH: always returns `REQUEST_USER_DECISION` (advisory — lets user decide).

**Key difference from AgentController:**
- DisruptionAgent → always `ASK_USER` for HIGH/MEDIUM (human in the loop)
- AgentController → directly `DEFER` or `REPLACE` based on S\_pti value (autonomous)

### 6.2 PlanningAgent

**Purpose:** Selects the optimal re-planning strategy based on disruption count and time pressure.

**Constants:**

| Constant | Value |
|---|---|
| `MULTI_DISRUPTION_TRIGGER` | `3` |
| `TIME_PRESSURE_MINUTES` | `60` |
| `SINGLE_DISRUPTION_REPAIR` | `1` |

**4-Rule strategy selection (first match wins):**

| # | Condition | Strategy | ActionType | Target |
|---|---|---|---|---|
| 1 | disruptions ≥ 3 | `FULL_PLAN` | `REOPTIMIZE_DAY` | Day |
| 2 | remaining ≤ 60 min AND stops > 1 | `REORDER` | `RELAX_CONSTRAINT` | Day |
| 3 | 1 ≤ disruptions ≤ 2 | `LOCAL_REPAIR` | `DEFER_POI` | POI |
| 4 | Otherwise | `NO_CHANGE` | `NO_ACTION` | POI |

When `FULL_PLAN` is selected, parameters include `deprioritize_outdoor: bool` (True if weather severity > 0.4).

### 6.3 BudgetAgent

**Purpose:** Monitors budget utilization and flags overruns or underutilization.

**Constants:**

| Constant | Value | Meaning |
|---|---|---|
| `OVERRUN_THRESHOLD` | `0.90` | Spend ratio triggering overrun alert |
| `UNDERUTILIZED_THRESHOLD` | `0.40` | Spend ratio considered underutilized |
| `TIME_PROGRESS_GATE` | `0.60` | Underutilization only flagged after 60% of day elapsed |

**Classification matrix:**

| spend\_ratio | time\_ratio | Status | Action | ActionType |
|---|---|---|---|---|
| ≥ 0.90 | any | `OVERRUN` | `SUGGEST_CHEAPER` | `REPLACE_POI` |
| ≤ 0.40 | ≥ 0.60 | `UNDERUTILIZED` | `REBALANCE` | `RELAX_CONSTRAINT` |
| otherwise | any | `OK` | `NO_CHANGE` | `NO_ACTION` |

**`evaluate()` output:** Returns `AgentAction` with parameters `{budget_status, action, variance_percentage}`.

### 6.4 PreferenceAgent

**Purpose:** Extracts and applies user preference changes (pace, interests, environmental tolerance).

**Pace mapping (`_PACE_MAP`):**

| Input | Normalized |
|---|---|
| `slower` | `relaxed` |
| `faster` | `fast` |
| `relaxed` | `relaxed` |
| `fast` | `fast` |
| `balanced` | `balanced` |

**Valid tolerance levels:** `frozenset({"low", "medium", "high"})`

**3 observation helpers (module-level):**

| Function | Logic |
|---|---|
| `_crowd_from_observation(obs)` | Returns `30` if `avoid_crowds` is True, else `None` |
| `_weather_from_observation(obs)` | Maps severity to condition string |
| `_traffic_from_observation(obs)` | Maps traffic level to descriptor |

**`evaluate()` decision:**
- If pace changed or new interests detected → `REOPTIMIZE_DAY`
- Otherwise → `NO_ACTION`

Returns parameters: `{interests, pace, env_tolerance}`.

### 6.5 MemoryAgent

**Purpose:** Routes disruption data to long-term or short-term memory based on frequency.

**Constants:**

| Constant | Value | Meaning |
|---|---|---|
| `_LONG_TERM_DISRUPTION_THRESHOLD` | `3` | ≥ 3 disruptions → LTM storage |
| `_SHORT_TERM_DISRUPTION_THRESHOLD` | `1` | 1–2 disruptions → STM storage |

**Decision logic:**

| disruptions\_today | Memory Type | Store? |
|---|---|---|
| ≥ 3 | `long_term` | Yes — "recurring pattern warrants long-term storage" |
| ≥ 1 | `short_term` | Yes — "noted in short-term memory" |
| 0 | `None` | No — "no disruptions; nothing to store" |

**Always returns `NO_ACTION`** — memory storage is a side-effect handled by the execution layer.

### 6.6 ExplanationAgent

**Purpose:** Generates a human-readable 2–4 sentence explanation of the current trip state via `_build_explanation()`.

**Sentence construction:**

| # | Content | Condition |
|---|---|---|
| 1 | Time + remaining minutes + stop count | Always |
| 2 | Next stop context (name, indoor/outdoor, S\_pti) | If `next_stop_name` exists |
| 3 | Environment (disruptions, crowd, weather, traffic) | Always |
| 4 | Budget snapshot ("X% spent") | If `total_budget > 0` and `total_spent > 0` |

**Always returns `NO_ACTION`** with `parameters: {"explanation": "..."}`.

---

## 7. AgentController (Legacy Rule Chain)

`agent_controller.py` — 428 lines. A monolithic 6-rule deterministic decision engine that runs in parallel with the multi-agent system.

### 7.1 Constants

| Constant | Value |
|---|---|
| `HC_UNSAFE_WEATHER_THRESHOLD` | `0.75` |
| `HIGH_VALUE_SPTI_CUTOFF` | `0.65` |
| `MULTI_DISRUPTION_TRIGGER` | `3` |
| `TIME_PRESSURE_MINUTES` | `60` |

### 7.2 `observe()` Method

Builds an `AgentObservation` from current `TripState`:
1. Finds next unvisited/unskipped/undeferred stop in `current_day_plan.route_points`
2. Looks up `AttractionRecord` for `is_outdoor` flag
3. Computes `next_spti = rating / 5.0` (clamped to [0, 1])
4. Resolves `weather_severity` from `WEATHER_SEVERITY[condition.lower()]`
5. Returns fully populated `AgentObservation`

### 7.3 `evaluate()` — 6-Rule Chain (First Match Wins)

| # | Rule | Condition | Action | Details |
|---|---|---|---|---|
| 1 | Weather unsafe | severity ≥ 0.75 + outdoor | `REPLACE_POI` | `category_hint="indoor"` |
| 1b | Weather moderate | severity > threshold + outdoor | `DEFER_POI` | Temporary exclusion |
| 2 | Crowd exceeded | crowd > threshold | S\_pti ≥ 0.65 → `DEFER_POI`; S\_pti < 0.65 → `REQUEST_USER_DECISION` |  |
| 3 | Traffic exceeded | traffic > threshold | S\_pti ≥ 0.65 → `DEFER_POI`; S\_pti < 0.65 → `REPLACE_POI` |  |
| 4 | Multi-disruption | disruptions ≥ 3 | `REOPTIMIZE_DAY` | `deprioritize_outdoor` if weather > 0.4 |
| 5 | Time pressure | remaining ≤ 60 min + stops > 1 | `RELAX_CONSTRAINT` | `max_travel_min` 60 → 120 |
| 6 | Default | none of the above | `NO_ACTION` |  |

### 7.4 AgentController vs Multi-Agent Comparison

| Aspect | AgentController | Multi-Agent (Orchestrator → Specialist) |
|---|---|---|
| Decision model | Single 6-rule chain | Routing + specialist evaluation |
| User consultation | Only on crowd (low S\_pti) | DisruptionAgent always asks for MEDIUM/HIGH |
| Planning strategy | One-size-fits-all REOPTIMIZE | PlanningAgent selects FULL\_PLAN / LOCAL\_REPAIR / REORDER |
| Budget awareness | None | BudgetAgent monitors spend ratio |
| Preference changes | None | PreferenceAgent tracks pace / interests |
| Memory routing | None | MemoryAgent routes to LTM / STM |
| Explanations | None | ExplanationAgent builds 4-sentence output |
| Extensibility | Add rules to monolith | Add new specialist agent |

---

## 8. AgentDispatcher Pipeline

`agents/agent_dispatcher.py` — Owns no state. Orchestrates the full evaluate → execute cycle.

### 8.1 DispatchResult

```python
class DispatchResult:
    __slots__ = ("routing", "specialist_name", "action", "execution_result")
```

| Field | Type |
|---|---|
| `routing` | `OrchestratorResult` |
| `specialist_name` | `str` |
| `action` | `AgentAction` |
| `execution_result` | `ExecutionResult` |

### 8.2 5-Step Pipeline

```
Step 1: Route
  orchestrator.route(context) → OrchestratorResult
  Prints: [Orchestrator] → AgentName (reason)

Step 2: Lookup
  specialists[routing.invoke_agent] → specialist
  If routing = "NONE" → return DispatchResult(NO_ACTION, specialist="NONE")

Step 3: Evaluate
  specialist.evaluate(context) → AgentAction
  Prints: [AgentName] action_type

Step 4: Execute
  execution_layer.execute(action, state, remaining, constraints, budget, restaurant_pool)
  → ExecutionResult

Step 5: Log
  stm.log_interaction("orchestrator_dispatch", {routing, action, result})
```

### 8.3 Constructor

```python
AgentDispatcher(
    orchestrator:    OrchestratorAgent,
    specialists:     dict[str, BaseAgent],   # name → agent instance
    execution_layer: ExecutionLayer,
    stm:             ShortTermMemory,
)
```

---

## 9. Execution Layer

`execution_layer.py` — The **ONLY** component that may mutate itinerary state.

### 9.1 Safety Guardrails

**Forbidden parameter keys** (`_FORBIDDEN_PARAM_KEYS`):

```python
frozenset({"change_hotel", "change_city", "modify_budget", "delete_multiple", "override_hc"})
```

**Guardrail checks (`_check_guardrails`):**

| Rule | Check | Violation |
|---|---|---|
| Multi-target | `parameters["targets"]` is list with len > 1 | "Cannot delete multiple stops in one action" |
| Forbidden keys | Any key in `_FORBIDDEN_PARAM_KEYS` present | "Forbidden parameter: {key}" |

Violation → `SafetyViolation(RuntimeError)` logged to STM, `ExecutionResult(executed=False, error=...)`.

### 9.2 State Hashing

`compute_state_hash(state: TripState) -> str`

- Deterministic SHA-256 of all mutable TripState fields
- Excludes transient fields: `frozenset({"current_day_plan", "replan_pending"})`
- Converts `set` → `sorted(set)` for determinism
- Logged as `before_hash` / `after_hash` on every state mutation

### 9.3 Dispatch Map

| ActionType | Handler | Behavior |
|---|---|---|
| `NO_ACTION` | `_exec_no_action` | Returns `ExecutionResult(executed=True)` — noop |
| `REQUEST_USER_DECISION` | `_exec_request_user` | Filters candidates, calls `AlternativeGenerator.generate()` with 5 alternatives |
| `DEFER_POI` | `_exec_defer` | `state.defer_stop(poi)` → `LocalRepair.repair()` → updates `state.current_day_plan` |
| `REPLACE_POI` | `_exec_replace` | Same as `REQUEST_USER_DECISION` with `category_hint` from params |
| `RELAX_CONSTRAINT` | `_exec_relax` | Reads `constraint/new/old` from params. Does NOT touch budget or HCs |
| `REOPTIMIZE_DAY` | `_exec_reoptimize` | `PartialReplanner.replan()` → updates `state.current_day_plan`, clears `replan_pending` |

### 9.4 ExecutionResult

```python
class ExecutionResult:
    __slots__ = ("action", "executed", "new_plan", "alternatives",
                 "relaxed_constraint", "error")
```

| Field | Type | Default | Description |
|---|---|---|---|
| `action` | `AgentAction` | *required* | The action that was executed |
| `executed` | `bool` | `True` | Whether execution succeeded |
| `new_plan` | `Optional[DayPlan]` | `None` | Replacement day plan (if replanned) |
| `alternatives` | `list[AlternativeOption]` | `[]` | Ranked alternatives (if generated) |
| `relaxed_constraint` | `dict \| None` | `None` | Which constraint was relaxed |
| `error` | `str` | `""` | Error message if failed |

---

## 10. Alternative Generator

`alternative_generator.py` — 419 lines. Context-aware replacement generator using 7-criteria composite scoring. Read-only — does NOT mutate the schedule.

### 10.1 AlternativeOption (Dataclass)

| Field | Type | Description |
|---|---|---|
| `rank` | `int` | 1-based display rank |
| `name` | `str` | Attraction / restaurant name |
| `category` | `str` | e.g. "Historical", "Park", "Restaurant (Italian)" |
| `distance_km` | `float` | Haversine from current position |
| `travel_time_min` | `int` | Transit minutes (at 25 km/h) |
| `expected_duration_min` | `int` | Visit/meal duration (default: 60 min) |
| `why_suitable` | `str` | One-line human-readable reason |
| `historical_summary` | `str` | Cultural/historical brief |
| `predicted_crowd` | `float` | 0.0–1.0 |
| `ftrm_score` | `float` | η\_ij = S\_pti / D\_ij proxy |
| `composite_score` | `float` | Final 7-criteria weighted score |
| `is_meal_option` | `bool` | True if restaurant alternative |

### 10.2 Scoring Weights (Sum = 1.0)

| Weight | Value | Criterion |
|---|---|---|
| `_W_DISTANCE` | 0.25 | Proximity — linear decay to 0 at 5 km |
| `_W_CROWD` | 0.20 | Inverse crowd level |
| `_W_CATEGORY` | 0.15 | Category match (exact=1.0, partial=0.5, none=0.2) |
| `_W_WEATHER` | 0.15 | Weather suitability (indoor in rain=1.0, outdoor in rain=0.1) |
| `_W_TIMING` | 0.10 | Open/closed status |
| `_W_FTRM` | 0.10 | ACO η\_ij proxy: `min(1, (rating/5) / (dist/5))` |
| `_W_MEAL` | 0.05 | Meal window bonus |

### 10.3 Scoring Functions

| Method | Formula |
|---|---|
| `_score_distance(d)` | `max(0, 1 - d / 5.0)` |
| `_score_category(cand, disrupted)` | Exact → 1.0, substring → 0.5, else → 0.2 |
| `_score_crowd(name, forecast)` | `1 - crowd_level` (default 0.4 if unknown) |
| `_score_weather(outdoor, weather)` | outdoor + bad → 0.1, indoor + bad → 1.0, else → 0.8 |
| `_score_timing(time, hours)` | Within hours → 1.0, closed → 0.0, unknown → 0.8 |
| `_score_ftrm(rating, dist)` | `min(1.0, (rating/5) / max(0.01, dist/5))` |

### 10.4 Generation Pipeline

```
generate(disrupted_poi, disrupted_category, candidates, restaurant_pool, context)

1. For each attraction candidate:
   ├── Haversine distance from (current_lat, current_lon)
   ├── Hard filter: distance > 5.0 km → skip
   ├── Compute 7 criterion scores
   ├── Composite = Σ (weight × score)
   └── Build AlternativeOption (meal_score = 0)

2. If in meal window AND restaurant_pool provided:
   ├── For each restaurant:
   │   ├── Same distance filter + 7 criteria
   │   ├── s_cat = 0.5, s_weather = 1.0 (indoor), s_meal = 1.0
   │   └── Category = "Restaurant (cuisine)"
   └── Merge with attraction candidates

3. Sort all by composite score (descending)
4. Take top N (default: 5)
5. Assign 1-based ranks
```

### 10.5 Helper Methods

| Method | Purpose |
|---|---|
| `_in_meal_window(time, lunch, dinner)` | True if time falls in `("12:00","14:00")` or `("19:00","21:00")` |
| `_get_historical_summary(name)` | Calls `HistoricalInsightTool` — returns `""` on failure |
| `_why_suitable(...)` | Builds reason: "very close by" (<1km), "low crowd expected" (>0.7), "indoor—weather safe", etc. |
| `_haversine(lat1, lon1, lat2, lon2)` | Great-circle distance in km (R=6371) |
| `_travel_time(dist)` | `max(5, int((dist / 25) * 60))` |

---

## 11. Inter-Agent Data Flow

### 11.1 Dependency Graph

```
agent_action.py                  ← LEAF (no internal deps)
    ActionType, AgentAction
        │
        ▼
agent_controller.py              ← AgentObservation + 6-rule evaluate()
    uses: agent_action, trip_state, condition_monitor,
          disruption_memory, short_term_memory, weather/traffic tools
        │
        ▼
agents/base_agent.py             ← BaseAgent ABC + AgentContext
    uses: AgentAction, AgentObservation
        │
        ├── orchestrator_agent.py
        ├── disruption_agent.py
        ├── planning_agent.py
        ├── budget_agent.py
        ├── preference_agent.py
        ├── memory_agent.py
        └── explanation_agent.py
        │
        ▼
agents/agent_dispatcher.py       ← 5-step pipeline
    uses: OrchestratorAgent, all specialists,
          ExecutionLayer, ShortTermMemory
        │
        ▼
execution_layer.py               ← State mutator + guardrails
    uses: LocalRepair, PartialReplanner,
          AlternativeGenerator, ShortTermMemory
        │
        ▼
alternative_generator.py         ← 7-criteria scorer (no internal deps)
```

### 11.2 Typical Request Flow

```
User command (e.g., "crowd 85")
  │
  ▼
ReOptimizationSession.check_conditions(crowd_level=0.85)
  │
  ├─── AgentController.observe() → AgentObservation
  ├─── AgentController.evaluate(obs) → AgentAction [legacy path]
  │
  ├─── Build AgentContext(observation=obs, event_type="crowd")
  ├─── AgentDispatcher.dispatch(context, state, ...) [multi-agent path]
  │       │
  │       ├── OrchestratorAgent.route(context) → "DisruptionAgent"
  │       ├── DisruptionAgent.evaluate(context) → REQUEST_USER_DECISION
  │       ├── ExecutionLayer.execute(action, ...) → alternatives list
  │       └── Return DispatchResult
  │
  ▼
Session creates PendingDecision with alternatives
User must: approve / reject / modify <n>
```

---

## 12. Constants Reference

### 12.1 Threshold Constants

| Constant | File | Value | Used For |
|---|---|---|---|
| `HC_UNSAFE_WEATHER_THRESHOLD` | `agent_controller.py` | `0.75` | HC gate — blocks outdoor stop |
| `HC_UNSAFE_WEATHER` | `disruption_agent.py` | `0.75` | Same gate in multi-agent path |
| `HIGH_VALUE_SPTI_CUTOFF` | `agent_controller.py` | `0.65` | High-value → DEFER; low-value → REPLACE |
| `HIGH_VALUE_CUTOFF` | `disruption_agent.py` | `0.65` | Same cutoff in multi-agent path |
| `_HIGH_CROWD` | `disruption_agent.py` | `0.85` | Crowd classified as HIGH |
| `_HIGH_TRAFFIC` | `disruption_agent.py` | `0.80` | Traffic classified as HIGH |
| `MULTI_DISRUPTION_TRIGGER` | Both | `3` | Triggers full-day reoptimization |
| `TIME_PRESSURE_MINUTES` | Both | `60` | Remaining time triggers constraint relaxation |

### 12.2 Budget Constants

| Constant | File | Value |
|---|---|---|
| `OVERRUN_THRESHOLD` | `budget_agent.py` | `0.90` |
| `UNDERUTILIZED_THRESHOLD` | `budget_agent.py` | `0.40` |
| `TIME_PROGRESS_GATE` | `budget_agent.py` | `0.60` |

### 12.3 Memory Constants

| Constant | File | Value |
|---|---|---|
| `_LONG_TERM_DISRUPTION_THRESHOLD` | `memory_agent.py` | `3` |
| `_SHORT_TERM_DISRUPTION_THRESHOLD` | `memory_agent.py` | `1` |

### 12.4 Alternative Generator Constants

| Constant | File | Value |
|---|---|---|
| `_MAX_DISTANCE_KM` | `alternative_generator.py` | `5.0` |
| `_AVG_SPEED_KMPH` | `alternative_generator.py` | `25.0` |
| `_DEFAULT_DURATION` | `alternative_generator.py` | `60` |
| Weights (7) | `alternative_generator.py` | Sum = 1.0 (see §10.2) |

### 12.5 Safety Constants

| Constant | File | Value |
|---|---|---|
| `_FORBIDDEN_PARAM_KEYS` | `execution_layer.py` | 5 keys (see §9.1) |
| `_TRANSIENT_FIELDS` | `execution_layer.py` | `{"current_day_plan", "replan_pending"}` |

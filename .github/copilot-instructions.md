# Copilot Instructions — Travel Itinerary Optimizer

## Project Overview
Python travel planner that converts a natural-language chat into a multi-day
itinerary. Uses the FTRM mathematical model + ACO route optimization.
All external APIs are stubbed by default (`USE_STUB_LLM=true` in `config.py`).

---

## Running & Testing
```powershell
# Run the full end-to-end test (5 parts, exit 0 = pass)
$env:PYTHONUTF8="1"; & ".venv\Scripts\python.exe" test_full_pipeline.py

# LLM stub mode (default — no API key needed)
$env:USE_STUB_LLM="true"

# Use real Gemini (requires LLM_API_KEY)
$env:USE_STUB_LLM="false"; $env:LLM_API_KEY="..."
```
Never run bare `python` — always use `.venv\Scripts\python.exe`.

---

## Pipeline Stages (main.py → 5 stages)
| Stage | Module | Output |
|---|---|---|
| 1 — Chat Intake | `modules/input/chat_intake.py` | `ConstraintBundle` |
| 2 — Budget Planning | `modules/planning/budget_planner.py` | `BudgetAllocation` |
| 3 — Recommendation | `modules/recommendation/` | ranked `AttractionRecord` list |
| 4 — Route Planning | `modules/planning/route_planner.py` + ACO | `Itinerary` |
| 5 — Memory Update | `modules/memory/` | persisted preferences |
| 6 — Re-optimization | `modules/reoptimization/` (runtime) | updated `DayPlan` |

---

## FTRM Equations (use these variable names everywhere)
```
HC_pti = Π hcm          (Eq 1)  — 0 if ANY hard constraint violated
SC_pti = Σ Wv × scv     (Eq 2)  — SC weights: [0.25,0.20,0.30,0.15,0.10]
S_pti  = HC_pti × SC_pti (Eq 4) — composite score [0,1]
η_ij   = S_pti / Dij    (Eq 12) — ACO heuristic
P_ij   = τ^α × η^β / Σ  (Eq 13) — ACO transition probability
```
All times (`Dij`, `STi`, `Tmax`) are **minutes**. Scores are **[0, 1]**.

---

## Re-optimization Architecture (Stage 6)
Entry point: `ReOptimizationSession` in `modules/reoptimization/session.py`

**Event routing in `session.event()` and `session.check_conditions()`:**
- `crowd_action` metadata → `_handle_crowd_action()` → 3-strategy tree
- `weather_action` metadata → `_handle_weather_action()` → `WeatherAdvisor`
- `traffic_action` metadata → `_handle_traffic_action()` → `TrafficAdvisor`
- else → `_do_replan()`

**Three crowd strategies (event_handler.py `_handle_env_crowd`):**
1. `reschedule_same_day` — defer + replan + un-defer (enough time today)
2. `reschedule_future_day` — move to `current_day + 1`
3. `inform_user` — HC cannot save it; show advisory; user decides

**Advisory panel rules:**
- `WHAT YOU WILL MISS` — shown ONLY for `inform_user` / `USER_SKIP`
- `BEST ALTERNATIVES` — shown for all 3 strategies
- `YOUR CHOICE` — shown ONLY for `inform_user`

**Weather — two severity thresholds:**
```
severity > WeatherThreshold (user-derived) → disruption triggered
severity ≥ HC_UNSAFE_THRESHOLD (0.75)      → HC_pti = 0, stop BLOCKED
threshold ≤ severity < 0.75               → stop DEFERRED, duration ×0.75
```

**Traffic — defer vs replace:**
```
Dij_new = Dij_base × (1 + traffic_level)
S_pti ≥ 0.65  →  DEFER  (high value — keep for later)
S_pti <  0.65  →  REPLACE (low value — swap for nearby alternative)
η_ij_new = S_pti / Dij_new   (updated ACO heuristic)
```

---

## Key Conventions
- **`AttractionRecord.historical_importance`** — rich text string; primary
  source for `HistoricalInsightTool`; set it on all stub attractions.
- **Deferred ≠ Skipped**: `state.deferred_stops` is a temporary exclusion set;
  `state.skipped_stops` is permanent. `undefer_stop()` re-admits to pool.
- **`PartialReplanner.replan()`** always filters `visited | skipped | deferred`
  before delegating to `RoutePlanner._plan_single_day()`.
- **`DisruptionMemory`** (`modules/memory/disruption_memory.py`) is updated
  after every weather/traffic event and surfaced via `session.summary()`.
- **Threshold derivation** lives in `ConditionMonitor._derive_thresholds()` —
  never hard-code crowd/traffic/weather thresholds; always derive from
  `SoftConstraints`.

---

## File Map for New Features
| Concern | File |
|---|---|
| New disruption type | `event_handler.py` + new `*_advisor.py` |
| New HC constraint | `constraint_registry.py` + `AttractionRecord` field |
| New SC dimension | `attraction_scoring.py` + weights list |
| Historical/cultural text | `historical_tool.py` (priority: record → LLM → stub) |
| Memory persistence | `disruption_memory.py` `.serialize()` / `.deserialize()` |

---

## ACO Defaults (config.py)
`α=2.0 β=3.0 ρ=0.1 Q=1.0 τ_init=1.0 num_ants=20 iterations=100`
SC aggregation: `"sum"` | Pheromone strategy: `"best_ant"`

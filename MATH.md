# Mathematical Formulas — Travel Itinerary Optimizer

This document catalogues every mathematical formula, equation, and quantitative rule
used across all modules. All times are in **minutes** unless otherwise stated.
All scores are in **[0, 1]** unless otherwise stated.
All monetary amounts are in **INR (Indian Rupee)**.

---

## 1. FTRM Satisfaction Chain

The FTRM (Flexible Traveller Requirement Model) produces a single satisfaction score
$S_{pti} \in [0,1]$ for placing attraction $p$ in time-slot $t$ of itinerary $i$.

### Eq 1 — Hard Constraint Gate

$$
HC_{pti} = \prod_{m} hc_{m,pti}, \quad hc_m \in \{0, 1\}
$$

$HC_{pti} = 0$ if **any** hard constraint is violated; $HC_{pti} = 1$ otherwise.

Active hard constraints (`constraint_registry.py`):

| ID  | Description |
|-----|-------------|
| hc1 | Opening-hours gate (attraction open at planned arrival) |
| hc2 | Time-budget feasibility: $elapsed + D_{ij} + ST_j \leq T_{max}$ |
| hc3 | Wheelchair accessibility |
| hc4 | Minimum visit duration: $remaining \geq D_{ij} + ST_{min}$ |

---

### Eq 2 — Soft Constraint Aggregation

Four supported aggregation methods (selected via `config.SC_AGGREGATION_METHOD`):

**Sum (default):**
$$
SC_{pti} = \sum_{v} W_v \cdot sc_{v,pti}
$$

**Least-misery:**
$$
SC_{pti} = \min_{v}(sc_{v,pti})
$$

**Most-pleasure:**
$$
SC_{pti} = \max_{v}(sc_{v,pti})
$$

**Multiplicative:**
$$
SC_{pti} = \prod_{v} sc_{v,pti}^{W_v}
$$

---

### Eq 3 — Weight Normalization

$$
\sum_{v} W_v = 1, \quad W_v \geq 0
$$

---

### Eq 4 — Unified Satisfaction Score

$$
S_{pti} = HC_{pti} \times SC_{pti} \in [0, 1]
$$

If any hard constraint fails, $HC_{pti} = 0$ forces $S_{pti} = 0$ regardless of soft scores.

---

## 2. Soft Constraint Dimensions (SC Weights)

Three API-verified SC dimensions (`attraction_scoring.py`):

| Dim | Weight $W_v$ | Source | Formula |
|-----|-------------|--------|---------|
| $SC_r$ — Rating quality | 0.40 | `attraction.rating` | $SC_r = rating / 5.0$ |
| $SC_p$ — Interest/category match | 0.35 | `user.interests` | $SC_p = 1.0$ if category $\in$ interests, else $0.5$ |
| $SC_o$ — Outdoor preference | 0.25 | `is_outdoor`, pace | $SC_o \in \{0.2, 0.5, 0.8, 1.0\}$ (see below) |

**$SC_o$ derivation:**

$$
SC_o = \begin{cases}
1.0 & \text{if outdoor and } pace = \text{relaxed} \\
0.8 & \text{if outdoor and } pace = \text{moderate/packed but avoid\_crowds} \\
0.5 & \text{if outdoor and } pace = \text{packed} \\
0.2 & \text{if indoor and } avoid\_crowds = \text{True} \\
0.5 & \text{otherwise}
\end{cases}
$$

Full expansion:
$$
SC_{pti} = 0.40 \cdot SC_r + 0.35 \cdot SC_p + 0.25 \cdot SC_o
$$

---

## 3. ACO Route Optimization

The Ant Colony Optimization solver (`aco_optimizer.py`) finds the highest-satisfaction
feasible day-route over the set of remaining attractions.

### Eq 8 — Visit-Once Constraint

$$
j \notin visited_k \quad \text{for all ant } k
$$

Implemented via `AntState.visited` set; pooled attractions are removed after each day.

---

### Eq 9 — Path Continuity

$$
\text{Each step extends from } current\_node \text{ (implicit in AntState)}
$$

---

### Eq 10 — Time Budget (T_max Feasibility)

$$
elapsed + D_{ij} + ST_j \leq T_{max}
$$

| Symbol | Meaning | Default |
|--------|---------|---------|
| $elapsed$ | Minutes used so far today | — |
| $D_{ij}$ | Travel time from node $i$ to $j$ (minutes) | — |
| $ST_j$ | Visit duration at node $j$ (minutes) | — |
| $T_{max}$ | Daily time budget (minutes) | **660 min** (09:00 → 20:00) |

---

### Eq 11 — ACO Objective Function

$$
\max \sum_{j \in path} S_{pti}(j) \times ST_j
$$

Accumulated in `AntState.total_satisfaction` during tour construction.

---

### Eq 12 — ACO Heuristic Desirability

$$
\eta_{ij} = \frac{S_{pti}(j)}{D_{ij}}, \quad \eta_{ij} \leq \eta_{max} = 10^6 \text{ (cap when } D_{ij} = 0\text{)}
$$

Precomputed once per day; static across all iterations (`aco_optimizer.py`).

---

### Eq 13 — Transition Probability

$$
P_{ij} = \frac{\tau_{ij}^{\alpha} \cdot \eta_{ij}^{\beta}}
              {\displaystyle\sum_{k \in \text{feasible}(i)} \tau_{ik}^{\alpha} \cdot \eta_{ik}^{\beta}}
$$

Roulette-wheel selection over feasible neighbours.

**Default parameters** (`config.py`):

| Param | Symbol | Default |
|-------|--------|---------|
| Pheromone exponent | $\alpha$ | **2.0** |
| Heuristic exponent | $\beta$ | **3.0** |
| Evaporation rate | $\rho$ | **0.1** |
| Pheromone deposit factor | $Q$ | **1.0** |
| Initial pheromone | $\tau_{init}$ | **1.0** |
| Ants per iteration | — | **20** |
| Iterations | — | **100** |

---

### Eq 14 — Pheromone Deposit per Ant

$$
\delta_{ij} = \begin{cases}
Q / L_k & \text{if edge } (i,j) \in \text{path of ant } k \\
0 & \text{otherwise}
\end{cases}
$$

$L_k$ = `tour.total_cost` (total travel minutes; lower cost → higher deposit).

---

### Eq 15 — Local Pheromone Update (all-ants strategy)

$$
\tau_{ij} \leftarrow (1 - \rho)\,\tau_{ij} + \delta_{ij}
$$

Applied per ant after each tour construction.

---

### Eq 16 — Global Pheromone Update (best-ant strategy, default)

$$
\tau_{ij} \leftarrow \rho\,\tau_{ij} + (1 - \rho)\,\delta_{ij}
$$

Applied once per iteration using **only the best tour** found so far.
This reduces noise vs the all-ants update and is the default (`pheromone_update_strategy = "best_ant"`).

---

## 4. LocalRepair Engine (§1–§7)

The `LocalRepair` class (`reoptimization/local_repair.py`) performs single-POI
minimal-change schedule surgery after a disruption event.

### §4 — Timing Rule

$$
arr_i = dep_{i-1} + travel_{i-1,i} + BUFFER
$$
$$
dep_i = arr_i + ST_i
$$

| Constant | Value | Meaning |
|----------|-------|---------|
| BUFFER | **10 min** | Transition buffer between consecutive stops |
| MAX\_GAP | **90 min** | Maximum idle gap warning threshold |
| Day-end hard cutoff | **20:55** | No arrival permitted after this |

---

### §5 — Crowd Decay (Exponential Model)

$$
crowd_{est}(t + \Delta t) = crowd_0 \cdot \left(1 - 0.15\right)^{\Delta t / 30}
$$

| Symbol | Meaning |
|--------|---------|
| $crowd_0$ | Crowd level at disruption time |
| $\Delta t$ | Delay in minutes from disruption |
| $0.15$ | `CROWD_DECAY_PER_30MIN` — 15 % decay per 30-minute window |

Used in `_try_shift()` to estimate whether deferring a stop by $\Delta t$ minutes
will bring the crowd level below the user's threshold.

---

### §6 — Replacement Candidate Ranking (ACO-style)

$$
\eta_{candidate} = \frac{rating / 5.0}{D_{ij}}
$$

Candidates within `MAX_REPLACE_RADIUS_KM = 3.0 km` are ranked by $\eta$.
Same-category candidates are preferred with a bonus multiplier.

---

### §3 — Meal Scheduling Constraints

| Rule | Formula |
|------|---------|
| Lunch window | arrival $\in [720, 870]$ min i.e. 12:00–14:30 |
| Dinner window | arrival $\in [1110, 1290]$ min i.e. 18:30–21:30 |
| Post-meal gap | $arr_{meal} \geq dep_{prev} + 60$ min |
| Exactly one lunch, one dinner per day | invariant enforced by `_validate_and_fix_meals()` |
| No back-to-back meals | two meals may not be consecutive stops |

---

### §1 — LocalRepair Invariant 8 (Cluster Radius)

$$
haversine(disrupted, alternative) \leq 5.0\text{ km}
$$

Ensures replacement stops remain geographically local.

---

## 5. Re-optimization — Condition Thresholds

Derived from `SoftConstraints` in `ConditionMonitor._derive_thresholds()`.
Never hard-coded; always user-personalised. All comparisons use **≥ (greater-than-or-equal)** —
a reading equal to the threshold triggers the disruption.

### Crowd Threshold

$$
\theta_{crowd} = \begin{cases}
0.35 & avoid\_crowds = \text{True} \\
0.70 & avoid\_crowds = \text{False}
\end{cases}
\quad \text{clamped to } [0.15,\; 0.90]
$$

**Trigger condition**: disruption fires when $crowd\_level \geq \theta_{crowd}$.

> **Note**: `heavy_travel_penalty` does **not** affect the crowd threshold.
> It only reduces the **traffic** threshold (see below). Crowd sensitivity
> is controlled solely by `avoid_crowds`.

---

### Traffic Threshold

$$
\theta_{traffic,base} = \begin{cases}
0.30 & pace\_preference = \text{``relaxed''} \\
0.55 & pace\_preference = \text{``moderate''} \\
0.80 & pace\_preference = \text{``packed''}
\end{cases}
$$

$$
\theta_{traffic} = \begin{cases}
\theta_{traffic,base} \times 0.80 & heavy\_travel\_penalty = \text{True} \\
\theta_{traffic,base} & \text{otherwise}
\end{cases}
\quad \text{clamped to } [0.15,\; 0.90]
$$

**Trigger condition**: disruption fires when $traffic\_level \geq \theta_{traffic}$.

---

### Weather Threshold

$$
outdoor\_ratio = \frac{\text{outdoor stops remaining}}{\text{total stops remaining}}
$$

$$
\theta_{weather,base} = \begin{cases}
0.40 & outdoor\_ratio > 0.5 \\
0.65 & \text{otherwise}
\end{cases}
$$

$$
\theta_{weather} = \begin{cases}
\theta_{weather,base} \times 0.85 & preferred\_time\_of\_day = \text{``morning''} \\
\theta_{weather,base} & \text{otherwise}
\end{cases}
\quad \text{clamped to } [0.15,\; 0.90]
$$

**Trigger condition**: disruption fires when $severity \geq \theta_{weather}$.

---

## 6. Re-optimization — Weather Disruption

Two distinct thresholds govern how weather affects a stop.

$$
\text{UserThreshold} = \theta_{weather} \quad \text{(derived above)}
$$
$$
\text{HC\_UNSAFE\_THRESHOLD} = 0.75 \quad \text{(hard-coded safety limit)}
$$

| Condition | Effect |
|-----------|--------|
| $severity \geq 0.75$ | $HC_{pti} = 0$ → stop **BLOCKED** |
| $\theta_{weather} \leq severity < 0.75$ | stop **DEFERRED**; $ST \leftarrow ST \times 0.75$ |
| $severity < \theta_{weather}$ | no action |

**Weather severity mapping** (`WEATHER_SEVERITY` dict — 17 entries):

| Condition | Severity | Condition | Severity |
|-----------|----------|-----------|----------|
| clear | 0.00 | mostly\_clear | 0.10 |
| cloudy | 0.30 | cold | 0.30 |
| hot | 0.35 | fog / foggy | 0.40 |
| overcast | 0.45 | drizzle | 0.55 |
| rainy | 0.65 | heatwave | 0.65 |
| snow | 0.70 | heavy\_rain | 0.80 |
| thunderstorm | 0.90 | stormy / hail / blizzard | 1.00 |

**CLI input validation** (`_VALID_WEATHER_CONDITIONS` in `main.py`):

$$
\text{accepted} \in \{\text{clear},\, \text{rainy},\, \text{stormy},\, \text{hot},\, \text{cold},\, \text{fog}\}
$$

The CLI whitelist is a strict subset of the 17 severity-mapped conditions. Invalid
conditions are rejected before reaching `ConditionMonitor`.

---

## 7. Re-optimization — Traffic Disruption

$$
D_{ij,new} = D_{ij,base} \times (1 + traffic\_level)
$$

$$
\eta_{ij,new} = \frac{S_{pti}}{D_{ij,new}}
$$

Decision rule:

$$
\text{action} = \begin{cases}
\text{DEFER} & S_{pti} \geq 0.65 \quad \text{(high-value — keep for later)} \\
\text{REPLACE} & S_{pti} < 0.65 \quad \text{(low-value — swap for nearby alternative)}
\end{cases}
$$

---

## 8. Re-optimization — Hunger & Fatigue Disruption

All state tracked in `TripState`; logic in `hunger_fatigue_advisor.py`.

### State Variables

| Variable | Range | Meaning |
|---|---|---|
| $hunger$ | $[0, 1]$ | 0 = satiated, 1 = urgent need to eat |
| $fatigue$ | $[0, 1]$ | 0 = fresh, 1 = exhausted |

---

### Accumulation Equations

$$
hunger \leftarrow \min\!\left(1,\; hunger + \Delta T \times r_{hunger}\right)
$$

$$
fatigue \leftarrow \min\!\left(1,\; fatigue + \Delta T \times r_{fatigue} \times m_{effort}\right)
$$

| Symbol | Value | Meaning |
|---|---|---|
| $r_{hunger}$ | $1/180$ min$^{-1}$ | Hunger rate — reaches 1.0 in 3 h without a meal |
| $r_{fatigue}$ | $1/420$ min$^{-1}$ | Fatigue rate — reaches 1.0 in 7 h of continuous activity |
| $m_{effort}$ | 1.8 / 1.3 / 1.0 | High / medium / low intensity multiplier |
| $\Delta T$ | minutes | Time elapsed since last meal (hunger) or since last rest (fatigue) |

---

### Trigger Thresholds

$$
\text{fire HUNGER\_DISRUPTION if } hunger \geq 0.70
$$

$$
\text{fire FATIGUE\_DISRUPTION if } fatigue \geq 0.75
$$

Three trigger mechanisms (applied on every `advance_to_stop`):
1. **Deterministic** — time × effort accumulation above.
2. **NLP** — keyword match in free-text forces floor: $hunger \geq 0.72$, $fatigue \geq 0.78$.
3. **Behavioural** — skipping a high-intensity stop: $fatigue \mathrel{+}= 0.10$; pace → relaxed: $fatigue \mathrel{+}= 0.08$.

---

### SC5 Penalty Injection (Impact on FTRM Score)

When hunger or fatigue is active, the wellness dimension $sc_5$ is penalised before scoring:

$$
sc_{5,adj} = \max\!\left(0,\; sc_{5,base} - P_{hunger} - P_{fatigue}\right)
$$

| Condition | Penalty applied |
|---|---|
| Hungry, stop duration $\geq 90$ min | $P_{hunger} = 0.40$ |
| Hungry, stop duration $< 90$ min | $P_{hunger} = 0.10$ |
| Fatigued, high-intensity stop | $P_{fatigue} = 0.50$ |
| Fatigued, medium-intensity stop | $P_{fatigue} = 0.20$ |
| Restaurant record while hungry | $sc_{5,adj} \mathrel{+}= 0.30$ (bonus, not penalty) |

The adjusted score feeds the standard FTRM chain:

$$
SC_{pti,adj} = \sum_v W_v \cdot sc_{v,adj} \qquad (\text{Eq 2 variant, } sc_5 := sc_{5,adj})
$$

$$
S_{pti,adj} = HC_{pti} \times SC_{pti,adj} \qquad (\text{Eq 4 variant})
$$

$$
\eta_{ij,adj} = \frac{S_{pti,adj}}{D_{ij}} \qquad (\text{Eq 12 variant})
$$

---

### Recovery

| Event | Effect |
|---|---|
| Meal insertion (45 min block) | $hunger \leftarrow 0$; clock advances 45 min |
| Rest insertion (20 min block) | $fatigue \leftarrow fatigue - 0.40$; clock advances 20 min |
| Trigger cooldown | 40 min suppression — prevents back-to-back disruption fires |

---

## 9. Budget Planning Formulas

All computed in `BudgetPlanner.distribute()` (`planning/budget_planner.py`).

### Accommodation

$$
Accommodation = \min\!\left( hotel_{nightly} \times TripDays,\; 0.40 \times TotalBudget \right)
$$

Hard cap: $Accommodation \leq 0.45 \times TotalBudget$.
$hotel_{nightly}$ = **median** of available `HotelRecord.price_per_night` values
(or city-index fallback).

---

### Restaurants

$$
restaurant_{base} = avg\_meal\_cost \times group\_size \times 2 \times TripDays
$$

$$
Restaurants = \min\!\left( restaurant_{base} \times 1.10,\; 0.25 \times TotalBudget \right)
$$

The $\times 1.10$ factor is a **10 % meal flexibility buffer**.
$avg\_meal\_cost$ = **median** of `RestaurantRecord.avg_price_per_person` (or city-index).

---

### Attractions

$$
scale = \min\!\left(\frac{scheduled\_per\_day}{4.0},\; 1.5\right)
$$

$$
Attractions = city\_idx[attraction\_per\_day] \times scale \times TripDays
$$

4 attractions/day is the city-index baseline. Scale is capped at 1.5× to prevent
outlier-heavy days from distorting the budget.

---

### Transportation

**Distance-based (preferred):**
$$
Transportation = \min\!\left( total\_km \times cost\_per\_km,\; 0.20 \times TotalBudget \right)
$$

**Daily-rate fallback:**
$$
Transportation = \min\!\left( daily\_transport \times group\_size \times TripDays,\; 0.20 \times TotalBudget \right)
$$

---

### Other Expenses

$$
Other\_Expenses = 0.075 \times TotalBudget \quad \text{(midpoint of specified 5–10 \% range)}
$$

---

### Reserve Fund (residual)

$$
Reserve\_Fund = TotalBudget - Accommodation - Restaurants - Attractions - Transportation - Other\_Expenses
$$

Hard floor: $Reserve\_Fund \geq 0.05 \times TotalBudget$.
If the residual is negative, `_apply_constraints_and_balance()` proportionally
scales down all soft categories until the floor is met.

---

### Post-Itinerary Rebalance Trigger

$$
\text{rebalance if } proj\_total > allocation\_total \;\lor\; proj\_reserve < 0.05 \times TotalBudget
$$

---

## 10. Soft-Weight Learning (Long-Term Memory)

Applied in Stage 5 (`long_term_memory.update_soft_weights()`).

### Update Rule

$$
W_{v,new} = W_{v,old} + \lambda \times feedback_v, \quad feedback_v \in [-1, +1]
$$

### Clamp

$$
W_{v,new} = \max(0,\; W_{v,new})
$$

### Re-normalize (Eq 3)

$$
W_{v,new} \leftarrow \frac{W_{v,new}}{\sum_v W_{v,new}}
$$

| Parameter | Value | Notes |
|-----------|-------|-------|
| Learning rate $\lambda$ | **0.1** (default) | Tune empirically |
| $feedback_v$ domain | $[-1, +1]$ | From `ShortTermMemory.get_feedback_summary()` |

---

## 11. Geographic Distance — Haversine Formula

Used for clustering (`route_planner.py`), deduplication, and replacement-candidate
radius checks (`local_repair.py`, `partial_replanner.py`).

$$
a = \sin^2\!\left(\frac{\Delta\phi}{2}\right) + \cos\phi_1 \cdot \cos\phi_2 \cdot \sin^2\!\left(\frac{\Delta\lambda}{2}\right)
$$

$$
d = 2R \cdot \arcsin\!\left(\sqrt{a}\right), \quad R = 6371\text{ km}
$$

---

## 12. Deterministic Scheduling Rules (Route Planner)

Applied by `RoutePlanner._plan_single_day()` after ACO tour construction
to assign concrete arrival/departure times.

| Rule | Constant | Value |
|------|----------|-------|
| R1 — Transition buffer | `_TRANSITION_BUFFER_MIN` | **12 min** |
| R2 — Cluster radius cap | `_MAX_CLUSTER_RADIUS_KM` | **9.0 km** |
| R4 — Same-location dedup (coords) | `_DEDUP_COORD_DIST_KM` | **0.30 km** (300 m) |
| R4 — Same-location dedup (name overlap) | `_DEDUP_WORD_OVERLAP_RATIO` | **0.70** (70 %) |
| R5 — Max continuous sightseeing | `_MAX_CONTINUOUS_SIGHT_MIN` | **180 min** |
| R6 — Max idle gap | `_MAX_IDLE_GAP_MIN` | **90 min** |
| R6 — Hard day-end cutoff | `_DAY_END_HARD` | **20:30** |
| R7 — Max same-day travel | `_MAX_SAME_DAY_TRAVEL_MIN` | **60 min** |

**Time assignment per RoutePoint:**

$$
arr_j = dep_i + D_{ij} + 12 \quad \text{(12 min transition buffer)}
$$
$$
dep_j = arr_j + ST_j
$$

**K-means geographic clustering:**
- Convergence limit: **15 iterations**
- Attractions reassigned daily so each day's cluster radius $\leq$ 9.0 km

---

## 13. Summary of All Numeric Constants

| Constant | Value | Location |
|----------|-------|----------|
| $T_{max}$ | 660 min | `config.ACO_TMAX_MINUTES` |
| $\alpha$ | 2.0 | `config.ACO_ALPHA` |
| $\beta$ | 3.0 | `config.ACO_BETA` |
| $\rho$ | 0.1 | `config.ACO_RHO` |
| $Q$ | 1.0 | `config.ACO_Q` |
| $\tau_{init}$ | 1.0 | `config.ACO_TAU_INIT` |
| $\eta_{max}$ | $10^6$ | `heuristic.py _ETA_MAX` |
| $W_r / W_p / W_o$ | 0.40 / 0.35 / 0.25 | `attraction_scoring.py` |
| $\lambda$ (learning rate) | 0.1 | `long_term_memory.py` |
| HC\_UNSAFE\_THRESHOLD | 0.75 | `weather_advisor.py` |
| CROWD\_DECAY\_PER\_30MIN | 0.15 | `local_repair.py` |
| LocalRepair BUFFER | 10 min | `local_repair.py` |
| LocalRepair MAX\_GAP | 90 min | `local_repair.py` |
| LocalRepair MEAL\_MIN\_GAP | 60 min | `local_repair.py` |
| LocalRepair CLUSTER\_RADIUS | 5.0 km | `local_repair.py` |
| LocalRepair MAX\_REPLACE\_RADIUS | 3.0 km | `local_repair.py` |
| Route Buffer | 12 min | `route_planner.py` |
| Route Cluster Radius | 9.0 km | `route_planner.py` |
| Dedup Distance | 0.30 km | `route_planner.py` |
| Dedup Name Overlap | 0.70 | `route_planner.py` |
| Accommodation cap | 0.45 | `budget_planner.py` |
| Restaurant cap | 0.25 | `budget_planner.py` |
| Transport cap | 0.20 | `budget_planner.py` |
| Reserve floor | 0.05 | `budget_planner.py` |
| Meal flexibility buffer | 1.10 | `budget_planner.py` |
| Other\_Expenses % | 0.075 | `budget_planner.py` |
| Crowd $\theta$ — sensitive | 0.35 | `condition_monitor.py` |
| Crowd $\theta$ — tolerant | 0.70 | `condition_monitor.py` |
| Traffic $\theta$ — relaxed | 0.30 | `condition_monitor.py` |
| Traffic $\theta$ — moderate | 0.55 | `condition_monitor.py` |
| Traffic $\theta$ — packed | 0.80 | `condition_monitor.py` |
| Heavy penalty multiplier | 0.80 | `condition_monitor.py` (traffic only, not crowd) |
| Weather $\theta$ — outdoor-heavy | 0.40 | `condition_monitor.py` |
| Weather $\theta$ — indoor-heavy | 0.65 | `condition_monitor.py` |
| Morning weather multiplier | 0.85 | `condition_monitor.py` |
| Threshold clamp | \[0.15, 0.90\] | `condition_monitor.py` |
| Traffic DEFER threshold | 0.65 | `traffic_advisor.py` |
| $R$ (Earth radius) | 6371 km | `route_planner.py` || GLOBAL\_REPLAN\_THRESHOLD | 3 | `local_repair.py` |
| DAY\_END\_MINUTES | 1255 (20:55) | `local_repair.py` |
| REPAIR\_WINDOW\_RADIUS | 2 | `local_repair.py` |
| AlternativeGen MAX\_DISTANCE | 5.0 km | `alternative_generator.py` |
| AlternativeGen AVG\_SPEED | 25 km/h | `alternative_generator.py` |
| MULTI\_DISRUPTION\_TRIGGER | 3 | `planning_agent.py`, `memory_agent.py` |
| TIME\_PRESSURE\_MINUTES | 60 | `planning_agent.py`, `agent_controller.py` |
| HIGH\_VALUE\_CUTOFF | 0.65 | `disruption_agent.py`, `agent_controller.py` |
| OVERRUN\_THRESHOLD | 0.90 | `budget_agent.py` |
| UNDERUTILIZED\_THRESHOLD | 0.40 | `budget_agent.py` |
| TIME\_PROGRESS\_GATE | 0.60 | `budget_agent.py` |

---

## 14. AlternativeGenerator — Composite Scoring (§AG)

The `AlternativeGenerator` ranks replacement candidates using a 7-criteria weighted
composite score. All candidates within $d \leq 5.0$ km are considered. Restaurants are
added to the pool during meal windows.

### §AG-1 — Composite Score

$$
C_{alt} = \sum_{k=1}^{7} w_k \cdot s_k
$$

| Criterion $k$ | Weight $w_k$ | Score $s_k$ formula |
|---|---|---|
| Distance | 0.25 | $s_1 = \max(0,\; 1 - d / D_{max})$, $D_{max} = 5.0$ km |
| Category match | 0.15 | $s_2 = 1.0$ (exact) / $0.5$ (partial) / $0.2$ (unrelated) |
| Crowd avoidance | 0.20 | $s_3 = 1 - crowd\_level$ |
| Weather suitability | 0.15 | $s_4 = 1.0$ (indoor or clear) / $0.3$ (outdoor in bad weather) |
| Timing | 0.10 | $s_5 = 1.0$ (open now) / $0.0$ (closed) |
| FTRM proxy | 0.10 | $s_6 = \frac{rating / 5.0}{d / D_{max}}$ (η-style) |
| Meal bonus | 0.05 | $s_7 = 1.0$ (restaurant during meal window) / $0.0$ |

$$
\sum_{k} w_k = 1.0
$$

### §AG-2 — Travel Time Estimate

$$
T_{travel} = \max\!\left(5,\; \frac{d}{25} \times 60\right) \quad \text{minutes}
$$

---

## 15. LocalRepair Invariant System (§INV)

8 invariants enforced in `InvariantChecker.check()` after every repair operation.

### §INV-1 through §INV-8

| ID | Invariant | Exemption |
|----|-----------|-----------|
| Inv1 | Visited POIs immutable — cannot reorder or remove | None |
| Inv2 | Completed time blocks locked | None |
| Inv3 | Executed meals locked | None |
| Inv4 | Stop count change ≤ ±1 from original | **Exempted when `is_user_skip=True`** |
| Inv5 | No duplicate POIs in plan | None |
| Inv6 | No duplicate meals in plan | None |
| Inv7 | No reordering of unaffected (non-disrupted) stops | None |
| Inv8 | Geographic cluster: $haversine(disrupted, alt) \leq 5.0$ km | None |

### §INV-SKIP — USER_SKIP Invariant Exemption

The `is_user_skip` flag is threaded through the full repair chain:

$$
repair() \to \_repair\_inner() \to \_finalise() \to InvariantChecker.check()
$$

When `is\_user\_skip = True$:
- Inv4 check is **skipped** — the plan may lose more than 1 stop
- All other invariants remain enforced

### §INV-FRAG — Fragile Day Guard

After `_validate_and_fix_meals()`, the finaliser checks:

$$
non\_meal\_count = |\{stop \in plan \mid stop.category \neq \text{``restaurant''}\}|
$$

$$
\text{reject plan if } non\_meal\_count = 0
$$

This prevents degenerate "meal-only" days from passing invariant checks.

---

## 16. State Hashing (Observability)

`compute_state_hash(state)` in `execution_layer.py` generates a deterministic
fingerprint of `TripState` for integrity verification.

### Formula

$$
H = \text{SHA-256}\!\left(\text{json\_dumps}(S_{filtered},\; sort\_keys=True,\; default=str)\right)
$$

where:

$$
S_{filtered} = S_{all} \setminus S_{transient}, \quad S_{transient} = \{current\_day\_plan,\; replan\_pending\}
$$

- Sets (e.g. `visited`, `skipped`, `deferred`) are **sorted** before serialisation
- Logged as `before_hash` / `after_hash` in every `STATE_MUTATION` event
- Replay verification: last replayed `after_hash` must match last logged `after_hash`
  → `RuntimeError("REPLAY_DIVERGENCE")` on mismatch
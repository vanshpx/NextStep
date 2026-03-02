# Database Architecture — Polyglot Persistence Decision

> System: Travel Itinerary Optimizer (TravelAgent + ICDM + FTRM + ACO + Re-optimization Engine)
> Created: 2026-02-23

---

## Verdict: Polyglot Persistence Required

A **single database cannot satisfy all workload requirements** of this system.
Three distinct tiers are required.

---

## Three-Tier Architecture

| Tier | Technology Class | Data Stored |
|---|---|---|
| **Tier 1 — Relational** | PostgreSQL (with JSONB) | Users, SC weights, Trips, Budget, POI catalog, Hotels/Restaurants/Flights, Itinerary & DayPlans, Dij backing store, DisruptionEvents, CommonsenseRules |
| **Tier 2 — In-memory cache** | Redis / Valkey (with AOF persistence) | Active TripState, Dij hot-path lookup cache, ShortTermMemory during session |
| **Tier 3 — Document / Log store** | Append-only log store (Elasticsearch, Loki, or JSONL for small scale) | LLM prompt/response audit logs |

---

## Why Not a Single Relational DB

| Requirement | Why Relational Alone Fails |
|---|---|
| ACO inner loop: 20 ants × 100 iterations × n² Dij lookups | Relational query latency (even indexed) cannot match Redis sub-millisecond key lookup. Every millisecond of Dij latency multiplies into seconds of total optimization time. |
| TripState mutation every `advance_to_stop` call | Row-level locking on a relational write for every stop arrival (every few seconds during active trip) creates contention if multiple sessions run concurrently. Redis hash update is atomic and lock-free. |
| LLM prompt/response blobs | Large variable-length text blobs with no JOIN dependencies bloat Postgres table storage and query plans if co-located with structured data. A log store handles append-only writes with time-based TTL more efficiently. |

---

## Why Not a Graph DB for POIs and Edges

| Consideration | Decision |
|---|---|
| Travel graph topology | Complete weighted graph — every POI pair has a Dij value. Graph DBs are optimized for multi-hop traversals (friend-of-friend, path finding). ACO only performs single-hop point lookups: `(poi_a, poi_b) → travel_time_minutes`. |
| Query pattern | `SELECT travel_time_minutes FROM poi_graph_edges WHERE city=X AND poi_a_id=A AND poi_b_id=B AND transport_mode=M` → Composite index covers this in O(log n). |
| Operational cost | Graph DB adds a third persistent infrastructure component. A `poi_graph_edges` table in Postgres + Redis cache achieves identical performance at lower complexity. |
| Verdict | **No graph DB required.** Relational table + Redis cache is sufficient. |

---

## Why Not a Vector DB

| Consideration | Decision |
|---|---|
| Stated requirement | No semantic similarity search is performed in the current system. Recommendations use explicit FTRM scoring (HC × SC), not embedding similarity. |
| `HistoricalInsightTool` | Retrieves `AttractionRecord.historical_importance` by stop name (exact lookup) and falls back to LLM. No embedding search. |
| `LongTermMemory` | Stores and retrieves user preferences by `user_id` key. No nearest-neighbour lookup on preference vectors. |
| Future consideration | MISSING: If future versions add "find attractions similar to ones the user liked," a vector DB becomes relevant. Not required now. |
| Verdict | **No vector DB required at current architecture level.** |

---

## ACO Pheromone Matrix — In-Process Only

```
τ_ij  →  Python dict / numpy 2D array  →  discarded after optimizer.run() returns

Lifecycle:
  1. aco_optimizer.run() initializes τ_ij = τ_init (1.0) for all edges
  2. 100 iterations: ants update τ_ij, evaporation applied each round
  3. Best tour returned → τ_ij discarded
  4. Next trip or replan: τ_ij re-initialized from τ_init

Cross-session pheromone persistence provides no benefit:
  - τ_ij encodes the search history of ONE optimization run over ONE city graph
  - City graph changes (new POIs, updated Dij) invalidate prior pheromones
  - τ_init = 1.0 is tunable per run via config.py
  - Storing a 50×50 float matrix per trip adds storage with zero analytical value
```

**Rule: ACO pheromone state MUST NEVER leave the optimizer process.**

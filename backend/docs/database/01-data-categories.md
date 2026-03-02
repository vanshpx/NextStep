# Database Architecture — Data Categories

> System: Travel Itinerary Optimizer (TravelAgent + ICDM + FTRM + ACO + Re-optimization Engine)
> Created: 2026-02-23

---

## All Data Categories — Storage Model and Rationale

| # | Data Category | Data Type | Read/Write Pattern | Retention | Consistency | Storage Model | Justification |
|---|---|---|---|---|---|---|---|
| 1 | User Profile + Auth | Structured | High read (every session start), low write (session end) | Permanent | Strong | **Relational** | Fixed schema: `user_id`, timestamps, currency pref. Foreign key anchor for all other tables. |
| 2 | Soft Constraint Weights (Wv) | Structured numeric | High read, low write (Stage 5 update via λ-learning) | Permanent | Strong | **Relational** (same DB as user, separate `user_sc_weights` table) | 5-dim float vector per user, updated via `W_v_new = normalize(W_v_old + λ × feedback_v)`. Must be transactionally consistent with user profile. |
| 3 | Long-term User Preferences (interests, pace, diet, traits) | Semi-structured | High read (Stage 1 seed), moderate write | Permanent | Strong | **JSONB column** in relational user profile table | Shape evolves (new preference keys added). JSONB gives schema flexibility without a separate document store. |
| 4 | Commonsense Rules | Structured list | High read (Stage 1), rare write | Permanent | Eventual | **Relational** (`commonsense_rules` table keyed by user_id + rule_text) | Small cardinality (~5–20 rules/user). Simpler to query, join, and deduplicate in SQL than in document store. |
| 5 | Trip (HardConstraints) | Structured | Write-once at planning, high read during active trip | Long-term | Strong | **Relational** | All HC fields are flat scalars or small arrays (traveler_ages, fixed_appointments as JSONB). Transactional integrity required at booking. |
| 6 | Budget Allocation (BudgetAllocation) | Structured | Write-once + updates on replan | Long-term | Strong | **Relational** (FK to Trip) | 6 fixed float columns. No document overhead needed. |
| 7 | POI Catalog (AttractionRecord) | Semi-structured | High read by ACO + recommenders (Stage 3–4), low write (API cache refresh) | Medium-term (cache TTL) | Eventual | **Relational** with `historical_importance` as TEXT column + full-text index | 20+ fixed fields (HC/SC). Full-text search on `historical_importance` needed by `HistoricalInsightTool`. JSONB `raw` column for unprocessed API response. |
| 8 | Hotel / Restaurant / Flight Records | Semi-structured | High read (recommenders), low write | Medium-term | Eventual | **Relational** (separate tables per type) | Each has distinct HC columns (e.g., `star_rating`, `cuisine_tags`, `stops_type`). Separate tables avoid wide sparse rows. |
| 9 | Travel-time Graph Edges (Dij) | Structured | **Very high read** by ACO (20 ants × 100 iterations × n² lookups), batch write per city | Medium-term | Eventual | **In-memory cache** (Redis/Valkey) as primary; **Relational** as persistent backing store | ACO inner loop requires sub-millisecond edge lookups. Cache key: `dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}`. Relational table persists pre-computed city graphs between sessions. |
| 10 | Itinerary + DayPlan + RoutePoints | Hierarchical structured | Write at generation (Stage 4) + replan mutations; high read (user view) | Long-term | Strong | **Relational** — `itinerary_days` table + `route_points` as JSONB array | Itinerary hierarchy is 3 levels deep (Trip → DayPlan → RoutePoint[]) but not recursive and not graph-traversed. JSONB for route_points avoids N+1 join overhead on display. |
| 11 | Active Session / TripState | Structured | **Very high write** (every `advance_to_stop`, environmental check, event) | Ephemeral (session TTL) | Strong within session | **In-memory cache** (Redis/Valkey with TTL) | Fields: `visited_stops`, `skipped_stops`, `deferred_stops`, `current_time`, `current_lat/lon`, `hunger_level`, `fatigue_level`, `replan_pending`, `pending_decision`. Session lasts hours; must survive process restart → Redis persistence (AOF). |
| 12 | Disruption History (DisruptionMemory) | Semi-structured event records | Append-only write during session; read at session end for `serialize()` | Session → promoted to long-term on trip completion | Eventual | **In-memory** during session (already in `DisruptionMemory` class); serialized JSON checkpoint → **Relational** `disruption_events` table on promotion | Maps directly to `WeatherRecord`, `TrafficRecord`, `ReplacementRecord`, `HungerRecord`, `FatigueRecord`. Each row = one event. `metadata` JSONB for type-specific fields. |
| 13 | Short-term Interaction Log (ShortTermMemory) | Semi-structured | High write (every exchange), read at session end (→ LongTermMemory.promote) | Session-scoped | Eventual | **In-memory** during session; selective promotion to relational at end | Conversation turns, mid-session preference changes, feedback scores. Not all rows need long-term persistence — only `get_feedback_summary()` output is promoted. |
| 14 | ACO Pheromone Matrix (τ_ij) | Dense float matrix | Very high read+write within optimization run | **Ephemeral** (per optimization call, minutes) | N/A | **In-process memory only** (numpy/dict) | Pheromones encode the best tour found in *this run*. No cross-trip signal. τ_init is configurable. Persisting pheromones cross-session provides no architectural benefit and wastes I/O on 100× evaporation cycles. **DO NOT PERSIST.** |
| 15 | LLM Interaction Logs | Semi-structured | Write-once (append), read for audit/debug only | Short-term (30 days) | Eventual | **Document DB** or append-only log store | Prompts and raw JSON responses contain free-form text of variable size. Not joined with other tables. Used only for debugging. Separating from relational DB avoids bloating main DB with large text blobs. |
| 16 | Approval Gate Payload (PendingDecision) | Structured | Write on disruption detection, read on `resolve_pending()`, delete on resolution | Ephemeral (minutes) | Strong | Part of **TripState in in-memory cache** | `PendingDecision` is a transient struct in `session.pending_decision`. No independent store needed. Checkpoint survives in the Redis TripState snapshot. |

---

## Storage Model Legend

| Symbol | Meaning |
|---|---|
| **Relational** | PostgreSQL with JSONB support |
| **In-memory cache** | Redis / Valkey |
| **In-process memory** | Python in-process (numpy, dict) — no external store |
| **Document / Log store** | Append-only log (Elasticsearch, Loki, or JSONL for small scale) |
| **DO NOT PERSIST** | Computation artifact — must never leave the optimizer process |

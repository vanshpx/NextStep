# Database Architecture — Data Exclusions

> System: Travel Itinerary Optimizer (TravelAgent + ICDM + FTRM + ACO + Re-optimization Engine)
> Created: 2026-02-23

---

## What MUST NOT Be Stored

| Item | Category | Reason |
|---|---|---|
| ACO pheromone matrix (τ_ij) | Computation artifact | Ephemeral per optimization call. Encodes search history of one run over one city graph. τ_init = 1.0 is configurable per run. Persisting 100 evaporation iterations across sessions has zero downstream value. **Must never leave the optimizer process.** |
| Intermediate ant tour snapshots | Computation artifact | Debugging artifact only. Not actionable for any downstream module. If debugging is needed, log to stdout — not DB. |
| S_pti score map for unselected POIs | Computation artifact | Overflow computation from the ACO scoring pass. Only the winning tour's scores feed the Wv feedback update. Storing all candidate scores inflates storage with no retrieval use case. |
| Raw LLM API keys / tokens | Security | Never stored in any row or column. Loaded exclusively from environment variables (`config.py` `LLM_API_KEY`, `SERPAPI_KEY`, etc.). |
| LLM prompt text containing user PII | Privacy | Prompt templates are code, not data. Any prompt containing user-supplied free-text (Phase 2 chat) must have PII stripped or hashed before entering any log store. Plain prompt storage creates a privacy liability. |
| Hunger / fatigue level time-series beyond session scope | Unnecessary biometric data | No stated analytics requirement for user biometric trends across trips. Session-scoped `FatigueRecord` / `HungerRecord` in `disruption_events` table is the maximum granularity needed. Do not build a continuous biometric time-series table. |
| `TripState.deferred_stops` and `skipped_stops` post-trip | Redundant state | After trip completion these sets are fully superseded by the `disruption_events` table rows. Persisting them as a separate column duplicates state and creates a stale-read hazard if event records are later corrected. |
| Full serialized `ConstraintBundle` per optimization run | Redundant duplication | HC fields are stored in `trips`; SC fields + Wv are stored in `user_memory_profile`. Storing a serialized bundle per run creates a derived copy that can silently diverge from the source tables if either is updated. Always reconstruct from source tables. |
| Hotel / Restaurant / Flight raw API responses (beyond `poi.raw_api_response`) | Storage bloat | One JSONB `raw_api_response` column per POI record is the ceiling. Duplicating full API payloads across separate hotel, restaurant, and flight tables wastes storage and has no access pattern that justifies it. |
| Session-to-session pheromone history | Architectural misuse | Pheromones model ACO's internal search state, not user preferences. Persisting them cross-trip would require invalidation logic every time a POI is added, removed, or its Dij changes — which is every city cache refresh. The cost outweighs any theoretical warm-start benefit. |
| User authentication tokens / session cookies | Security / MISSING | Authentication infrastructure is absent from the current codebase. A token table must not be designed until the auth layer is specified. The `user_id` UUID is sufficient as a session identifier for now. |
| Commonsense rules sourced from LLM without user confirmation | Data quality | LLM-extracted commonsense rules (`CommonsenseConstraints.rules`) must only be promoted to `user_memory_profile.commonsense_rules` after a session completes without user correction. Storing speculative LLM output as permanent user preference is a data quality risk. |

---

## Promotion Rules (ShortTermMemory → LongTermMemory)

> MISSING in codebase (`long_term_memory.py`: "TODO: MISSING — promotion logic/rules").

Until specified, these rules apply as defaults:

| Signal | Promote? | Condition |
|---|---|---|
| `get_feedback_summary()` Wv feedback scores | Yes | Always — feeds λ-learning update |
| Mid-session `USER_PREFERENCE_CHANGE` events | Yes | After user confirms via approval gate |
| Commonsense rules extracted from LLM | Yes | Only if trip completed without user contradicting the rule |
| `disruption_events` rows | Yes | All rows promoted on trip completion |
| `ShortTermMemory` raw conversation turns | No | Not promoted — too granular, no retrieval use case |
| Hunger / fatigue raw levels (float) | No | Only the outcome (`action_taken`, `user_response`) is stored |
| Deferred stop names | No | Subsumed by disruption event records |

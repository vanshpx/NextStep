"""
modules/memory/short_term_memory.py
-------------------------------------
Stores new user interactions, immediate contextual travel data, constraints,
and plans from the current session. Adapts to the latest user preferences.

Populated/updated:
  - During Stage 3 (Implicit Insight Learning after user behavioral interactions).
  - During Stage 5 (Memory Update after itinerary generation).

Resolution 3: record_feedback() added to accumulate per-constraint
  feedback scores ∈ [-1, +1] in-session for Wv weight learning.
  get_feedback_summary() aggregates per-constraint scores for promotion
  to LongTermMemory.update_soft_weights() at Stage 5.

TODO (MISSING from architecture doc):
  - Storage backend (in-memory dict used as placeholder; should be Redis/vector DB).
  - Data schema for stored insights.
  - Eviction/TTL policy for short-term entries.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any


class ShortTermMemory:
    """
    Session-scoped memory store.
    Persists interactions and insights for the current planning session only.
    """

    def __init__(self) -> None:
        # TODO: MISSING — replace dict with actual backend (Redis, SQLite, etc.)
        self._store: dict[str, Any] = {}
        self._interaction_log: list[dict[str, Any]] = []
        # Resolution 3: per-constraint feedback buffer {constraint_name: [scores]}
        self._feedback_buffer: dict[str, list[float]] = {}

    # ── Interaction Logging ───────────────────────────────────────────────────

    def log_interaction(self, interaction_type: str, payload: dict[str, Any]) -> None:
        """
        Record a user interaction (e.g., like/pass feedback, budget confirmation).

        Args:
            interaction_type: e.g. "feedback" | "budget_confirm" | "constraint_update"
                              TODO: MISSING — exact taxonomy of interaction types.
            payload:          Interaction data. Schema per type is MISSING.
        """
        entry = {
            "type": interaction_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self._interaction_log.append(entry)

    def get_interactions(self, interaction_type: str | None = None) -> list[dict[str, Any]]:
        """
        Retrieve logged interactions, optionally filtered by type.
        """
        if interaction_type is None:
            return list(self._interaction_log)
        return [e for e in self._interaction_log if e["type"] == interaction_type]

    # ── Insight Storage ───────────────────────────────────────────────────────

    def store_insight(self, key: str, value: Any) -> None:
        """
        Store a short-term insight derived from the current session.

        Args:
            key:   Insight identifier (e.g. "prefers_outdoor", "dislikes_crowded").
                   TODO: MISSING — insight key taxonomy not specified in architecture doc.
            value: Insight value.
        """
        self._store[key] = {
            "value": value,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    def get_insight(self, key: str) -> Any | None:
        """Retrieve a stored insight by key. Returns None if not found."""
        entry = self._store.get(key)
        return entry["value"] if entry else None

    def get_all_insights(self) -> dict[str, Any]:
        """Return all current short-term insights as a flat dict."""
        return {k: v["value"] for k, v in self._store.items()}

    def clear(self) -> None:
        """Clear all short-term memory (e.g., at session end after long-term promotion)."""
        self._store.clear()
        self._interaction_log.clear()
        self._feedback_buffer.clear()

    # ── Resolution 3: Constraint Feedback for Wv Weight Learning ─────────────

    def record_feedback(self, constraint_name: str, score: float) -> None:
        """
        Record a per-constraint feedback signal in the session buffer.

        Called when the user implicitly or explicitly signals preference
        (e.g., like=+1, pass=-1, partial preference=∈(-1,+1)).

        Args:
            constraint_name : Soft constraint identifier matching Wv key.
                              e.g. "optimal_window", "time_efficiency", "cuisine_match".
            score           : Feedback value ∈ [-1, +1].
                              +1 = strong positive signal.
                               0 = neutral.
                              -1 = strong negative signal.
        """
        score = max(-1.0, min(1.0, float(score)))   # clamp to [-1, +1]
        if constraint_name not in self._feedback_buffer:
            self._feedback_buffer[constraint_name] = []
        self._feedback_buffer[constraint_name].append(score)
        self.log_interaction("constraint_feedback", {
            "constraint": constraint_name, "score": score
        })

    def get_feedback_summary(self) -> dict[str, float]:
        """
        Aggregate per-constraint feedback as mean scores.
        Returns {constraint_name: mean_score} for all recorded constraints.
        Used by LongTermMemory.update_soft_weights() at Stage 5 (Eq 3 update).
        """
        return {
            name: sum(scores) / len(scores)
            for name, scores in self._feedback_buffer.items()
            if scores
        }

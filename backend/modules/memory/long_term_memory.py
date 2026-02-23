"""
modules/memory/long_term_memory.py
------------------------------------
Retains user data over extended periods.
Accumulates a comprehensive persona based on:
  - Historical interactions (promoted from ShortTermMemory).
  - Stable user preferences.
  - Commonsense knowledge.

Updated in Stage 5 after itinerary generation.
Read in Stage 1 (soft/commonsense constraint initialization) and Stage 3 (history insights).

Resolution 3: update_soft_weights() added, implementing:
  W_v_new = normalize(W_v_old + λ × feedback_v)
  where feedback_v ∈ [-1, +1], λ = learning rate (DEFAULT 0.1).
  Called at Stage 5 with data from ShortTermMemory.get_feedback_summary().

TODO (MISSING from architecture doc):
  - Storage backend (in-memory dict placeholder; should be vector DB / RDBMS).
  - Promotion rules from ShortTermMemory to LongTermMemory.
  - User identification/authentication schema.
  - Commonsense knowledge seeding strategy.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any


class LongTermMemory:
    """
    Cross-session persistent user profile and commonsense knowledge store.
    Provides history_insights to other modules.
    """

    def __init__(self) -> None:
        # TODO: MISSING — replace with actual persistent backend.
        # Key: user_id (str), Value: user profile dict.
        self._user_profiles: dict[str, dict[str, Any]] = {}

        # Commonsense knowledge rules (seeded at init; expanded over time).
        # TODO: MISSING — actual commonsense rules not specified in architecture doc.
        self._commonsense_rules: list[str] = [
            "A sight cannot be visited twice during the same trip.",
            "Hotels should be positioned near the city centre or trip activity areas.",
            "Restaurants should be selected at reasonable meal times.",
            # TODO: Add more commonsense rules as they are specified.
        ]

    # ── User Profile Management ───────────────────────────────────────────────

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """
        Retrieve the stored profile for a user.
        Returns empty profile dict if user not found.
        """
        return self._user_profiles.get(user_id, {})

    def update_user_profile(self, user_id: str, updates: dict[str, Any]) -> None:
        """
        Merge new insights into the user's long-term profile.
        Called in Stage 5 (Memory Update).

        Args:
            user_id: Unique user identifier.
                     TODO: MISSING — user ID format not specified in architecture doc.
            updates: Dict of insight key → value to merge into the profile.
        """
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = {}

        self._user_profiles[user_id].update(updates)
        self._user_profiles[user_id]["_last_updated"] = datetime.utcnow().isoformat() + "Z"

    def promote_from_short_term(
        self,
        user_id: str,
        short_term_insights: dict[str, Any],
    ) -> None:
        """
        Promote insights from ShortTermMemory into the long-term user profile.
        Called at session end (Stage 5).

        TODO: MISSING — promotion logic/rules (threshold, conflict resolution)
              not specified in architecture doc.
        Placeholder: direct merge.
        """
        self.update_user_profile(user_id, short_term_insights)

    # ── History Insights Retrieval ────────────────────────────────────────────

    def get_history_insights(self, user_id: str) -> dict[str, Any]:
        """
        Return combined history insights for a user.
        Used by Recommendation Module and Planning Module in Stage 1 and Stage 3.

        Returns:
            Dict with 'user_preferences' and 'commonsense_rules'.
        """
        profile = self.get_user_profile(user_id)
        return {
            "user_preferences": profile,
            "commonsense_rules": self._commonsense_rules,
        }

    # ── Commonsense Knowledge Management ─────────────────────────────────────

    def add_commonsense_rule(self, rule: str) -> None:
        """Add a new commonsense rule to the knowledge base."""
        if rule not in self._commonsense_rules:
            self._commonsense_rules.append(rule)

    def get_commonsense_rules(self) -> list[str]:
        """Return all current commonsense knowledge rules."""
        return list(self._commonsense_rules)

    def get_profile(self, user_id: str) -> dict:
        """Alias for get_user_profile — used by planning modules."""
        return self.get_user_profile(user_id)

    # ── Resolution 3: Soft Constraint Weight Learning (Wv) ────────────────────

    _DEFAULT_LAMBDA: float = 0.1   # SUGGESTED DEFAULT — tune empirically

    def update_soft_weights(
        self,
        user_id: str,
        feedback: dict[str, float],
        lambda_: float = _DEFAULT_LAMBDA,
    ) -> dict[str, float]:
        """
        Apply feedback-driven weight update rule for Wv (Resolution 3).

        Update equation:
            W_v_new = W_v_old + λ × feedback_v
            Then: normalize so Σ W_v = 1  (Eq 3)

        Args:
            user_id  : User whose weight vector to update.
            feedback : {constraint_name: score ∈ [-1, +1]} from
                       ShortTermMemory.get_feedback_summary().
            lambda_  : Learning rate (SUGGESTED DEFAULT: 0.1).

        Returns:
            Updated weight dict {constraint_name: Wv} post-normalization.
        """
        profile = self._user_profiles.setdefault(user_id, {})
        weights: dict[str, float] = dict(profile.get("soft_weights", {}))

        # Seed equal weights for any new constraints
        all_keys = set(weights) | set(feedback)
        if not weights:
            n = len(all_keys)
            weights = {k: (1.0 / n if n > 0 else 1.0) for k in all_keys}

        # W_v_new = W_v_old + λ × feedback_v
        for constraint, fb_score in feedback.items():
            current = weights.get(constraint, 0.0)
            weights[constraint] = current + lambda_ * fb_score

        # Clamp to non-negative (weights must not go below 0)
        weights = {k: max(0.0, v) for k, v in weights.items()}

        # Normalize: Σ Wv = 1  (Eq 3)
        total = sum(weights.values())
        if total > 0.0:
            weights = {k: v / total for k, v in weights.items()}
        else:
            # All clamped to 0 — reset to equal weights
            n = len(weights)
            weights = {k: 1.0 / n for k in weights}

        # Persist updated weights into profile
        profile["soft_weights"] = weights
        profile["_last_updated"] = datetime.utcnow().isoformat() + "Z"

        return weights

    def get_soft_weights(self, user_id: str) -> dict[str, float]:
        """
        Retrieve current Wv weight map for a user.
        Returns empty dict (caller falls back to equal weights) if not set.
        """
        return dict(self._user_profiles.get(user_id, {}).get("soft_weights", {}))

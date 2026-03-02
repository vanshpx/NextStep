"""
modules/reoptimization/agent_action.py
-----------------------------------------
Structured action schema emitted by AgentController.

The agent NEVER free-texts a plan.  It returns exactly one AgentAction
whose ``action_type`` is drawn from the closed ``ActionType`` enum.
The execution layer (``ExecutionLayer``) is the ONLY component that
may mutate itinerary state based on this action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Action taxonomy ───────────────────────────────────────────────────────────

class ActionType(Enum):
    """Closed set of actions the agent may emit."""

    NO_ACTION          = "NO_ACTION"
    """Continue the current itinerary unchanged."""

    REQUEST_USER_DECISION = "REQUEST_USER_DECISION"
    """Show alternatives to the user; block until decision received."""

    DEFER_POI          = "DEFER_POI"
    """Temporarily remove a POI from today's schedule (local repair)."""

    REPLACE_POI        = "REPLACE_POI"
    """Generate alternatives for a POI and present to user."""

    RELAX_CONSTRAINT   = "RELAX_CONSTRAINT"
    """Loosen a soft constraint (e.g. extend travel radius, shift pace)."""

    REOPTIMIZE_DAY     = "REOPTIMIZE_DAY"
    """Trigger a bounded ACO re-run for the remainder of the day."""


# ── Action payload ────────────────────────────────────────────────────────────

@dataclass
class AgentAction:
    """
    Immutable decision emitted by AgentController.evaluate().

    Fields
    ------
    action_type : ActionType
        One of the six allowed actions.
    target_poi : str | None
        Name of the POI the action applies to (None for day-level actions).
    reasoning : str
        One-line deterministic explanation (logged to ShortTermMemory).
    parameters : dict
        Extra key-value context consumed by ExecutionLayer.
        Examples:
          DEFER_POI        → {"cause": "crowd", "crowd_level": 0.82}
          REPLACE_POI      → {"cause": "weather", "category_hint": "indoor"}
          RELAX_CONSTRAINT → {"constraint": "max_travel_min", "old": 60, "new": 90}
          REOPTIMIZE_DAY   → {"deprioritize_outdoor": True}
    """

    action_type: ActionType
    target_poi:  Optional[str] = None
    reasoning:   str = ""
    parameters:  dict = field(default_factory=dict)

    # ── Safety invariant ──────────────────────────────────────────────────────
    # The agent is NOT allowed to represent multi-stop deletions, hotel changes,
    # city changes, or budget mutations via this schema.  Any attempt to sneak
    # those through ``parameters`` must be caught by ExecutionLayer guardrails.

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "target_poi":  self.target_poi,
            "reasoning":   self.reasoning,
            "parameters":  dict(self.parameters),
        }

    def __repr__(self) -> str:  # pragma: no cover
        poi = f" → {self.target_poi}" if self.target_poi else ""
        return f"AgentAction({self.action_type.value}{poi}: {self.reasoning})"

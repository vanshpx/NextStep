"""
modules/reoptimization/agents/base_agent.py
----------------------------------------------
Base class and shared context for all specialist agents.

Every agent:
  1. Receives an ``AgentContext`` (read-only snapshot + event metadata).
  2. Returns an ``AgentAction`` (typed, immutable, logged).
  3. NEVER mutates state — only ``ExecutionLayer`` may do that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from modules.reoptimization.agent_action import AgentAction
from modules.reoptimization.agent_controller import AgentObservation


# ── Shared context bundle ─────────────────────────────────────────────────────

@dataclass
class AgentContext:
    """
    Read-only context bundle passed to every specialist agent.

    Fields
    ------
    observation : AgentObservation
        Live snapshot (itinerary, time, location, budget, disruptions, prefs).
    event_type : str
        The triggering event — e.g. ``"crowd"``, ``"weather"``, ``"budget"``,
        ``"explain"``, ``"slower"``.  Empty string when auto-detected.
    user_input : str
        Raw user text (if any).
    parameters : dict
        Extra CLI / caller-supplied key-value pairs.
    """

    observation: AgentObservation
    event_type:  str  = ""
    user_input:  str  = ""
    parameters:  dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type":  self.event_type,
            "user_input":  self.user_input,
            "parameters":  self.parameters,
            "observation": self.observation.to_dict(),
        }


# ── Abstract base ────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """
    Abstract base for every specialist agent.

    Subclasses **must** define:
      - ``AGENT_NAME``  — short identifier (e.g. ``"DisruptionAgent"``).
      - ``SYSTEM_PROMPT`` — the system prompt that governs the agent.
      - ``evaluate(context)`` — deterministic decision → ``AgentAction``.
    """

    AGENT_NAME:    str = "BaseAgent"
    SYSTEM_PROMPT: str = ""

    @abstractmethod
    def evaluate(self, context: AgentContext) -> AgentAction:
        """
        Given a context, return exactly one AgentAction.
        Deterministic: same context → same action.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.AGENT_NAME}"

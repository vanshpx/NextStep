"""modules/reoptimization/agents — Multi-agent architecture for trip re-optimization.

Agent hierarchy:
  OrchestratorAgent  →  routes to one of:
    PlanningAgent      — schedule-level replanning (REOPTIMIZE_DAY, RELAX_CONSTRAINT)
    DisruptionAgent    — crowd / weather / traffic disruptions
    BudgetAgent        — budget overrun detection and cost optimisation
    PreferenceAgent    — user preference changes mid-trip
    MemoryAgent        — disruption pattern analysis and memory logging
    ExplanationAgent   — human-readable explanation of recent decisions

  AgentDispatcher    — orchestrate → specialist → ExecutionLayer pipeline
"""

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agents.orchestrator_agent import (
    OrchestratorAgent, OrchestratorResult,
)
from modules.reoptimization.agents.disruption_agent import DisruptionAgent
from modules.reoptimization.agents.planning_agent import PlanningAgent
from modules.reoptimization.agents.budget_agent import BudgetAgent
from modules.reoptimization.agents.preference_agent import PreferenceAgent
from modules.reoptimization.agents.memory_agent import MemoryAgent
from modules.reoptimization.agents.explanation_agent import ExplanationAgent
from modules.reoptimization.agents.agent_dispatcher import (
    AgentDispatcher, DispatchResult,
)

__all__ = [
    "BaseAgent",
    "AgentContext",
    "OrchestratorAgent",
    "OrchestratorResult",
    "DisruptionAgent",
    "PlanningAgent",
    "BudgetAgent",
    "PreferenceAgent",
    "MemoryAgent",
    "ExplanationAgent",
    "AgentDispatcher",
    "DispatchResult",
]

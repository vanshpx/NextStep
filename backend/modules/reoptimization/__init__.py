"""modules/reoptimization — Real-time itinerary re-optimization."""

from modules.reoptimization.trip_state import TripState
from modules.reoptimization.event_handler import EventHandler, EventType, ReplanDecision
from modules.reoptimization.condition_monitor import ConditionMonitor, ConditionThresholds
from modules.reoptimization.partial_replanner import PartialReplanner
from modules.reoptimization.crowd_advisory import CrowdAdvisory, CrowdAdvisoryResult
from modules.reoptimization.weather_advisor import WeatherAdvisor, WeatherAdvisoryResult
from modules.reoptimization.traffic_advisor import TrafficAdvisor, TrafficAdvisoryResult
from modules.reoptimization.user_edit_handler import (
    UserEditHandler, DislikeResult, ReplaceResult, SkipResult,
    AlternativeOption,
)
from modules.reoptimization.hunger_fatigue_advisor import (
    HungerFatigueAdvisor, HungerAdvisoryResult, FatigueAdvisoryResult,
    MealOption,
)
from modules.reoptimization.session import ReOptimizationSession
from modules.reoptimization.agent_action import ActionType, AgentAction
from modules.reoptimization.agent_controller import AgentController, AgentObservation
from modules.reoptimization.execution_layer import ExecutionLayer, ExecutionResult
from modules.reoptimization.alternative_generator import (
    AlternativeGenerator, AlternativeOption,
)
from modules.reoptimization.agents import (
    BaseAgent, AgentContext,
    OrchestratorAgent, OrchestratorResult,
    DisruptionAgent, PlanningAgent, BudgetAgent,
    PreferenceAgent, MemoryAgent, ExplanationAgent,
    AgentDispatcher, DispatchResult,
)

__all__ = [
    "TripState",
    "EventHandler",
    "EventType",
    "ReplanDecision",
    "ConditionMonitor",
    "ConditionThresholds",
    "PartialReplanner",
    "CrowdAdvisory",
    "CrowdAdvisoryResult",
    "WeatherAdvisor",
    "WeatherAdvisoryResult",
    "TrafficAdvisor",
    "TrafficAdvisoryResult",
    "UserEditHandler",
    "DislikeResult",
    "ReplaceResult",
    "SkipResult",
    "AlternativeOption",
    "HungerFatigueAdvisor",
    "HungerAdvisoryResult",
    "FatigueAdvisoryResult",
    "MealOption",
    "ReOptimizationSession",
    "AlternativeGenerator",
    "AlternativeOption",
    "ActionType",
    "AgentAction",
    "AgentController",
    "AgentObservation",
    "ExecutionLayer",
    "ExecutionResult",
    # Multi-agent architecture
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

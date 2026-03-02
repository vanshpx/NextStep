from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.enums import DisruptionType
from core.models import Task

@dataclass
class DisruptionEvent:
    type: DisruptionType
    task_id: Optional[str]
    detected_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ReoptOption:
    id: str
    description: str
    new_future_tasks: List[Task]
    # Rule: I will validate logic in ReoptimizationAgent, here just pure data structure.

@dataclass
class ReoptimizationProposal:
    disruption: DisruptionEvent
    options: List[ReoptOption]
    needs_confirmation: bool

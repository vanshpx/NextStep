from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from core.enums import TaskStatus, CompletionType

@dataclass
class Task:
    id: str
    title: str
    location: str
    start_time: datetime
    end_time: datetime
    status: TaskStatus = TaskStatus.PLANNED
    completion: CompletionType = CompletionType.NONE
    
    def __post_init__(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")

@dataclass
class Itinerary:
    tasks: List[Task] = field(default_factory=list)
    
    def __post_init__(self):
        # Invariant: tasks sorted by start_time
        # Support tuple or list input
        self.tasks = list(self.tasks)
        self.tasks.sort(key=lambda x: x.start_time)
        # If we want strict immutability, we might convert back to tuple?
        # But type hint says List.
        # However, calling with tuple(copied_tasks) implies we passed a tuple.
        # If I convert to list here, it runs.
        # But user requested "return Itinerary(tasks=tuple(copied_tasks))".
        # Does the user want the attribute to STAY a tuple?
        # If so, I should convert back to tuple.
        # But type hint `List[Task]`?
        # Python type hints are ignored at runtime.
        # I will leave it as list to match type hint and allow sorting,
        # UNLESS user strictly implies immutable attribute.
        # "snapshot protection... get_state_snapshot must return Itinerary(tasks=tuple(copied_tasks))"
        # This implies the CALLER passes a tuple.
        # If Itinerary converts it to list, protection is reduced (it becomes mutable list in the snapshot).
        # But snapshot is frozen.
        # If snapshot is frozen, `itinerary` field is read-only.
        # But `itinerary.tasks` (list) is mutable.
        # To be truly distinct, `get_state_snapshot` copies them.
        # If `Itinerary` converts to list, it's a new list (because we did `list(self.tasks)`).
        # So it is safe.


@dataclass(frozen=True)
class StateSnapshot:
    current_time: datetime
    itinerary: Itinerary

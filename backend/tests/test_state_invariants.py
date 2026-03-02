import pytest
from datetime import datetime, timedelta
from dataclasses import replace
from typing import List

from core.models import Task, Itinerary, StateSnapshot
from core.enums import TaskStatus, CompletionType, DisruptionType
from core.events import ReoptOption, DisruptionEvent
from agents.state_agent import StateAgent

# Helper
def create_task(id: str, start_h: int, end_h: int, base_time: datetime) -> Task:
    return Task(
        id=id,
        title=f"Task {id}",
        location="Test Loc",
        start_time=base_time + timedelta(hours=start_h),
        end_time=base_time + timedelta(hours=end_h)
    )

@pytest.fixture
def base_time():
    return datetime(2025, 1, 1, 10, 0) # 10:00 AM

@pytest.fixture
def agent(base_time):
    # Initial State: Empty or simple
    snapshot = StateSnapshot(current_time=base_time, itinerary=Itinerary(tasks=[]))
    return StateAgent(snapshot)

def test_explicit_immutability(base_time):
    # Setup
    t1 = create_task("T1", 0, 1, base_time) # 10-11
    t2 = create_task("T2", 2, 3, base_time) # 12-13
    
    snapshot = StateSnapshot(current_time=base_time, itinerary=Itinerary(tasks=[t1, t2]))
    agent = StateAgent(snapshot)
    
    # Advance into T1 (10:30)
    agent.advance_time(30)
    agent.confirm_task("T1")
    
    # Advance past T1 (11:30)
    agent.advance_time(60)
    
    # Apply Proposal adjusting future
    # New task T3 (12:30-13:30) replaces T2 (12-13)
    t3 = create_task("T3", 2.5, 3.5, base_time)
    option = ReoptOption(id="opt1", description="desc", new_future_tasks=[t3])
    
    agent.apply_proposal(option)
    
    # Assert
    final = agent.get_state_snapshot()
    ids = [t.id for t in final.itinerary.tasks]
    assert "T1" in ids, "Explicit task T1 should persist"
    assert "T3" in ids
    assert "T2" not in ids
    
    preserved_t1 = next(t for t in final.itinerary.tasks if t.id == "T1")
    assert preserved_t1.status == TaskStatus.COMPLETED
    assert preserved_t1.completion == CompletionType.EXPLICIT

def test_rollback_survival(base_time):
    t1 = create_task("T1", 0, 1, base_time) # 10-11
    snapshot = StateSnapshot(current_time=base_time, itinerary=Itinerary(tasks=[t1]))
    agent = StateAgent(snapshot)
    
    # Advance past end (12:00 -> +2h)
    agent.advance_time(120)
    
    s = agent.get_state_snapshot()
    t1_missed = s.itinerary.tasks[0]
    assert t1_missed.status == TaskStatus.MISSED
    assert t1_missed.completion == CompletionType.IMPLICIT
    
    # Rollback
    agent.rollback_implicit("T1")
    
    s2 = agent.get_state_snapshot()
    t1_rolled = s2.itinerary.tasks[0]
    assert t1_rolled.status == TaskStatus.PLANNED, "Should revert to PLANNED"
    assert t1_rolled.completion == CompletionType.NONE, "Should obey Persistent Rollback"

def test_future_only_replacement(base_time):
    # T1 Past (8-9), T2 Active (9-11), T3 Future (12-13)
    # Current time: 10:00
    t1 = create_task("T1", -2, -1, base_time)
    t2 = create_task("T2", -1, 1, base_time)
    t3 = create_task("T3", 2, 3, base_time)
    
    snapshot = StateSnapshot(current_time=base_time, itinerary=Itinerary(tasks=[t1, t2, t3]))
    agent = StateAgent(snapshot)
    
    # Verify Initial State
    s = agent.get_state_snapshot()
    assert s.itinerary.tasks[1].id == "T2"
    
    # Proposal: Replace T3 with T4 (13-14)
    t4 = create_task("T4", 3, 4, base_time)
    option = ReoptOption(id="opt2", description="replace future", new_future_tasks=[t4])
    
    agent.apply_proposal(option)
    
    final = agent.get_state_snapshot()
    ids = [t.id for t in final.itinerary.tasks]
    
    assert "T1" in ids, "Past task preserved"
    assert "T2" in ids, "Active task preserved"
    assert "T3" not in ids, "Future task replaced"
    assert "T4" in ids, "New future task added"

def test_active_protection(base_time):
    # T1 Active (9-11). Current 10:00.
    t1 = create_task("T1", -1, 1, base_time)
    snapshot = StateSnapshot(current_time=base_time, itinerary=Itinerary(tasks=[t1]))
    agent = StateAgent(snapshot)
    
    # Proposal tries to insert T2 (10:30-11:30) overlapping Active End
    t2 = create_task("T2", 0.5, 1.5, base_time) # Starts at 10:30
    option = ReoptOption(id="fail", description="fail", new_future_tasks=[t2])
    
    with pytest.raises(ValueError, match="overlaps with preserved task"):
        agent.apply_proposal(option)

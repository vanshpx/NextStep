from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import replace

from core.enums import TaskStatus, CompletionType
from core.models import StateSnapshot, Task, Itinerary
from core.events import ReoptOption

class StateAgent:
    def __init__(self, initial_snapshot: StateSnapshot):
        self._current_time = initial_snapshot.current_time
        self._tasks: List[Task] = [
            replace(t) for t in initial_snapshot.itinerary.tasks
        ]
        self._sort_tasks()

    def _sort_tasks(self):
        self._tasks.sort(key=lambda x: x.start_time)

    def _get_task(self, task_id: str) -> Optional[Task]:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def get_state_snapshot(self) -> StateSnapshot:
        # Snapshot Protection
        copied_tasks = tuple(replace(t) for t in self._tasks)
        # Note: We rely on models.py being lenient about tuple vs List typing at runtime
        # or we cast to list if absolutely required, but tuple is requested.
        return StateSnapshot(
            current_time=self._current_time,
            itinerary=Itinerary(tasks=copied_tasks) 
        )

    def advance_time(self, minutes: int) -> None:
        if minutes < 0:
            raise ValueError("Time can only move forward")
        
        previous_time = self._current_time
        new_time = previous_time + timedelta(minutes=minutes)
        self._current_time = new_time
        
        for task in self._tasks:
            if task.completion == CompletionType.NONE:
                # Edge-Triggered Implicit Failure
                if previous_time < task.end_time <= new_time:
                    task.completion = CompletionType.IMPLICIT
                    task.status = TaskStatus.MISSED
            
            self._update_time_status(task)

    def confirm_task(self, task_id: str) -> None:
        task = self._get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Rule 1: Allow confirmation only if Active Or Recovered via Rollback
        # Strict constraints:
        # if completion == IMPLICIT -> Fail (Must rollback first)
        if task.completion == CompletionType.IMPLICIT:
             raise ValueError("Cannot confirm missed task directly. Perform rollback first.")
        
        # Active: start <= current <= end
        is_active = task.start_time <= self._current_time <= task.end_time
        
        # Recovered: current > end AND completion == NONE (Logic implies rollback happened)
        is_recovered = (self._current_time > task.end_time) and (task.completion == CompletionType.NONE)
        
        if not (is_active or is_recovered):
             # Future: start > current
             if self._current_time < task.start_time:
                  raise ValueError("Cannot confirm future task before start time")
             # Catch-all
             raise ValueError("Validation failed: Task not in active or recovered state")

        task.completion = CompletionType.EXPLICIT
        task.status = TaskStatus.COMPLETED

    def rollback_implicit(self, task_id: str) -> None:
        task = self._get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Rule 2: Allow rollback only if IMPLICIT and END <= CURRENT
        if task.completion != CompletionType.IMPLICIT:
            raise ValueError("Can only rollback implicit completion")
            
        if task.end_time > self._current_time:
             # Should be impossible if implicit edge triggered correctly, 
             # but strictly enforces invariants.
             raise ValueError("Cannot rollback task that hasn't ended")
            
        task.completion = CompletionType.NONE
        task.status = TaskStatus.PLANNED
        # Next update_time_status loop will see NONE + after end -> keep current status (PLANNED).

    def apply_proposal(self, option: ReoptOption) -> None:
        # Preservation logic (Same as before)
        preserved_tasks = []
        for t in self._tasks:
            # Preserve PAST (end <= current) OR ACTIVE (start <= current < end)
            is_past = t.end_time <= self._current_time
            is_active = t.start_time <= self._current_time < t.end_time
            if is_past or is_active:
                preserved_tasks.append(t)
        
        # History Protection (Max Explicit End)
        max_explicit_end = self._current_time
        for t in preserved_tasks:
            if t.completion == CompletionType.EXPLICIT:
                if t.end_time > max_explicit_end:
                    max_explicit_end = t.end_time
        
        # Validation
        for new_t in option.new_future_tasks:
            if new_t.start_time <= self._current_time:
                 raise ValueError(f"New task {new_t.id} starts in past/present")
            if new_t.start_time < max_explicit_end:
                 raise ValueError(f"New task {new_t.id} overlaps with explicit history")
            for p in preserved_tasks:
                if new_t.start_time < p.end_time:
                     raise ValueError(f"New task {new_t.id} overlaps with preserved task {p.id}")

        new_list = preserved_tasks + option.new_future_tasks
        new_list.sort(key=lambda x: x.start_time)
        
        # Rule 3: STRICT Ordering Invariant (Monotonic increasing intervals)
        for i in range(len(new_list) - 1):
            t1 = new_list[i]
            t2 = new_list[i+1]
            if t1.end_time > t2.start_time:
                 raise ValueError(f"Overlapping tasks: {t1.id} vs {t2.id}")
            # Ensure strict ordering
            if t1.start_time > t2.start_time: # Should be sorted
                 raise ValueError("Ordering invariant violated")

        self._tasks = new_list
        for t in self._tasks:
            self._update_time_status(t)

    def _update_time_status(self, task: Task) -> None:
        if task.completion == CompletionType.EXPLICIT:
            task.status = TaskStatus.COMPLETED
            return
            
        if task.completion == CompletionType.IMPLICIT:
            task.status = TaskStatus.MISSED
            return
            
        if self._current_time < task.start_time:
            task.status = TaskStatus.PLANNED
        elif task.start_time <= self._current_time < task.end_time:
            task.status = TaskStatus.ACTIVE
        else:
            # Persistent Rollback (completion=NONE, time >= end)
            pass

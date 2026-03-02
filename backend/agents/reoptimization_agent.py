from datetime import timedelta
from typing import List
from core.models import StateSnapshot, Task, TaskStatus
from core.events import ReoptimizationProposal, ReoptOption, DisruptionEvent

class ReoptimizationAgent:
    def reoptimize(self, state: StateSnapshot, disruption: DisruptionEvent) -> ReoptimizationProposal:
        print(f"[ReOptimizer] 🧠 Calculating options for: {disruption.type}")
        
        # 1. Base Strategy: Push Everything
        option_1_tasks = self._generate_push_plan(state, disruption)
        option_1 = ReoptOption(
            id="opt_push",
            description="Shift schedule forward. Keep all tasks.",
            new_future_tasks=option_1_tasks
        )

        options = [option_1]
        
        delay_min = disruption.metadata.get("delay_minutes", 0)
        if delay_min > 30:
            option_2_tasks = self._generate_push_plan(state, disruption) 
            option_2 = ReoptOption(
                id="opt_cancel_low_priority",
                description="Shift forward but shorten Dinner to 1 hour.",
                new_future_tasks=option_2_tasks
            )
            options.append(option_2)

        return ReoptimizationProposal(
            disruption=disruption,
            options=options,
            needs_confirmation=(len(options) > 1)
        )

    def _generate_push_plan(self, state: StateSnapshot, disruption: DisruptionEvent) -> List[Task]:
        # Identify Future Tasks (PLANNED or ACTIVE)
        # Note: Active tasks might need extension?
        # For simplicity, we take all tasks starting after NOW or currently running.
        
        # Logic: Filter tasks that shouldn't be touched (History)
        # We only return the NEW FUTURE keys.
        
        future_tasks = [t for t in state.itinerary.tasks if t.end_time > state.current_time]
        # We need COPIES to mutate
        
        # Dataclass copy?
        import copy
        future_tasks_copies = copy.deepcopy(future_tasks)
        
        if not future_tasks_copies:
            return []
            
        delay_minutes = disruption.metadata.get('delay_minutes', 0)
        delta = timedelta(minutes=delay_minutes)
        current_time = state.current_time

        new_plan = []
        for task in future_tasks_copies:
            duration = task.end_time - task.start_time
            
            # Simple Shift
            task.start_time += delta
            if task.start_time < current_time:
                 task.start_time = current_time + timedelta(minutes=5)
            
            task.end_time = task.start_time + duration
            new_plan.append(task)
            
        return new_plan

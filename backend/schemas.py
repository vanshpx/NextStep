from pydantic import BaseModel
from typing import List, Dict, Optional
from enum import Enum
from typing import Literal

class UserPreferences(BaseModel):
    destination: str
    days: int
    interests: List[str]
    pace: str
    budget_level: str  # low | medium | high
    traveling_with: Literal["solo", "couple", "family", "friends"]
    suggestions: Optional[str]=None
    




class ActivityStatus(str, Enum):
    planned = "planned"
    completed = "completed"
    skipped = "skipped"
    failed = "failed"



class Activity(BaseModel):
    activity_id: str
    name: str
    category: str
    estimated_duration_min: int
    day: int
    start_time: str
    end_time: str
    budget_level: str
    status: ActivityStatus = ActivityStatus.planned


class Itinerary(BaseModel):
    version: int
    days: Dict[str, List[Activity]]

class TripState(BaseModel):
    trip_id: str
    version: int
    days: Dict[str, List[Activity]]


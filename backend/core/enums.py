from enum import Enum, auto

class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"

class CompletionType(str, Enum):
    NONE = "NONE"
    IMPLICIT = "IMPLICIT"
    EXPLICIT = "EXPLICIT"

class DisruptionType(str, Enum):
    DELAY = "DELAY"
    WEATHER = "WEATHER"
    CLOSED = "CLOSED"
    FATIGUE = "FATIGUE"
    LATE_ARRIVAL = "LATE_ARRIVAL"

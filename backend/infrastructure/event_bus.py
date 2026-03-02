import asyncio
from typing import Callable, Dict, List, Any, Awaitable
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Event:
    topic: str
    payload: Any
    timestamp: datetime = datetime.now()

class InfrastructureEventBus:
    """
    In-memory implementation.
    Defines its own Transport Event type to keep Core pure.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Awaitable[None]]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Event], Awaitable[None]]):
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    async def publish(self, topic: str, payload: Any):
        event = Event(topic=topic, payload=payload)
        if topic in self._subscribers:
            await asyncio.gather(*[handler(event) for handler in self._subscribers[topic]])

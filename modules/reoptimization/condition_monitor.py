"""
modules/reoptimization/condition_monitor.py
---------------------------------------------
Monitors real-time environmental conditions (crowd, traffic, weather) and
fires DisruptionEvents when user-specific tolerance thresholds are exceeded.

Thresholds are NOT hard-coded — they are LEARNED from the user's SoftConstraints
so that a crowd-averse traveler gets rerouted earlier than a packed-schedule tourist.

Threshold derivation rules
───────────────────────────
CROWD:
  avoid_crowds=True                  → 0.35  (very sensitive)
  avoid_crowds=False                 → 0.70  (tolerant)

TRAFFIC:
  pace_preference="relaxed"          → 0.30  (+0 if heavy_travel_penalty)
  pace_preference="moderate"         → 0.55
  pace_preference="packed"           → 0.80
  heavy_travel_penalty=True          → threshold *= 0.80 (more sensitive)

WEATHER (severity 0–1: clear=0, cloudy=0.3, rainy=0.6, stormy=1.0):
  If >50% of remaining attractions are outdoor  → 0.40
  Else                                          → 0.65
  preferred_time_of_day="morning"               → threshold *= 0.85
    (morning travellers are more disrupted by weather changes)

All thresholds are clamped to [0.15, 0.90].
"""

from __future__ import annotations
from dataclasses import dataclass

from schemas.constraints import SoftConstraints
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.reoptimization.event_handler import EventHandler, EventType, ReplanDecision
from modules.reoptimization.trip_state import TripState


# ── Weather severity mapping ──────────────────────────────────────────────────

WEATHER_SEVERITY: dict[str, float] = {
    "clear":        0.00,
    "mostly_clear": 0.10,
    "cloudy":       0.30,
    "overcast":     0.45,
    "drizzle":      0.55,
    "rainy":        0.65,
    "heavy_rain":   0.80,
    "thunderstorm": 0.90,
    "stormy":       1.00,
    "hail":         1.00,
    "snow":         0.70,
    "blizzard":     1.00,
    "foggy":        0.40,
    "hot":          0.35,    # heat advisory
    "heatwave":     0.65,
}


@dataclass
class ConditionThresholds:
    """User-personalized tolerance thresholds derived from SoftConstraints."""
    crowd:   float   # trigger replan when crowd_level   > this
    traffic: float   # trigger replan when traffic_level > this
    weather: float   # trigger replan when weather_severity > this

    def describe(self) -> str:
        return (f"crowd>{self.crowd:.0%}  "
                f"traffic>{self.traffic:.0%}  "
                f"weather>{self.weather:.0%}")


class ConditionMonitor:
    """
    Derives tolerance thresholds from SoftConstraints and checks incoming
    environmental readings against them.

    Usage:
        monitor = ConditionMonitor(soft_constraints, remaining_attractions)
        events  = monitor.check(
            crowd_level=0.6,
            traffic_level=0.4,
            weather_condition="rainy",
            state=trip_state,
            next_stop_name="Riverfront Park",
            next_stop_is_outdoor=True,
        )
        for replan_decision in events:
            ...
    """

    def __init__(
        self,
        soft: SoftConstraints,
        remaining_attractions: list[AttractionRecord] | None = None,
        total_days: int = 1,
    ) -> None:
        self.soft = soft
        self._remaining = remaining_attractions or []
        self.total_days = total_days
        self.thresholds = self._derive_thresholds()
        self._event_handler = EventHandler()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_remaining(self, remaining: list[AttractionRecord]) -> None:
        """Call whenever remaining_attractions changes so weather threshold refreshes."""
        self._remaining = remaining
        self.thresholds = self._derive_thresholds()

    def update_total_days(self, total_days: int) -> None:
        """Update total trip days (used for crowd rescheduling decisions)."""
        self.total_days = total_days

    def check(
        self,
        state: TripState,
        crowd_level: float | None = None,
        traffic_level: float | None = None,
        weather_condition: str | None = None,
        next_stop_name: str = "",
        next_stop_is_outdoor: bool = False,
        estimated_traffic_delay_minutes: int = 0,
    ) -> list[ReplanDecision]:
        """
        Check current environmental readings against user thresholds.

        Args:
            state:                          Live TripState (mutated by handler).
            crowd_level:                    Float 0-1 or None if unavailable.
            traffic_level:                  Float 0-1 or None if unavailable.
            weather_condition:              String key from WEATHER_SEVERITY or None.
            next_stop_name:                 Name of the next planned stop.
            next_stop_is_outdoor:           Whether next stop is outdoor (for weather).
            estimated_traffic_delay_minutes:Extra minutes from current traffic.

        Returns:
            List of ReplanDecisions (empty if all conditions within tolerance).
        """
        decisions: list[ReplanDecision] = []

        # ── Crowd check ───────────────────────────────────────────────────────
        if crowd_level is not None and crowd_level > self.thresholds.crowd:
            # Look up stop-specific details to enrich the crowd payload so the
            # event handler can choose the right rescheduling strategy.
            stop_record = next(
                (a for a in self._remaining if a.name == next_stop_name), None
            )
            min_duration = (
                getattr(stop_record, "min_visit_duration_minutes", 60)
                if stop_record else 60
            )
            importance = (
                getattr(stop_record, "historical_importance", "")
                if stop_record else ""
            )
            d = self._event_handler.handle(
                EventType.ENV_CROWD_HIGH,
                {
                    "stop_name":           next_stop_name,
                    "crowd_level":         crowd_level,
                    "threshold":           self.thresholds.crowd,
                    "total_days":          self.total_days,
                    "remaining_minutes":   state.remaining_minutes_today(),
                    "min_visit_duration":  min_duration,
                    "place_importance":    importance,
                },
                state,
            )
            decisions.append(d)

        # ── Traffic check ─────────────────────────────────────────────────────
        if traffic_level is not None and traffic_level > self.thresholds.traffic:
            d = self._event_handler.handle(
                EventType.ENV_TRAFFIC_HIGH,
                {
                    "stop_name":         next_stop_name,
                    "traffic_level":     traffic_level,
                    "threshold":         self.thresholds.traffic,
                    "delay_minutes":     estimated_traffic_delay_minutes,
                    "current_lat":       state.current_lat,
                    "current_lon":       state.current_lon,
                    "remaining_minutes": state.remaining_minutes_today(),
                },
                state,
            )
            decisions.append(d)

        # ── Weather check ─────────────────────────────────────────────────────
        if weather_condition is not None:
            severity = WEATHER_SEVERITY.get(weather_condition.lower(), 0.0)
            if severity > self.thresholds.weather:
                d = self._event_handler.handle(
                    EventType.ENV_WEATHER_BAD,
                    {
                        "severity":          severity,
                        "threshold":         self.thresholds.weather,
                        "condition":         weather_condition,
                        "affects_outdoor":   next_stop_is_outdoor,
                        "current_lat":       state.current_lat,
                        "current_lon":       state.current_lon,
                        "remaining_minutes": state.remaining_minutes_today(),
                    },
                    state,
                )
                decisions.append(d)

        return decisions

    # ── Threshold derivation ─────────────────────────────────────────────────

    def _derive_thresholds(self) -> ConditionThresholds:
        crowd   = self._crowd_threshold()
        traffic = self._traffic_threshold()
        weather = self._weather_threshold()
        return ConditionThresholds(crowd=crowd, traffic=traffic, weather=weather)

    def _crowd_threshold(self) -> float:
        """
        avoid_crowds=True  → 0.35  (trigger replan quickly)
        avoid_crowds=False → 0.70  (only replan when very crowded)
        """
        base = 0.35 if self.soft.avoid_crowds else 0.70
        return float(max(0.15, min(0.90, base)))

    def _traffic_threshold(self) -> float:
        """
        Pace preference sets base; heavy_travel_penalty reduces tolerance.
        """
        pace_map = {"relaxed": 0.30, "moderate": 0.55, "packed": 0.80}
        base = pace_map.get(self.soft.pace_preference, 0.55)
        if getattr(self.soft, "heavy_travel_penalty", True):
            base *= 0.80
        return float(max(0.15, min(0.90, base)))

    def _weather_threshold(self) -> float:
        """
        If most remaining stops are outdoor, set a lower threshold
        (disruption is more impactful). Morning travellers also get a
        slight reduction in tolerance.
        """
        outdoor_count = sum(
            1 for a in self._remaining if getattr(a, "is_outdoor", False)
        )
        total = max(len(self._remaining), 1)
        outdoor_ratio = outdoor_count / total

        base = 0.40 if outdoor_ratio > 0.5 else 0.65
        if getattr(self.soft, "preferred_time_of_day", "") == "morning":
            base *= 0.85
        return float(max(0.15, min(0.90, base)))

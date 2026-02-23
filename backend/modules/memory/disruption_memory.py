"""
modules/memory/disruption_memory.py
--------------------------------------
Stores in-session disruption insights for the Memory Module.

Learns and surfaces three categories of traveller behaviour:
  1. Weather tolerance     — which conditions the traveller accepted vs. avoided
  2. Delay tolerance       — at what delay magnitude replans were accepted
  3. Replacement patterns  — which original stops were replaced, and by what

All data is in-memory for the current session only (no persistence to disk):
the session is typically ≤ 1 day. If multi-day memory is required, call
serialize() and load the JSON into the next session via deserialize().

Memory Module integration
─────────────────────────
This class is intended to be stored inside ReOptimizationSession:
    self._disruption_memory = DisruptionMemory()

And updated after every disruption event:
    session._disruption_memory.record_weather(...)
    session._disruption_memory.record_traffic(...)
    session._disruption_memory.record_replacement(...)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import json


# ─────────────────────────────────────────────────────────────────────────────
# Record types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeatherRecord:
    """One weather disruption event and its outcome."""
    condition:      str
    severity:       float
    threshold:      float
    blocked_count:  int
    deferred_count: int
    replan_accepted: bool   # True if user continued; False if user overrode
    alternatives_used: list[str] = field(default_factory=list)


@dataclass
class TrafficRecord:
    """One traffic disruption event and its outcome."""
    traffic_level:   float
    threshold:       float
    delay_minutes:   int
    delay_factor:    float
    deferred_stops:  list[str] = field(default_factory=list)
    replaced_stops:  list[str] = field(default_factory=list)
    replan_accepted: bool = True


@dataclass
class ReplacementRecord:
    """One stop-replacement event."""
    original_stop:    str
    replacement_stop: str
    reason:           str   # "weather" | "traffic" | "crowd" | "user_skip"
    S_pti_original:   float = 0.0
    S_pti_replacement: float = 0.0


@dataclass
class HungerRecord:
    """One hunger disruption event and its outcome."""
    trigger_time:    str
    hunger_level:    float
    action_taken:    str           # "meal_inserted" | "advisory_only"
    restaurant_name: str | None    # name of inserted/selected restaurant, if any
    S_pti_inserted:  float | None  # S_pti of the meal stop
    user_response:   str = "accepted"  # "accepted" | "skipped"


@dataclass
class FatigueRecord:
    """One fatigue disruption event and its outcome."""
    trigger_time:   str
    fatigue_level:  float
    action_taken:   str           # "rest_inserted" | "replan_triggered"
    rest_duration:  int | None    # minutes of rest taken
    stops_deferred: list[str] = field(default_factory=list)
    user_response:  str = "accepted"  # "accepted" | "skipped"


# ─────────────────────────────────────────────────────────────────────────────
# DisruptionMemory
# ─────────────────────────────────────────────────────────────────────────────

class DisruptionMemory:
    """
    In-session store for disruption insights.

    Usage:
        mem = DisruptionMemory()
        mem.record_weather("heavy_rain", 0.80, 0.65, blocked=2, deferred=1,
                           accepted=True, alternatives=["City Museum"])
        mem.record_traffic(0.70, 0.44, delay_minutes=35, delay_factor=1.7,
                           deferred=["Heritage Fort"], replaced=["Riverfront Park"])
        mem.record_replacement("Riverfront Park", "City Museum",
                                reason="weather", S_orig=0.72, S_rep=0.88)
        print(mem.summarize())
    """

    def __init__(self) -> None:
        self.weather_history:     list[WeatherRecord]     = []
        self.traffic_history:     list[TrafficRecord]     = []
        self.replacement_history: list[ReplacementRecord] = []
        self.hunger_history:      list[HungerRecord]      = []
        self.fatigue_history:     list[FatigueRecord]     = []

    # ── Record methods ────────────────────────────────────────────────────────

    def record_weather(
        self,
        condition:       str,
        severity:        float,
        threshold:       float,
        blocked:         int,
        deferred:        int,
        accepted:        bool = True,
        alternatives:    list[str] | None = None,
    ) -> None:
        """Store outcome of a weather disruption event."""
        self.weather_history.append(WeatherRecord(
            condition          = condition,
            severity           = severity,
            threshold          = threshold,
            blocked_count      = blocked,
            deferred_count     = deferred,
            replan_accepted    = accepted,
            alternatives_used  = alternatives or [],
        ))

    def record_traffic(
        self,
        traffic_level:   float,
        threshold:       float,
        delay_minutes:   int,
        delay_factor:    float,
        deferred:        list[str] | None = None,
        replaced:        list[str] | None = None,
        accepted:        bool = True,
    ) -> None:
        """Store outcome of a traffic disruption event."""
        self.traffic_history.append(TrafficRecord(
            traffic_level    = traffic_level,
            threshold        = threshold,
            delay_minutes    = delay_minutes,
            delay_factor     = delay_factor,
            deferred_stops   = deferred or [],
            replaced_stops   = replaced or [],
            replan_accepted  = accepted,
        ))

    def record_replacement(
        self,
        original:    str,
        replacement: str,
        reason:      str,
        S_orig:      float = 0.0,
        S_rep:       float = 0.0,
    ) -> None:
        """Store one stop-replacement pair."""
        self.replacement_history.append(ReplacementRecord(
            original_stop      = original,
            replacement_stop   = replacement,
            reason             = reason,
            S_pti_original     = S_orig,
            S_pti_replacement  = S_rep,
        ))

    def record_hunger(
        self,
        trigger_time:    str,
        hunger_level:    float,
        action_taken:    str,
        restaurant_name: str | None = None,
        S_pti_inserted:  float | None = None,
        user_response:   str = "accepted",
    ) -> None:
        """Store outcome of a hunger disruption event."""
        self.hunger_history.append(HungerRecord(
            trigger_time    = trigger_time,
            hunger_level    = hunger_level,
            action_taken    = action_taken,
            restaurant_name = restaurant_name,
            S_pti_inserted  = S_pti_inserted,
            user_response   = user_response,
        ))

    def record_fatigue(
        self,
        trigger_time:   str,
        fatigue_level:  float,
        action_taken:   str,
        rest_duration:  int | None = None,
        stops_deferred: list[str] | None = None,
        user_response:  str = "accepted",
    ) -> None:
        """Store outcome of a fatigue disruption event."""
        self.fatigue_history.append(FatigueRecord(
            trigger_time   = trigger_time,
            fatigue_level  = fatigue_level,
            action_taken   = action_taken,
            rest_duration  = rest_duration,
            stops_deferred = stops_deferred or [],
            user_response  = user_response,
        ))

    def record_generic(
        self,
        disruption_type: str,
        severity:        float,
        action_taken:    str,
        user_response:   str,
        impacted_stops:  list | None = None,
    ) -> None:
        """
        Store a crowd / weather / traffic disruption outcome after the
        user has responded via the approval gate (APPROVE / REJECT / MODIFY).
        Mapped into replacement_history so it surfaces in summarize().
        """
        for stop in (impacted_stops or []):
            self.replacement_history.append(ReplacementRecord(
                original_stop     = stop,
                replacement_stop  = "",
                reason            = f"{disruption_type}:{user_response}",
                S_pti_original    = severity,
                S_pti_replacement = 0.0,
            ))

    # ── Query helpers ─────────────────────────────────────────────────────────

    def weather_tolerance_level(self) -> float | None:
        """
        Inferred weather tolerance = lowest accepted severity / total events.
        Returns None if no events recorded yet.
        """
        accepted = [w for w in self.weather_history if w.replan_accepted]
        if not accepted:
            return None
        return min(w.severity for w in accepted)

    def delay_tolerance_minutes(self) -> float | None:
        """
        Inferred delay tolerance = average delay_minutes across accepted events.
        """
        accepted = [t for t in self.traffic_history if t.replan_accepted]
        if not accepted:
            return None
        return sum(t.delay_minutes for t in accepted) / len(accepted)

    def common_replacements(self) -> dict[str, list[str]]:
        """
        Map of original_stop → list of stops it was replaced by during the session.
        Useful for downstream personalization.
        """
        result: dict[str, list[str]] = {}
        for r in self.replacement_history:
            result.setdefault(r.original_stop, []).append(r.replacement_stop)
        return result

    # ── Summary ───────────────────────────────────────────────────────────────

    def summarize(self) -> dict:
        """Return a structured summary dict (for session.summary() integration)."""
        return {
            "weather_events":         len(self.weather_history),
            "weather_tolerance":      self.weather_tolerance_level(),
            "traffic_events":         len(self.traffic_history),
            "delay_tolerance_min":    self.delay_tolerance_minutes(),
            "hunger_events":          len(self.hunger_history),
            "fatigue_events":         len(self.fatigue_history),
            "replacements":           [
                {
                    "original":    r.original_stop,
                    "replacement": r.replacement_stop,
                    "reason":      r.reason,
                }
                for r in self.replacement_history
            ],
            "common_replacements":    self.common_replacements(),
        }

    # ── Serialization (multi-day persistence) ────────────────────────────────

    def serialize(self) -> str:
        """Export all records to a JSON string for cross-session storage."""
        return json.dumps({
            "weather": [
                {
                    "condition":       r.condition,
                    "severity":        r.severity,
                    "threshold":       r.threshold,
                    "blocked_count":   r.blocked_count,
                    "deferred_count":  r.deferred_count,
                    "accepted":        r.replan_accepted,
                    "alternatives":    r.alternatives_used,
                }
                for r in self.weather_history
            ],
            "traffic": [
                {
                    "traffic_level":  r.traffic_level,
                    "threshold":      r.threshold,
                    "delay_minutes":  r.delay_minutes,
                    "delay_factor":   r.delay_factor,
                    "deferred":       r.deferred_stops,
                    "replaced":       r.replaced_stops,
                    "accepted":       r.replan_accepted,
                }
                for r in self.traffic_history
            ],
            "replacements": [
                {
                    "original":    r.original_stop,
                    "replacement": r.replacement_stop,
                    "reason":      r.reason,
                    "S_orig":      r.S_pti_original,
                    "S_rep":       r.S_pti_replacement,
                }
                for r in self.replacement_history
            ],
            "hunger": [
                {
                    "trigger_time":    r.trigger_time,
                    "hunger_level":    r.hunger_level,
                    "action_taken":    r.action_taken,
                    "restaurant_name": r.restaurant_name,
                    "S_pti_inserted":  r.S_pti_inserted,
                    "user_response":   r.user_response,
                }
                for r in self.hunger_history
            ],
            "fatigue": [
                {
                    "trigger_time":   r.trigger_time,
                    "fatigue_level":  r.fatigue_level,
                    "action_taken":   r.action_taken,
                    "rest_duration":  r.rest_duration,
                    "stops_deferred": r.stops_deferred,
                    "user_response":  r.user_response,
                }
                for r in self.fatigue_history
            ],
        }, indent=2)

    @classmethod
    def deserialize(cls, json_str: str) -> "DisruptionMemory":
        """Reconstruct from a previously serialized JSON string."""
        mem  = cls()
        data = json.loads(json_str)
        for w in data.get("weather", []):
            mem.record_weather(
                w["condition"], w["severity"], w["threshold"],
                w["blocked_count"], w["deferred_count"],
                w["accepted"], w.get("alternatives", []),
            )
        for t in data.get("traffic", []):
            mem.record_traffic(
                t["traffic_level"], t["threshold"], t["delay_minutes"],
                t["delay_factor"], t.get("deferred", []), t.get("replaced", []),
                t["accepted"],
            )
        for r in data.get("replacements", []):
            mem.record_replacement(
                r["original"], r["replacement"], r["reason"],
                r.get("S_orig", 0.0), r.get("S_rep", 0.0),
            )
        for h in data.get("hunger", []):
            mem.record_hunger(
                h["trigger_time"], h["hunger_level"], h["action_taken"],
                h.get("restaurant_name"), h.get("S_pti_inserted"),
                h.get("user_response", "accepted"),
            )
        for f in data.get("fatigue", []):
            mem.record_fatigue(
                f["trigger_time"], f["fatigue_level"], f["action_taken"],
                f.get("rest_duration"), f.get("stops_deferred", []),
                f.get("user_response", "accepted"),
            )
        return mem

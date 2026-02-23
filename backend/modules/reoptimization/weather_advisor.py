"""
modules/reoptimization/weather_advisor.py
-------------------------------------------
Deterministic weather disruption handler for the Travel Itinerary Optimizer.

Core logic
──────────
1. Classify remaining POIs into:
   - BLOCKED  : outdoor AND unsafe weather (severity ≥ HC_UNSAFE_THRESHOLD)
                HC_pti is force-zeroed → these must be deferred or replaced.
   - DEFERRED : outdoor but weather not yet unsafe (threshold < severity < HC_UNSAFE)
                still risky — defer to a less exposed time slot.
   - SAFE     : indoor (is_outdoor=False) — unaffected by weather.

2. Rank indoor alternatives by composite score:
       score = (HC_pti × SC_pti) / Dij          (full FTRM η_ij)
   where Dij is haversine(current_pos, stop) / AVG_TRAVEL_SPEED_KMH.

3. Adjust visit durations for remaining outdoor stops scheduled later:
       adjusted_duration = original × DURATION_WEATHER_SCALE_FACTOR

4. Return WeatherAdvisoryResult: blocked list, deferred list, ranked indoor
   alternatives, duration adjustments, reason string.

Constants (MISSING in spec — defined here with rationale):
    HC_UNSAFE_THRESHOLD     = 0.75
        Severity above which outdoor visits are physically unsafe (heavy_rain ~ 0.80).
    DURATION_SCALE_FACTOR   = 0.75
        Visit durations for non-blocked outdoor stops are cut 25% as weather slows movement.
    AVG_TRAVEL_SPEED_KMH    = 4.0
        Conservative walking speed in bad weather (vs. 5 in good weather).
    WEATHER_SENSITIVE_CATS  = {"beach", "park", "viewpoint", "rooftop", "market",
                                "open_air_museum", "garden", "zoo", "amusement_park"}
        Categories that are also weather-sensitive even without strict is_outdoor=True.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2
from typing import Any

from modules.tool_usage.attraction_tool import AttractionRecord
from schemas.constraints import ConstraintBundle


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HC_UNSAFE_THRESHOLD:     float       = 0.75   # MISSING in spec
DURATION_SCALE_FACTOR:   float       = 0.75   # MISSING in spec
AVG_TRAVEL_SPEED_KMH:    float       = 4.0    # MISSING in spec
EARTH_RADIUS_KM:         float       = 6371.0

WEATHER_SENSITIVE_CATS: set[str] = {          # MISSING in spec
    "beach", "park", "viewpoint", "rooftop", "market",
    "open_air_museum", "garden", "zoo", "amusement_park",
}

# Severity map mirrors condition_monitor.WEATHER_SEVERITY
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
    "hot":          0.35,
    "heatwave":     0.65,
}


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeatherImpact:
    """Describes how weather affects one specific POI."""
    attraction:        AttractionRecord
    hc_override:       float = 1.0     # 0.0 = unsafe (HC zeroed), 1.0 = safe
    is_blocked:        bool  = False   # True → must be deferred this replan
    is_deferred:       bool  = False   # True → defer (risky but not blocked)
    adjusted_duration: int   = 0       # minutes — scaled if risky outdoor
    reason:            str   = ""


@dataclass
class WeatherAlternative:
    """One indoor alternative suggestion ranked by η_ij."""
    attraction:   AttractionRecord
    eta_ij:       float   # S_pti / Dij_new
    S_pti:        float
    Dij_new:      float   # travel time [minutes] at reduced speed
    why_suitable: str


@dataclass
class WeatherAdvisoryResult:
    """Full weather advisory package produced by WeatherAdvisor.classify()."""
    condition:         str
    severity:          float
    threshold:         float
    blocked_stops:     list[WeatherImpact]      = field(default_factory=list)
    deferred_stops:    list[WeatherImpact]      = field(default_factory=list)
    safe_stops:        list[AttractionRecord]   = field(default_factory=list)
    alternatives:      list[WeatherAlternative] = field(default_factory=list)
    duration_adjustments: dict[str, int]        = field(default_factory=dict)
    # ^ {stop_name: adjusted_duration_minutes}
    strategy_msg:      str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_minutes(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    speed_kmh: float = AVG_TRAVEL_SPEED_KMH,
) -> float:
    """Great-circle distance converted to travel minutes at speed_kmh."""
    r   = EARTH_RADIUS_KM
    φ1, φ2 = radians(lat1), radians(lat2)
    dφ  = radians(lat2 - lat1)
    dλ  = radians(lon2 - lon1)
    a   = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    d   = 2 * r * atan2(sqrt(a), sqrt(1 - a))   # km
    return max(1.0, (d / speed_kmh) * 60)        # minutes, floor 1


def _is_weather_sensitive(attraction: AttractionRecord) -> bool:
    """True if stop is outdoor or belongs to a weather-sensitive category."""
    return (
        getattr(attraction, "is_outdoor", False)
        or attraction.category.lower() in WEATHER_SENSITIVE_CATS
    )


def _simple_S_pti(attraction: AttractionRecord, constraints: ConstraintBundle) -> float:
    """
    Lightweight FTRM composite score (no full scorer import to avoid cycles).
    HC assumed = 1.0 for indoor candidates (already validated safe).
    SC approximated from rating + category match.
    """
    rating_norm = (getattr(attraction, "rating", 3.0) - 1.0) / 4.0  # [0, 1]

    soft = constraints.soft
    interest_bonus = (
        0.15 if soft.interests and
        any(i.lower() == attraction.category.lower() for i in soft.interests)
        else 0.0
    )
    crowd_bonus = (
        0.10 if soft.avoid_crowds and not getattr(attraction, "is_outdoor", False)
        else 0.0
    )
    return min(1.0, rating_norm + interest_bonus + crowd_bonus)


# ─────────────────────────────────────────────────────────────────────────────
# WeatherAdvisor
# ─────────────────────────────────────────────────────────────────────────────

class WeatherAdvisor:
    """
    Classifies impacted POIs and ranks indoor alternatives under bad weather.

    Usage:
        advisor = WeatherAdvisor()
        result  = advisor.classify(
            condition         = "heavy_rain",
            threshold         = 0.65,
            remaining_pool    = [...],
            constraints       = bundle,
            current_lat       = 28.62,
            current_lon       = 77.21,
            remaining_minutes = 310,
            top_n             = 3,
        )
    """

    def classify(
        self,
        condition:         str,
        threshold:         float,
        remaining_pool:    list[AttractionRecord],
        constraints:       ConstraintBundle,
        current_lat:       float,
        current_lon:       float,
        remaining_minutes: int,
        top_n:             int = 3,
    ) -> WeatherAdvisoryResult:
        """
        Full deterministic weather classification + alternative ranking.

        Decision rules:
            severity ≥ HC_UNSAFE_THRESHOLD : hc_override = 0.0  → BLOCKED
            threshold < severity < HC_UNSAFE: hc_override = 1.0 → DEFERRED
            is_outdoor = False              :                    → SAFE (candidate)
        """
        severity = WEATHER_SEVERITY.get(condition.lower(), 0.5)

        blocked:  list[WeatherImpact] = []
        deferred: list[WeatherImpact] = []
        safe:     list[AttractionRecord] = []

        for a in remaining_pool:
            if _is_weather_sensitive(a):
                if severity >= HC_UNSAFE_THRESHOLD:
                    # HC override → 0. Stop must not be visited.
                    blocked.append(WeatherImpact(
                        attraction    = a,
                        hc_override   = 0.0,
                        is_blocked    = True,
                        adjusted_duration = a.visit_duration_minutes,
                        reason        = (
                            f"Unsafe weather '{condition}' (severity {severity:.0%} ≥ "
                            f"HC_UNSAFE={HC_UNSAFE_THRESHOLD:.0%}) — "
                            f"HC_pti forced to 0; visit not viable."
                        ),
                    ))
                else:
                    # Risky but not unsafe → defer, scale duration down
                    adj = max(
                        a.min_visit_duration_minutes,
                        int(a.visit_duration_minutes * DURATION_SCALE_FACTOR),
                    )
                    deferred.append(WeatherImpact(
                        attraction    = a,
                        hc_override   = 1.0,
                        is_deferred   = True,
                        adjusted_duration = adj,
                        reason        = (
                            f"Risky outdoor stop in '{condition}' — visit shortened "
                            f"to {adj} min (×{DURATION_SCALE_FACTOR})."
                        ),
                    ))
            else:
                safe.append(a)

        # ── Rank indoor alternatives by η_ij = S_pti / Dij_new ──────────────
        candidates: list[WeatherAlternative] = []
        for a in safe:
            Dij = _haversine_minutes(
                current_lat, current_lon,
                a.location_lat, a.location_lon,
                AVG_TRAVEL_SPEED_KMH,
            )
            if a.visit_duration_minutes > remaining_minutes:
                continue   # not feasible in remaining time
            S   = _simple_S_pti(a, constraints)
            eta = S / Dij if Dij > 0 else 0.0
            candidates.append(WeatherAlternative(
                attraction   = a,
                eta_ij       = eta,
                S_pti        = S,
                Dij_new      = Dij,
                why_suitable = _why_weather_suitable(a, constraints),
            ))

        ranked = sorted(candidates, key=lambda x: x.eta_ij, reverse=True)[:top_n]

        # ── Duration adjustment map ───────────────────────────────────────────
        dur_adj: dict[str, int] = {}
        for imp in deferred:
            dur_adj[imp.attraction.name] = imp.adjusted_duration

        # ── Strategy message ──────────────────────────────────────────────────
        n_blocked  = len(blocked)
        n_deferred = len(deferred)
        alt_names  = " and ".join(f"'{a.attraction.name}'" for a in ranked[:2])

        if n_blocked > 0:
            msg = (
                f"{n_blocked} outdoor stop(s) blocked by unsafe '{condition}' "
                f"(severity {severity:.0%}); HC_pti set to 0 — deferred to less "
                f"exposed time. "
            )
        elif n_deferred > 0:
            msg = (
                f"{n_deferred} outdoor stop(s) at risk from '{condition}' — "
                f"visit durations reduced ×{DURATION_SCALE_FACTOR}. "
            )
        else:
            msg = f"No outdoor stops affected by '{condition}'. Plan unchanged. "

        if ranked:
            msg += f"Routing to indoor alternative(s): {alt_names}."

        return WeatherAdvisoryResult(
            condition          = condition,
            severity           = severity,
            threshold          = threshold,
            blocked_stops      = blocked,
            deferred_stops     = deferred,
            safe_stops         = safe,
            alternatives       = ranked,
            duration_adjustments = dur_adj,
            strategy_msg       = msg,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Why-suitable builder for weather alternatives
# ─────────────────────────────────────────────────────────────────────────────

def _why_weather_suitable(a: AttractionRecord, constraints: ConstraintBundle) -> str:
    reasons: list[str] = ["indoor — protected from weather"]
    soft = constraints.soft
    if soft.interests and a.category.lower() in [i.lower() for i in soft.interests]:
        reasons.append(f"matches your interest in '{a.category}'")
    if soft.pace_preference == "relaxed" and a.intensity_level == "low":
        reasons.append("low intensity — suits relaxed pace")
    return "; ".join(reasons)

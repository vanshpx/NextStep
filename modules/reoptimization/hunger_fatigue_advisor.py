"""
modules/reoptimization/hunger_fatigue_advisor.py
-------------------------------------------------
Deterministic hunger and fatigue disruption handling.

State variables (held in TripState):
    hunger_level  ∈ [0, 1]   — 0 = satiated, 1 = urgent
    fatigue_level ∈ [0, 1]   — 0 = fresh, 1 = exhausted

Three accumulation mechanisms:
  1. NLP trigger    — keywords in USER_REPORT_DISRUPTION message
  2. Behavioural    — inferred from UX signals (skip high-intensity, pace change)
  3. Deterministic  — time × effort_multiplier on every advance_to_stop

Equations:
    hunger_level  ← min(1, hunger + ΔT × HUNGER_RATE)
    fatigue_level ← min(1, fatigue + ΔT × FATIGUE_RATE × effort_multiplier)

    sc5_adjusted  = max(0, sc5_base − hunger_penalty − fatigue_penalty)
    SCpti_adj     = Σ Wv × scv  where sc5 := sc5_adjusted
    Spti_adjusted = HCpti × SCpti_adj                     (Eq 4 variant)
    η_ij_adj      = Spti_adjusted / Dij                   (Eq 12 variant)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.reoptimization.trip_state import TripState
    from schemas.constraints import ConstraintBundle
    from modules.tool_usage.attraction_tool import AttractionRecord

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Trigger thresholds
HUNGER_TRIGGER_THRESHOLD  = 0.70   # fire HUNGER_DISRUPTION when hunger_level ≥ this
FATIGUE_TRIGGER_THRESHOLD = 0.75   # fire FATIGUE_DISRUPTION when fatigue_level ≥ this

# Accumulation rates (units per minute)
HUNGER_RATE = 1 / 180    # reaches 1.0 in 3 h of no meal
FATIGUE_RATE = 1 / 420   # reaches 1.0 in 7 h of continuous activity

# Effort multipliers for fatigue_rate
HIGH_EFFORT_MULT = 1.8   # high-intensity stop
MED_EFFORT_MULT  = 1.3   # medium-intensity stop
# low-intensity:   1.0   (baseline)

# NLP floors: minimum level forced when keyword matched
NLP_HUNGER_FLOOR  = 0.72
NLP_FATIGUE_FLOOR = 0.78

# Behavioural inference increments
SKIP_FATIGUE_INCREMENT        = 0.10  # + fatigue when user skips high-intensity stop
PACE_CHANGE_FATIGUE_INCREMENT = 0.08  # + fatigue on pace → relaxed change

# Recovery amounts
REST_RECOVERY_AMOUNT = 0.40   # fatigue reduction per rest event
MEAL_DURATION_MIN    = 45     # clock minutes consumed by meal insertion
REST_DURATION_MIN    = 20     # clock minutes consumed by rest insertion

# SC5 penalty values (subtracted from existing sc5_base)
MAX_HUNGRY_DURATION_MIN       = 90   # stop duration above which full hunger penalty applies
HUNGER_LONG_STOP_PENALTY      = 0.40 # sc5 penalty — long stop while hungry
HUNGER_SHORT_STOP_PENALTY     = 0.10 # sc5 penalty — short stop while hungry
FATIGUE_HIGH_INTENSITY_PENALTY = 0.50 # sc5 penalty — high-intensity while fatigued
FATIGUE_MED_INTENSITY_PENALTY  = 0.20 # sc5 penalty — medium-intensity while fatigued

# SC bonuses
HUNGER_RESTAURANT_BONUS = 0.30  # SCpti bonus on RestaurantRecord when hungry

# SC5 weight (must match attraction_scoring.py)
SC5_WEIGHT = 0.10

# Trigger cooldown (minutes) — suppress re-trigger after an action
TRIGGER_COOLDOWN_MIN = 40

# NLP keyword sets
_HUNGER_KEYWORDS  = frozenset({
    "hungry", "starving", "famished", "need food", "want to eat",
    "eat", "lunch", "dinner", "snack", "food", "meal", "restaurant",
})
_FATIGUE_KEYWORDS = frozenset({
    "tired", "exhausted", "need rest", "feet hurt", "worn out",
    "take a break", "sit down", "need a break", "cant walk",
    "can't walk", "too much walking", "too tired", "rest",
})

# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MealOption:
    """A restaurant option surfaced in the HUNGER advisory."""
    rank:          int
    name:          str
    cuisine:       str
    rating:        float
    avg_cost:      float
    Dij_min:       float   # walking minutes from current position
    S_pti:         float
    why_suitable:  str


@dataclass
class HungerAdvisoryResult:
    """Output of HungerFatigueAdvisor.build_hunger_advisory()."""
    hunger_level:    float
    threshold:       float
    meal_options:    list[MealOption]
    action_taken:    str   # "meal_inserted" | "advisory_only"
    minutes_consumed: int
    no_options:      bool = False


@dataclass
class FatigueAdvisoryResult:
    """Output of HungerFatigueAdvisor.build_fatigue_advisory()."""
    fatigue_level:    float
    threshold:        float
    rest_duration:    int    # minutes of rest inserted
    next_stop:        str    # stop that would have been visited
    deferred_stops:   list[str]
    action_taken:     str    # "rest_inserted"
    minutes_consumed: int


# ─────────────────────────────────────────────────────────────────────────────
# HungerFatigueAdvisor
# ─────────────────────────────────────────────────────────────────────────────

class HungerFatigueAdvisor:
    """
    Stateless advisor — all mutable values live in TripState.

    Usage (inside ReOptimizationSession):
        # After each stop:
        self._hf_advisor.accumulate(
            state, intensity_level="medium", elapsed_minutes=90
        )
        # After USER_REPORT_DISRUPTION:
        self._hf_advisor.check_nlp_trigger(message, state)
        # Inside check_conditions():
        triggers = self._hf_advisor.check_triggers(state)
    """

    # ── Mechanism 1: NLP trigger ─────────────────────────────────────────────

    def check_nlp_trigger(self, message: str, state: "TripState") -> None:
        """
        Detect hunger/fatigue keywords in a free-text user message.
        Sets hunger_level / fatigue_level to at least the NLP floor if matched.
        Mutates state in place.
        """
        tokens = set(message.lower().split())
        # multi-word phrases
        msg_lower = message.lower()

        if tokens & _HUNGER_KEYWORDS or any(p in msg_lower for p in ("need food", "want to eat", "too hungry")):
            if state.hunger_level < NLP_HUNGER_FLOOR:
                state.hunger_level = NLP_HUNGER_FLOOR

        if tokens & _FATIGUE_KEYWORDS or any(p in msg_lower for p in ("need rest", "feet hurt", "take a break", "cant walk", "can't walk", "too tired")):
            if state.fatigue_level < NLP_FATIGUE_FLOOR:
                state.fatigue_level = NLP_FATIGUE_FLOOR

    # ── Mechanism 2: Behavioural inference ───────────────────────────────────

    def on_behavioral_signal(
        self,
        signal_type: str,       # "skip_high_intensity" | "pace_change"
        state:       "TripState",
    ) -> None:
        """
        Adjust fatigue based on inferred user signals.
        Mutates state in place.

        signal_type:
            "skip_high_intensity" — user skipped a high-intensity stop
            "pace_change"         — user changed pace_preference to "relaxed"
        """
        if signal_type == "skip_high_intensity":
            state.fatigue_level = min(1.0, state.fatigue_level + SKIP_FATIGUE_INCREMENT)
        elif signal_type == "pace_change":
            state.fatigue_level = min(1.0, state.fatigue_level + PACE_CHANGE_FATIGUE_INCREMENT)

    # ── Mechanism 3: Deterministic accumulation ───────────────────────────────

    def accumulate(
        self,
        state:             "TripState",
        intensity_level:   str = "medium",
        elapsed_minutes:   int = 60,
    ) -> None:
        """
        Called after every advance_to_stop() to accumulate hunger and fatigue.

        hunger_level  ← min(1, hunger  + elapsed × HUNGER_RATE)
        fatigue_level ← min(1, fatigue + elapsed × FATIGUE_RATE × effort_mult)

        Mutates state in place.
        """
        # Hunger: uniform rate, no multiplier
        state.hunger_level = min(
            1.0,
            state.hunger_level + elapsed_minutes * HUNGER_RATE,
        )

        # Fatigue: scaled by intensity
        effort = {
            "high":   HIGH_EFFORT_MULT,
            "medium": MED_EFFORT_MULT,
            "low":    1.0,
        }.get(intensity_level, MED_EFFORT_MULT)

        state.fatigue_level = min(
            1.0,
            state.fatigue_level + elapsed_minutes * FATIGUE_RATE * effort,
        )

    # ── Reset on meal / rest ─────────────────────────────────────────────────

    def on_meal_completed(self, state: "TripState") -> None:
        """Reset hunger to 0 and record last_meal_time. Called after a meal stop."""
        state.hunger_level  = 0.0
        state.last_meal_time = state.current_time

    def on_rest_completed(self, state: "TripState") -> None:
        """Reduce fatigue by REST_RECOVERY_AMOUNT. Called after a rest event."""
        state.fatigue_level = max(0.0, state.fatigue_level - REST_RECOVERY_AMOUNT)
        state.last_rest_time = state.current_time

    # ── Trigger check ────────────────────────────────────────────────────────

    def check_triggers(
        self,
        state: "TripState",
    ) -> list[str]:
        """
        Return a list of triggered disruption type strings.
        Respects cooldown so back-to-back checks don't re-fire immediately.

        Returns: list of "hunger_disruption" | "fatigue_disruption"
        """
        triggers: list[str] = []

        if state.hunger_level >= HUNGER_TRIGGER_THRESHOLD:
            # Cooldown: skip if we acted recently
            if not self._in_cooldown(state.last_meal_time, state.current_time):
                triggers.append("hunger_disruption")

        if state.fatigue_level >= FATIGUE_TRIGGER_THRESHOLD:
            if not self._in_cooldown(state.last_rest_time, state.current_time):
                triggers.append("fatigue_disruption")

        return triggers

    def _in_cooldown(self, event_time: str, current_time: str) -> bool:
        """True if fewer than TRIGGER_COOLDOWN_MIN minutes have passed since event_time."""
        if not event_time:
            return False
        try:
            eh, em = map(int, event_time.split(":"))
            ch, cm = map(int, current_time.split(":"))
            delta = (ch * 60 + cm) - (eh * 60 + em)
            return delta < TRIGGER_COOLDOWN_MIN
        except ValueError:
            return False

    # ── SC5 / Spti adjustment ────────────────────────────────────────────────

    def hunger_penalty(
        self,
        attraction:  "AttractionRecord",
        state:       "TripState",
    ) -> float:
        """
        sc5 penalty due to hunger.

        If attraction is a RestaurantRecord (type == "restaurant"), return 0.
        Else: if hunger ≥ threshold AND visit_duration > MAX_HUNGRY_DURATION_MIN
              → HUNGER_LONG_STOP_PENALTY
              else if hunger ≥ threshold
              → HUNGER_SHORT_STOP_PENALTY
        """
        from modules.tool_usage.restaurant_tool import RestaurantRecord
        if isinstance(attraction, RestaurantRecord):
            return 0.0
        if state.hunger_level < HUNGER_TRIGGER_THRESHOLD:
            return 0.0
        duration = getattr(attraction, "visit_duration_minutes", 60)
        return (HUNGER_LONG_STOP_PENALTY
                if duration > MAX_HUNGRY_DURATION_MIN
                else HUNGER_SHORT_STOP_PENALTY)

    def fatigue_penalty(
        self,
        attraction: "AttractionRecord",
        state:      "TripState",
    ) -> float:
        """
        sc5 penalty due to fatigue.

        Only applied when fatigue_level ≥ FATIGUE_TRIGGER_THRESHOLD.
        Scaled by attraction.intensity_level.
        """
        if state.fatigue_level < FATIGUE_TRIGGER_THRESHOLD:
            return 0.0
        intensity = getattr(attraction, "intensity_level", "medium")
        if intensity == "high":
            return FATIGUE_HIGH_INTENSITY_PENALTY
        if intensity == "medium":
            return FATIGUE_MED_INTENSITY_PENALTY
        return 0.0

    def restaurant_bonus(
        self,
        attraction: "AttractionRecord",
        state:      "TripState",
    ) -> float:
        """
        SCpti bonus for RestaurantRecords when traveller is hungry.
        Capped so final SCpti ≤ 1.0 (caller must clamp).
        """
        from modules.tool_usage.restaurant_tool import RestaurantRecord
        if isinstance(attraction, RestaurantRecord) and state.hunger_level >= HUNGER_TRIGGER_THRESHOLD:
            return HUNGER_RESTAURANT_BONUS
        return 0.0

    def apply_sc5_adjustment(
        self,
        sc5_base:   float,
        attraction: "AttractionRecord",
        state:      "TripState",
    ) -> float:
        """
        sc5_adjusted = max(0.0, sc5_base − hunger_penalty − fatigue_penalty)
        """
        penalty = self.hunger_penalty(attraction, state) + self.fatigue_penalty(attraction, state)
        return max(0.0, sc5_base - penalty)

    def compute_spti_adjusted(
        self,
        hc_pti:     float,
        sc_values:  list[float],        # [sc1, sc2, sc3, sc4, sc5]
        weights:    list[float],        # [0.25, 0.20, 0.30, 0.15, 0.10]
        attraction: "AttractionRecord",
        state:      "TripState",
    ) -> tuple[float, float]:
        """
        Returns (Spti_adjusted, eta_ij_adjusted) where:
            SCpti_adj    = Σ w_v × sc_v  with sc5 replaced by sc5_adjusted
            Spti_adj     = HCpti × SCpti_adj
            eta_ij_adj   = Spti_adj / Dij   [caller supplies Dij]

        Returns: (Spti_adjusted, SCpti_adjusted)
        """
        if len(sc_values) < 5 or len(weights) < 5:
            return hc_pti, hc_pti

        sc5_adj = self.apply_sc5_adjustment(sc_values[4], attraction, state)
        adjusted_sc = sc_values[:4] + [sc5_adj]

        # Apply restaurant bonus
        bonus = self.restaurant_bonus(attraction, state)
        scpti_adj = min(1.0, sum(w * s for w, s in zip(weights, adjusted_sc)) + bonus)
        spti_adj  = hc_pti * scpti_adj
        return spti_adj, scpti_adj

    def eta_adjusted(self, spti_adjusted: float, dij_minutes: float) -> float:
        """η_ij_adjusted = Spti_adjusted / Dij  (Eq 12 variant)."""
        return spti_adjusted / dij_minutes if dij_minutes > 0 else 0.0

    # ── Meal insertion ────────────────────────────────────────────────────────

    def advance_clock_for_meal(self, state: "TripState") -> int:
        """
        Advance clock by MEAL_DURATION_MIN, reset hunger, return minutes advanced.
        Called by session._handle_hunger_disruption() before _do_replan (LocalRepair).
        """
        h, m = map(int, state.current_time.split(":"))
        total = h * 60 + m + MEAL_DURATION_MIN
        total = min(total, 20 * 60)   # cap at DAY_END 20:00
        state.current_time = f"{total // 60:02d}:{total % 60:02d}"
        self.on_meal_completed(state)
        return MEAL_DURATION_MIN

    # ── Rest insertion ────────────────────────────────────────────────────────

    def advance_clock_for_rest(self, state: "TripState") -> int:
        """
        Advance clock by REST_DURATION_MIN, reduce fatigue, return minutes advanced.
        Called by session._handle_fatigue_disruption() before _do_replan (LocalRepair).
        """
        h, m = map(int, state.current_time.split(":"))
        total = h * 60 + m + REST_DURATION_MIN
        total = min(total, 20 * 60)
        state.current_time = f"{total // 60:02d}:{total % 60:02d}"
        self.on_rest_completed(state)
        return REST_DURATION_MIN

    # ── Advisory panels ──────────────────────────────────────────────────────

    def build_hunger_advisory(
        self,
        state:            "TripState",
        remaining:        list["AttractionRecord"],
        constraints:      "ConstraintBundle",
        cur_lat:          float,
        cur_lon:          float,
        remaining_minutes: int,
        budget_per_meal:  float,
    ) -> HungerAdvisoryResult:
        """
        Find best restaurant options from the remaining pool.
        Falls back to positional stubs if no RestaurantRecords are in pool.
        """
        from modules.tool_usage.restaurant_tool import RestaurantRecord

        dietary = set(getattr(constraints.soft, "dietary_preferences", []))

        # Collect restaurant candidates from remaining pool
        restaurants = [a for a in remaining if isinstance(a, RestaurantRecord)]

        # If no restaurants in the pool, fabricate a minimal stub advisory
        if not restaurants:
            return HungerAdvisoryResult(
                hunger_level    = state.hunger_level,
                threshold       = HUNGER_TRIGGER_THRESHOLD,
                meal_options    = [],
                action_taken    = "advisory_only",
                minutes_consumed= 0,
                no_options      = True,
            )

        options: list[MealOption] = []
        for rank, r in enumerate(restaurants, start=1):
            # HC check: dietary + budget (simplified)
            cuisine_pass = (not dietary) or bool(
                {r.cuisine_type.lower()} | set(r.cuisine_tags) & dietary
            )
            budget_pass = r.avg_price_per_person <= budget_per_meal
            if not (cuisine_pass and budget_pass):
                continue

            # Distance
            Dij = _haversine_minutes(cur_lat, cur_lon,
                                     r.location_lat, r.location_lon)
            # S_pti: rating / 5 as quick proxy (no full pipeline for restaurant here)
            S_pti = min(1.0, r.rating / 5.0 + HUNGER_RESTAURANT_BONUS)

            why = _why_meal(r, dietary)
            options.append(MealOption(
                rank         = rank,
                name         = r.name,
                cuisine      = r.cuisine_type,
                rating       = r.rating,
                avg_cost     = r.avg_price_per_person,
                Dij_min      = round(Dij, 1),
                S_pti        = round(S_pti, 2),
                why_suitable = why,
            ))

        options.sort(key=lambda o: (-o.S_pti, o.Dij_min))
        for i, o in enumerate(options, start=1):
            o.rank = i

        return HungerAdvisoryResult(
            hunger_level    = state.hunger_level,
            threshold       = HUNGER_TRIGGER_THRESHOLD,
            meal_options    = options[:3],
            action_taken    = "advisory_only",
            minutes_consumed= 0,
            no_options      = len(options) == 0,
        )

    def build_fatigue_advisory(
        self,
        state:       "TripState",
        next_stop:   str,
        remaining:   list["AttractionRecord"],
    ) -> FatigueAdvisoryResult:
        """
        Compute which upcoming stops will be affected by the rest pause
        (i.e. any stop whose Dij + STi would exceed remaining_minutes − REST_DURATION_MIN).
        """
        rem = state.remaining_minutes_today()
        usable_after_rest = max(0, rem - REST_DURATION_MIN)

        # Stops that require more time than available after rest are deferred
        deferred: list[str] = []
        for a in remaining:
            dur = getattr(a, "visit_duration_minutes", 60)
            if dur > usable_after_rest:
                deferred.append(a.name)

        return FatigueAdvisoryResult(
            fatigue_level   = state.fatigue_level,
            threshold       = FATIGUE_TRIGGER_THRESHOLD,
            rest_duration   = REST_DURATION_MIN,
            next_stop       = next_stop,
            deferred_stops  = deferred,
            action_taken    = "rest_inserted",
            minutes_consumed= REST_DURATION_MIN,
        )

    # ── Print methods ────────────────────────────────────────────────────────

    def print_hunger_advisory(self, result: HungerAdvisoryResult) -> None:
        """Print the HUNGER DISRUPTION advisory panel."""
        W   = 64
        sep = "-" * W
        bar = _level_bar(result.hunger_level)
        print(f"\n  [Hunger] {sep}")
        print(f"  HUNGER DISRUPTION")
        print(f"  Hunger: {result.hunger_level:.0%}  |  Threshold: {result.threshold:.0%}")
        print(f"  Level : {bar}")
        print(f"  {sep}")
        if result.no_options:
            print(f"  No restaurant data available — locate a nearby eatery and")
            print(f"  continue after a {MEAL_DURATION_MIN}-min meal break.")
        else:
            print(f"  NEAREST MEAL OPTIONS (ranked by satisfaction):")
            for opt in result.meal_options:
                print(f"    {opt.rank}. {opt.name}  [{opt.cuisine}]")
                print(f"       Rating={opt.rating:.1f}  Cost=₹{opt.avg_cost:.0f}/person  "
                      f"Dij={opt.Dij_min:.1f}min  S_pti={opt.S_pti:.2f}")
                print(f"       {opt.why_suitable}")
                print()
        print(f"  ACTION: {MEAL_DURATION_MIN}-min meal break — clock advanced, "
              f"hunger reset to 0.")
        print(f"  Downstream stop times recomputed (LocalRepair).")
        print(f"  {sep}\n")

    def print_fatigue_advisory(self, result: FatigueAdvisoryResult) -> None:
        """Print the FATIGUE DISRUPTION advisory panel."""
        W   = 64
        sep = "-" * W
        bar = _level_bar(result.fatigue_level)
        print(f"\n  [Fatigue] {sep}")
        print(f"  FATIGUE DISRUPTION")
        print(f"  Fatigue: {result.fatigue_level:.0%}  |  Threshold: {result.threshold:.0%}")
        print(f"  Level  : {bar}")
        print(f"  {sep}")
        print(f"  ACTION: {REST_DURATION_MIN}-min rest break before '{result.next_stop}'.")
        if result.deferred_stops:
            print(f"  NOTE  : After rest, {len(result.deferred_stops)} stop(s) may need")
            print(f"          deferral due to reduced remaining time:")
            for s in result.deferred_stops:
                print(f"            - {s}")
        else:
            print(f"  Remaining schedule unaffected by rest insertion.")
        print(f"  Fatigue reduced by {REST_RECOVERY_AMOUNT:.0%}  →  "
              f"{max(0.0, result.fatigue_level - REST_RECOVERY_AMOUNT):.2f}")
        print(f"  Downstream stop times recomputed (LocalRepair).")
        print(f"  {sep}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_EARTH_RADIUS_KM  = 6371.0
_TRAVEL_SPEED_KMH = 5.0


def _haversine_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Walking time in minutes via haversine distance."""
    if lat1 == lat2 == lon1 == lon2 == 0:
        return 0.0
    r = _EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    dist_km = 2 * r * math.asin(math.sqrt(a))
    return dist_km / _TRAVEL_SPEED_KMH * 60.0


def _level_bar(value: float, width: int = 20) -> str:
    """ASCII progress bar for a [0,1] level value."""
    filled = round(value * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"]  {value:.0%}"


def _why_meal(restaurant, dietary: set) -> str:
    parts: list[str] = []
    tags  = set(restaurant.cuisine_tags or [])
    if dietary & tags:
        matched = ", ".join(sorted(dietary & tags))
        parts.append(f"matches dietary: {matched}")
    if restaurant.rating >= 4.2:
        parts.append("highly rated")
    if restaurant.accepts_reservations:
        parts.append("takes reservations")
    return "; ".join(parts) if parts else "nearby option"

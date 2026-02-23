"""
modules/reoptimization/crowd_advisory.py
-----------------------------------------
CrowdAdvisory — advisory engine that fires whenever a crowd spike is detected
or a user requests a skip.  It combines:

  1. Historical importance of the affected stop
     Fetched via HistoricalInsightTool (record → LLM → stub fallback).

  2. Ranked alternative stops for the current time slot
     The remaining pool is scored with the full FTRM chain (AttractionScorer)
     using live SoftConstraints, then filtered by CommonsenseRules.

Output (CrowdAdvisoryResult) is printed by ReOptimizationSession before any
rescheduling action so the traveller always understands:
  - What they will miss (historical importance — shown only when permanent
    loss is possible: Strategy 3 + USER_SKIP).
  - What are good alternatives right now (FTRM-ranked suggestions).
  - What the system is proposing (strategy label).
  - That the final decision is theirs.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any

from schemas.constraints import ConstraintBundle
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.historical_tool import HistoricalInsightTool, HistoricalInsight
from modules.planning.attraction_scoring import AttractionScorer, AttractionScore
import config


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlternativeSuggestion:
    """One ranked alternative to the crowded/skipped stop."""
    attraction:   AttractionRecord
    score:        AttractionScore
    why_suitable: str   # one-line reason derived from SC alignment


@dataclass
class CrowdAdvisoryResult:
    """
    Full crowd advisory package for the traveller.

    Attributes:
        crowded_stop:     Name of the stop that triggered the advisory.
        crowd_level:      Live crowd reading (fraction 0–1).
        threshold:        User tolerance threshold.
        insight:          HistoricalInsight — what they'll miss if they skip.
        alternatives:     Top-N ranked alternatives under soft+commonsense constraints.
        strategy:         "reschedule_same_day" | "reschedule_future_day" | "inform_user"
        strategy_msg:     Human-readable system decision sentence.
        pending_decision: True when user must explicitly confirm (Strategy 3).
    """
    crowded_stop:     str
    crowd_level:      float
    threshold:        float
    insight:          HistoricalInsight
    alternatives:     list[AlternativeSuggestion] = field(default_factory=list)
    strategy:         str = ""
    strategy_msg:     str = ""
    pending_decision: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Commonsense filter
# ─────────────────────────────────────────────────────────────────────────────

_COMMONSENSE_BLOCK_KEYWORDS: dict[str, list[str]] = {
    "street food":  ["market", "street_food", "food_stall"],
    "tourist trap": ["tourist_trap"],
    "nightlife":    ["nightlife", "bar", "club"],
}


def _passes_commonsense(
    attraction: AttractionRecord,
    rules: list[str],
) -> tuple[bool, str]:
    cat        = attraction.category.lower()
    name_lower = attraction.name.lower()
    for rule in rules:
        rule_lower = rule.lower()
        for keyword, blocked_categories in _COMMONSENSE_BLOCK_KEYWORDS.items():
            if keyword in rule_lower:
                if cat in blocked_categories or any(bc in name_lower for bc in blocked_categories):
                    return False, f"blocked by rule: '{rule}'"
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Why-suitable builder
# ─────────────────────────────────────────────────────────────────────────────

def _why_suitable(score: AttractionScore, soft: Any) -> str:
    """One-line reason derived from dominant SC signal."""
    a = score.attraction
    reasons: list[str] = []

    # sc3 — interest / category match
    if soft.interests and a.category.lower() in [i.lower() for i in soft.interests]:
        reasons.append(f"matches your interest in '{a.category}'")

    # sc5 — crowd suitability
    if soft.avoid_crowds and not a.is_outdoor:
        reasons.append("indoor \u2014 likely less crowded")
    elif soft.avoid_crowds and a.is_outdoor:
        reasons.append("outdoor \u2014 best visited off-peak")

    # sc5 — pace / intensity
    if soft.pace_preference == "relaxed" and a.intensity_level == "low":
        reasons.append("low intensity \u2014 suits your relaxed pace")
    elif soft.pace_preference == "packed" and a.intensity_level in ("medium", "high"):
        reasons.append("high-value stop \u2014 keeps your pace")

    # sc1/sc4 — time-of-day alignment
    if soft.preferred_time_of_day == "morning" and a.optimal_visit_time:
        opt_start = a.optimal_visit_time.split("-")[0] if "-" in a.optimal_visit_time else ""
        if opt_start and opt_start < "13:00":
            reasons.append("best visited in the morning")

    # fallback — always show FTRM score
    reasons.append(f"FTRM score {score.S_pti:.2f}")

    return "; ".join(reasons) if reasons else f"FTRM score {score.S_pti:.2f}"


# ─────────────────────────────────────────────────────────────────────────────
# Strategy message composer
# ─────────────────────────────────────────────────────────────────────────────

def _compose_strategy_message(
    stop: str,
    crowd_level: float,
    threshold: float,
    strategy: str,
    alternatives: list[AlternativeSuggestion],
    target_day: int | None,
) -> str:
    alt_names = " and ".join(f"'{a.attraction.name}'" for a in alternatives[:2])

    if strategy == "reschedule_same_day":
        base = (
            f"'{stop}' is currently {crowd_level:.0%} crowded (your limit {threshold:.0%}). "
            f"The system will move it to a quieter slot later today"
        )
        if alt_names:
            base += f" and route you to {alt_names} first."
        else:
            base += "."
        return base

    if strategy == "reschedule_future_day":
        base = (
            f"'{stop}' is currently {crowd_level:.0%} crowded (your limit {threshold:.0%}). "
            f"Today's schedule is too tight to revisit it later, so it has been moved to "
            f"Day {target_day}"
        )
        if alt_names:
            base += f". Today you will go to {alt_names} instead."
        else:
            base += "."
        return base

    # inform_user
    base = (
        f"'{stop}' is very crowded ({crowd_level:.0%}, your limit {threshold:.0%}) and "
        f"cannot be rescheduled (last day or no remaining capacity). "
        f"You must decide whether to visit despite the crowds or skip permanently."
    )
    return base


# ─────────────────────────────────────────────────────────────────────────────
# CrowdAdvisory
# ─────────────────────────────────────────────────────────────────────────────

class CrowdAdvisory:
    """
    Builds a CrowdAdvisoryResult whenever a crowd spike or user-skip is triggered.

    Usage:
        advisory = CrowdAdvisory(HistoricalInsightTool())
        result   = advisory.build(
            crowded_stop      = "Heritage Fort",
            crowd_level       = 0.82,
            threshold         = 0.35,
            strategy          = "reschedule_same_day",
            remaining_pool    = [...],
            constraints       = bundle,
            current_lat       = 28.65,
            current_lon       = 77.24,
            current_time_str  = "09:50",
            remaining_minutes = 610,
        )
    """

    def __init__(self, historical_tool: HistoricalInsightTool | None = None) -> None:
        self._history = historical_tool or HistoricalInsightTool()

    def build(
        self,
        crowded_stop:      str,
        crowd_level:       float,
        threshold:         float,
        strategy:          str,
        remaining_pool:    list[AttractionRecord],
        constraints:       ConstraintBundle,
        current_lat:       float,
        current_lon:       float,
        current_time_str:  str,
        remaining_minutes: int,
        city:              str = "",
        target_day:        int | None = None,
        top_n:             int = 3,
    ) -> CrowdAdvisoryResult:
        """
        Build the full advisory package.

        Steps:
          1. Resolve historical importance of the crowded/skipped stop.
          2. Build AttractionScorer for current position + time.
          3. Score remaining pool excluding the crowded stop.
          4. Filter by commonsense rules.
          5. Take top_n feasible alternatives with why-suitable.
          6. Compose strategy message.
        """
        # ── 1. Resolve historical importance ─────────────────────────────────
        crowded_record = next(
            (a for a in remaining_pool if a.name == crowded_stop), None
        )
        if crowded_record is not None:
            insight = self._history.get(crowded_record, city=city)
        else:
            insight = self._history.get_by_name(place_name=crowded_stop, city=city)

        # ── 2. Build FTRM scorer for current position + time ─────────────────
        h, m = map(int, current_time_str.split(":"))
        t_cur    = dtime(h, m)
        end_time = dtime(20, 0)

        _dep        = getattr(constraints.hard, "departure_date", None)
        _trip_month = _dep.month if _dep is not None else 0
        _group = (
            (constraints.hard.group_size or 0)
            or constraints.hard.total_travelers
            or 1
        ) if constraints.hard else 1

        scorer = AttractionScorer(
            Tmax_minutes=remaining_minutes,
            constraints=constraints,
            trip_month=_trip_month,
            group_size=_group,
            traveler_ages=constraints.hard.traveler_ages if constraints.hard else [],
        )

        # ── 3. Score the pool, excluding the crowded stop itself ──────────────
        candidate_pool = [a for a in remaining_pool if a.name != crowded_stop]

        if candidate_pool:
            scored = scorer.score_all(
                candidates=candidate_pool,
                p_cur_lat=current_lat,
                p_cur_lon=current_lon,
                t_cur=t_cur,
                end_time=end_time,
            )
        else:
            scored = []

        # ── 4. Filter by commonsense rules ────────────────────────────────────
        rules = constraints.commonsense.rules if constraints.commonsense else []
        filtered: list[AttractionScore] = []
        for s in scored:
            ok, _ = _passes_commonsense(s.attraction, rules)
            if ok:
                filtered.append(s)

        # ── 5. Build top_n AlternativeSuggestion objects ──────────────────────
        feasible = [s for s in filtered if s.feasible][:top_n]
        soft     = constraints.soft if constraints.soft else None
        alternatives = [
            AlternativeSuggestion(
                attraction=s.attraction,
                score=s,
                why_suitable=_why_suitable(s, soft) if soft else f"FTRM score {s.S_pti:.2f}",
            )
            for s in feasible
        ]

        # ── 6. Compose strategy message ───────────────────────────────────────
        strategy_msg = _compose_strategy_message(
            stop=crowded_stop,
            crowd_level=crowd_level,
            threshold=threshold,
            strategy=strategy,
            alternatives=alternatives,
            target_day=target_day,
        )

        return CrowdAdvisoryResult(
            crowded_stop=crowded_stop,
            crowd_level=crowd_level,
            threshold=threshold,
            insight=insight,
            alternatives=alternatives,
            strategy=strategy,
            strategy_msg=strategy_msg,
            pending_decision=(strategy == "inform_user"),
        )

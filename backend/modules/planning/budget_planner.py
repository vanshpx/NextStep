"""
modules/planning/budget_planner.py
------------------------------------
Deterministic, validated budget planning engine.

Replaces naive static-percentage distribution with:
  1. City-aware cost index as fallback when real API data is absent.
  2. Real hotel / restaurant / attraction price data when provided.
  3. Trip-length and group-size aware calculations.
  4. Mathematical validation ensuring Σ(categories) == TotalBudget exactly.
  5. Hard caps enforced per category:
       Accommodation  ≤ 45 % of TotalBudget
       Restaurants    ≤ 25 % of TotalBudget
       Transportation ≤ 20 % of TotalBudget
       Reserve_Fund   ≥  5 % of TotalBudget
  6. Post-itinerary rebalance when projected spend > allocated.

Entry points
------------
  distribute()               — Stage 2 preliminary (city index) and
                               post-Stage-3 recompute (real price data).
  post_itinerary_rebalance() — Stage 4+ final validation & rebalance.
  validate()                 — boolean test-assertion hook.

All monetary amounts are in INR (Indian Rupee).
"""

from __future__ import annotations

from typing import Any

from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation
import config


# ── Category hard caps (fraction of TotalBudget) ─────────────────────────────
_CAP_ACCOMMODATION  = 0.45
_CAP_RESTAURANTS    = 0.25
_CAP_TRANSPORTATION = 0.20
_MIN_RESERVE        = 0.05      # Reserve_Fund floor
_OTHER_EXPENSES_PCT = 0.075     # 7.5 % — midpoint of the specified 5–10 % range
_MEAL_FLEXIBILITY   = 0.10      # +10 % buffer on top of base restaurant cost


# ── City-level cost index (all values in INR) ─────────────────────────────────
# Used as fallback when real pricing data (hotel_records / restaurant_records) is
# absent.  Keys are lowercase city-name fragments; partial matching is supported.
#
# Fields
#   hotel_per_night     — median midrange hotel rate per room per night
#   meal_per_person     — average single-meal cost per person
#   attraction_per_day  — combined daily entry fees for ~4 typical attractions
#   daily_transport     — metro/auto/cab cost per person per day
#   cost_per_km         — auto-equivalent INR/km (route-distance transport costing)
CITY_COST_INDEX: dict[str, dict[str, float]] = {
    "delhi":       {"hotel_per_night": 3500,  "meal_per_person": 350,  "attraction_per_day": 600,  "daily_transport": 400,  "cost_per_km": 8.0},
    "new delhi":   {"hotel_per_night": 3500,  "meal_per_person": 350,  "attraction_per_day": 600,  "daily_transport": 400,  "cost_per_km": 8.0},
    "mumbai":      {"hotel_per_night": 5000,  "meal_per_person": 450,  "attraction_per_day": 500,  "daily_transport": 300,  "cost_per_km": 10.0},
    "bangalore":   {"hotel_per_night": 4000,  "meal_per_person": 400,  "attraction_per_day": 400,  "daily_transport": 350,  "cost_per_km": 9.0},
    "bengaluru":   {"hotel_per_night": 4000,  "meal_per_person": 400,  "attraction_per_day": 400,  "daily_transport": 350,  "cost_per_km": 9.0},
    "jaipur":      {"hotel_per_night": 3000,  "meal_per_person": 300,  "attraction_per_day": 700,  "daily_transport": 350,  "cost_per_km": 7.0},
    "agra":        {"hotel_per_night": 2500,  "meal_per_person": 280,  "attraction_per_day": 1200, "daily_transport": 300,  "cost_per_km": 7.0},
    "goa":         {"hotel_per_night": 4500,  "meal_per_person": 500,  "attraction_per_day": 300,  "daily_transport": 400,  "cost_per_km": 9.0},
    "kolkata":     {"hotel_per_night": 3000,  "meal_per_person": 300,  "attraction_per_day": 400,  "daily_transport": 250,  "cost_per_km": 7.0},
    "chennai":     {"hotel_per_night": 3500,  "meal_per_person": 350,  "attraction_per_day": 400,  "daily_transport": 300,  "cost_per_km": 8.0},
    "hyderabad":   {"hotel_per_night": 3500,  "meal_per_person": 400,  "attraction_per_day": 500,  "daily_transport": 300,  "cost_per_km": 8.0},
    "pune":        {"hotel_per_night": 3500,  "meal_per_person": 400,  "attraction_per_day": 400,  "daily_transport": 300,  "cost_per_km": 8.0},
    "udaipur":     {"hotel_per_night": 3500,  "meal_per_person": 350,  "attraction_per_day": 600,  "daily_transport": 350,  "cost_per_km": 7.0},
    "varanasi":    {"hotel_per_night": 2500,  "meal_per_person": 250,  "attraction_per_day": 400,  "daily_transport": 250,  "cost_per_km": 6.0},
    "rishikesh":   {"hotel_per_night": 2000,  "meal_per_person": 250,  "attraction_per_day": 300,  "daily_transport": 300,  "cost_per_km": 7.0},
    "new york":    {"hotel_per_night": 18000, "meal_per_person": 2500, "attraction_per_day": 3000, "daily_transport": 1500, "cost_per_km": 50.0},
    "london":      {"hotel_per_night": 16000, "meal_per_person": 2000, "attraction_per_day": 2500, "daily_transport": 1800, "cost_per_km": 45.0},
    "paris":       {"hotel_per_night": 15000, "meal_per_person": 2000, "attraction_per_day": 2000, "daily_transport": 1500, "cost_per_km": 40.0},
    "dubai":       {"hotel_per_night": 12000, "meal_per_person": 1500, "attraction_per_day": 2000, "daily_transport": 1200, "cost_per_km": 30.0},
    "singapore":   {"hotel_per_night": 10000, "meal_per_person": 1200, "attraction_per_day": 1500, "daily_transport": 800,  "cost_per_km": 25.0},
    "bangkok":     {"hotel_per_night": 4000,  "meal_per_person": 500,  "attraction_per_day": 800,  "daily_transport": 400,  "cost_per_km": 10.0},
    # Fallback for unrecognised cities
    "_default":    {"hotel_per_night": 3500,  "meal_per_person": 350,  "attraction_per_day": 500,  "daily_transport": 350,  "cost_per_km": 8.0},
}


class BudgetPlanner:
    """
    Deterministic, validated budget planning engine.

    Usage pattern
    -------------
    Stage 2 (preliminary) — city-index only:
        budget = planner.distribute(total, constraints, num_days)

    Post-Stage-3 recompute — with real price records:
        budget = planner.distribute(total, constraints, num_days,
                                    hotel_records=...,
                                    restaurant_records=...,
                                    attraction_records=...)

    Post-itinerary validation (Stage 4+):
        budget = planner.post_itinerary_rebalance(budget, total, itinerary,
                                                   best_hotel, best_rest,
                                                   best_flight, group_size,
                                                   num_days)
    """

    def __init__(self, llm_client: Any = None) -> None:
        self.llm_client = llm_client   # reserved for future LLM dynamic adjustment

    # =========================================================================
    # PUBLIC: distribute
    # =========================================================================

    def distribute(
        self,
        total_budget: float,
        constraints: ConstraintBundle,
        num_days: int,
        hotel_records:      list | None = None,
        restaurant_records: list | None = None,
        attraction_records: list | None = None,
        estimated_daily_transport_km: float = 0.0,
    ) -> BudgetAllocation:
        """
        Compute a validated BudgetAllocation from available price signals.

        Priority order per category
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~
        1. Real data from hotel_records / restaurant_records.
        2. City-level cost index for the destination city.
        3. DataQuality flag is set to "MISSING_COST_DATA" if neither applies.

        Parameters
        ----------
        total_budget
            Total confirmed trip budget (INR).
        constraints
            ConstraintBundle supplying destination city and group size.
        num_days
            Trip length in nights / active sightseeing days.
        hotel_records
            Raw HotelRecord list from HotelTool.fetch() — optional.
        restaurant_records
            Raw RestaurantRecord list from RestaurantTool.fetch() — optional.
        attraction_records
            Raw AttractionRecord list from AttractionTool.fetch() — optional.
            AttractionRecord has no entry_cost field; used only for scaling
            the city-index attraction estimate.
        estimated_daily_transport_km
            Expected km travelled per day (for distance-cost transport);
            0 triggers fallback to city-index daily rate.
        """
        hard       = constraints.hard
        group_size = max(hard.num_adults + hard.num_children, 1)
        city       = hard.destination_city.strip().lower()
        city_idx   = self._get_city_index(city)
        data_quality = "REAL"

        # ── 1. Accommodation (Eq: min(hotel_nightly × TripDays, 40 % budget)) ──
        #    Rule: cannot exceed 45 % (enforced later in _apply_constraints_and_balance)
        if hotel_records:
            valid_prices = sorted(
                h.price_per_night for h in hotel_records
                if getattr(h, "price_per_night", 0) > 0
            )
            if valid_prices:
                # Median rate: representative midrange option for a single room
                hotel_nightly = valid_prices[len(valid_prices) // 2]
            else:
                hotel_nightly = city_idx["hotel_per_night"]
                data_quality  = "CITY_INDEX"
        else:
            hotel_nightly = city_idx["hotel_per_night"]
            data_quality  = "CITY_INDEX"

        accommodation = round(
            min(hotel_nightly * num_days, 0.40 * total_budget), 2
        )

        # ── 2. Restaurants (Eq: AverageMealCost × 2 meals × TripDays × 1.10) ──
        if restaurant_records:
            raw_prices = sorted(
                r.avg_price_per_person for r in restaurant_records
                if getattr(r, "avg_price_per_person", 0) > 0
            )
            if raw_prices:
                # Median per-person cost prevents expensive outliers inflating budget
                avg_meal_cost = raw_prices[len(raw_prices) // 2]
            else:
                avg_meal_cost = city_idx["meal_per_person"]
                data_quality  = "CITY_INDEX"
        else:
            avg_meal_cost = city_idx["meal_per_person"]
            data_quality  = "CITY_INDEX"

        restaurant_base = avg_meal_cost * group_size * 2 * num_days
        restaurants = round(
            min(restaurant_base * (1.0 + _MEAL_FLEXIBILITY),
                _CAP_RESTAURANTS * total_budget), 2
        )

        # ── 3. Attractions (city index: entry_cost not in AttractionRecord) ────
        #    Scale by ratio of scheduled attractions per day to city-index baseline.
        _CITY_BASELINE_ATTRACTIONS_PER_DAY = 4.0
        if attraction_records:
            scheduled_per_day = len(attraction_records) / max(num_days, 1)
            scale = min(scheduled_per_day / _CITY_BASELINE_ATTRACTIONS_PER_DAY, 1.5)
        else:
            scale = 1.0
        attractions = round(city_idx["attraction_per_day"] * scale * num_days, 2)

        # ── 4. Transportation ────────────────────────────────────────────────
        #    Distance-based if km known; city-index daily rate otherwise.
        if estimated_daily_transport_km > 0:
            total_km = estimated_daily_transport_km * num_days
            transportation = round(
                min(total_km * city_idx["cost_per_km"],
                    _CAP_TRANSPORTATION * total_budget), 2
            )
        else:
            transportation = round(
                min(city_idx["daily_transport"] * group_size * num_days,
                    _CAP_TRANSPORTATION * total_budget), 2
            )

        # ── 5. Other Expenses (7.5 % of TotalBudget) ────────────────────────
        other_expenses = round(_OTHER_EXPENSES_PCT * total_budget, 2)

        # ── 6. Reserve Fund = TotalBudget − Σ above ─────────────────────────
        reserve_fund = round(
            total_budget
            - accommodation - restaurants - attractions
            - transportation - other_expenses, 2
        )

        raw = BudgetAllocation(
            Accommodation  = accommodation,
            Attractions    = attractions,
            Restaurants    = restaurants,
            Transportation = transportation,
            Other_Expenses = other_expenses,
            Reserve_Fund   = reserve_fund,
            ValidationStatus = "PENDING",
            RebalanceApplied = False,
            DataQuality      = data_quality,
        )
        return self._apply_constraints_and_balance(raw, total_budget)

    # =========================================================================
    # PUBLIC: post_itinerary_rebalance
    # =========================================================================

    def post_itinerary_rebalance(
        self,
        allocation:       BudgetAllocation,
        total_budget:     float,
        itinerary:        object,
        best_hotel:       object | None,
        best_restaurant:  object | None,
        best_flight:      object | None,
        group_size:       int,
        num_days:         int,
    ) -> BudgetAllocation:
        """
        Post-Stage-4 validation: compare projected actual spend to allocated.

        Algorithm
        ---------
        1. Compute projected spend per category using selected best records.
        2. If projected_total > allocation.total
              OR projected_reserve < 5 % of total_budget
           → trigger budget_rebalance_event: hard-pin projected values and
             rebalance via _apply_constraints_and_balance.
        3. Otherwise: update allocation with projected values, let Reserve float.

        Flight cost is added into Transportation (ground + air combined).
        """
        # ── Project actual spend ─────────────────────────────────────────────
        proj_accommodation = 0.0
        if best_hotel and getattr(best_hotel, "price_per_night", 0) > 0:
            proj_accommodation = round(best_hotel.price_per_night * num_days, 2)

        proj_restaurants = 0.0
        if best_restaurant and getattr(best_restaurant, "avg_price_per_person", 0) > 0:
            proj_restaurants = round(
                best_restaurant.avg_price_per_person * group_size * 2 * num_days, 2
            )

        # Flight cost (outbound leg × group) merged into Transportation
        proj_flight = 0.0
        if best_flight and getattr(best_flight, "price", 0) > 0:
            proj_flight = round(best_flight.price * group_size, 2)

        proj_transport = round(allocation.Transportation + proj_flight, 2)

        # Count actual scheduled attractions from itinerary
        proj_attractions = allocation.Attractions      # no entry_cost data available

        proj_total = round(
            (proj_accommodation if proj_accommodation > 0 else allocation.Accommodation)
            + (proj_restaurants  if proj_restaurants  > 0 else allocation.Restaurants)
            + proj_transport
            + proj_attractions
            + allocation.Other_Expenses, 2
        )
        proj_reserve = round(total_budget - proj_total, 2)

        trigger = (
            proj_total  > allocation.total
            or proj_reserve < round(_MIN_RESERVE * total_budget, 2)
        )

        if trigger:
            print(
                f"  [BudgetPlanner] ⚠  budget_rebalance_event triggered — "
                f"projected ₹{proj_total:,.0f} vs allocated ₹{allocation.total:,.0f}"
            )
            updated = BudgetAllocation(
                Accommodation  = round(min(
                    proj_accommodation if proj_accommodation > 0 else allocation.Accommodation,
                    _CAP_ACCOMMODATION * total_budget), 2),
                Attractions    = proj_attractions,
                Restaurants    = round(min(
                    proj_restaurants if proj_restaurants > 0 else allocation.Restaurants,
                    _CAP_RESTAURANTS * total_budget), 2),
                Transportation = round(min(
                    proj_transport,
                    _CAP_TRANSPORTATION * total_budget), 2),
                Other_Expenses = allocation.Other_Expenses,
                Reserve_Fund   = max(proj_reserve, 0.0),
                ValidationStatus = "PENDING",
                RebalanceApplied = True,
                DataQuality      = allocation.DataQuality,
            )
        else:
            # No rebalance: pin projected values where available, let Reserve absorb delta
            accomm = proj_accommodation if proj_accommodation > 0 else allocation.Accommodation
            rest   = proj_restaurants   if proj_restaurants   > 0 else allocation.Restaurants
            updated = BudgetAllocation(
                Accommodation  = round(accomm, 2),
                Attractions    = proj_attractions,
                Restaurants    = round(rest,   2),
                Transportation = round(proj_transport, 2),
                Other_Expenses = allocation.Other_Expenses,
                Reserve_Fund   = round(
                    total_budget - accomm - rest - proj_transport
                    - proj_attractions - allocation.Other_Expenses, 2),
                ValidationStatus = "PENDING",
                RebalanceApplied = False,
                DataQuality      = "REAL",
            )

        return self._apply_constraints_and_balance(updated, total_budget)

    # =========================================================================
    # PUBLIC: validate
    # =========================================================================

    def validate(self, allocation: BudgetAllocation, total_budget: float) -> bool:
        """
        Return True iff:
          • Σ(all categories) is within ₹1 of TotalBudget, AND
          • ValidationStatus == "PASS".

        Used for test assertions (assert budget_planner.validate(...)).
        """
        return (
            abs(allocation.total - total_budget) <= 1.0
            and allocation.ValidationStatus == "PASS"
        )

    # =========================================================================
    # PRIVATE: constraint enforcement + exact balancing
    # =========================================================================

    def _apply_constraints_and_balance(
        self,
        allocation: BudgetAllocation,
        total_budget: float,
    ) -> BudgetAllocation:
        """
        Enforce per-category caps, guarantee Reserve ≥ 5 %, and make
        Σ(categories) == TotalBudget to the nearest paisa.

        Rebalance order when sum > total (or Reserve < floor):
          1. Reserve_Fund reduced first — but never below MIN_RESERVE × total.
          2. Other_Expenses reduced — but never below 5 % × total.
          3. Restaurant buffer (10 % markup) removed.
          4. Proportional scale across {Accommodation, Restaurants,
             Transportation, Attractions} as last resort.

        If sum < total, surplus is added to Reserve_Fund.
        """
        rebalance_applied = allocation.RebalanceApplied

        min_reserve = round(_MIN_RESERVE * total_budget, 2)
        min_other   = round(0.05 * total_budget, 2)
        max_accomm  = round(_CAP_ACCOMMODATION  * total_budget, 2)
        max_rest    = round(_CAP_RESTAURANTS    * total_budget, 2)
        max_transp  = round(_CAP_TRANSPORTATION * total_budget, 2)

        # ── Step 1: Apply per-category hard caps ─────────────────────────────
        accomm  = min(allocation.Accommodation,  max_accomm)
        rest    = min(allocation.Restaurants,    max_rest)
        transp  = min(allocation.Transportation, max_transp)
        attrac  = max(allocation.Attractions, 0.0)
        other   = allocation.Other_Expenses
        reserve = allocation.Reserve_Fund

        if (accomm != allocation.Accommodation
                or rest   != allocation.Restaurants
                or transp != allocation.Transportation):
            rebalance_applied = True

        # ── Step 2: Absorb any gap (positive or negative) into Reserve ───────
        current_sum = round(accomm + rest + transp + attrac + other + reserve, 2)
        gap         = round(total_budget - current_sum, 2)
        reserve     = round(reserve + gap, 2)

        # ── Step 3: Ensure Reserve ≥ floor — trim other categories if short ──
        if reserve < min_reserve:
            shortfall = round(min_reserve - reserve, 2)
            reserve   = min_reserve
            rebalance_applied = True

            # (a) Trim Other_Expenses down to min_other
            reduction = min(shortfall, max(0.0, other - min_other))
            other     = round(other - reduction, 2)
            shortfall = round(shortfall - reduction, 2)

            # (b) Remove restaurant 10 % flexibility buffer
            if shortfall > 0:
                rest_buffer = round(
                    allocation.Restaurants * _MEAL_FLEXIBILITY / (1.0 + _MEAL_FLEXIBILITY), 2
                )
                reduction = min(shortfall, max(0.0, rest_buffer))
                rest      = round(rest - reduction, 2)
                shortfall = round(shortfall - reduction, 2)

            # (c) Proportional scale across remaining flexible categories
            if shortfall > 0:
                flex_total = accomm + rest + transp + attrac
                if flex_total > 0:
                    scale  = max(0.0, (flex_total - shortfall) / flex_total)
                    accomm = round(accomm * scale, 2)
                    rest   = round(rest   * scale, 2)
                    transp = round(transp * scale, 2)
                    attrac = round(attrac * scale, 2)

        # ── Step 4: Exact penny correction (absorb float rounding into Reserve)
        total_computed = round(accomm + rest + transp + attrac + other + reserve, 2)
        penny_error    = round(total_budget - total_computed, 2)
        reserve        = round(reserve + penny_error, 2)

        # ── Step 5: Determine ValidationStatus ──────────────────────────────
        final_total = round(accomm + rest + transp + attrac + other + reserve, 2)
        status = "PASS" if abs(final_total - total_budget) <= 0.01 else "FAIL"

        return BudgetAllocation(
            Accommodation  = accomm,
            Attractions    = attrac,
            Restaurants    = rest,
            Transportation = transp,
            Other_Expenses = other,
            Reserve_Fund   = reserve,
            ValidationStatus = status,
            RebalanceApplied = rebalance_applied,
            DataQuality      = allocation.DataQuality,
        )

    def _get_city_index(self, city_lower: str) -> dict[str, float]:
        """
        Return cost index entry for the city (case-insensitive partial matching).

        Lookup order:
          1. Exact key match.
          2. Any key that is a substring of city_lower, or vice-versa.
          3. "_default" fallback entry.
        """
        if city_lower in CITY_COST_INDEX:
            return CITY_COST_INDEX[city_lower]
        for key, data in CITY_COST_INDEX.items():
            if key != "_default" and (key in city_lower or city_lower in key):
                return data
        return CITY_COST_INDEX["_default"]

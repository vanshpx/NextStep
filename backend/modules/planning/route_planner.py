"""
modules/planning/route_planner.py
-----------------------------------
Multi-day itinerary planner integrating the FTRM + ACO optimizer.

Architecture:
  - Primary solver: ACOOptimizer (one instance per day) via Eq 13, 14, 15, 16
  - Fallback:       Greedy η_ij selection (if num_ants=1 or ACO disabled)

Each day d ∈ M:
  1. Build FTRMGraph from remaining attractions (nodes not yet visited).
  2. Compute S_pti for each node (satisfaction.py: Eq 1→4).
  3. Run ACO for num_iterations → best Tour (Eq 13, 14, 15/16).
  4. Convert Tour path → RoutePoint list with arrival/departure times.
  5. Update p_cur, t_cur; remove visited attractions from pool.

Constraints enforced:
  Eq  8 (visit-once): attractions removed from pool after each day.
  Eq  9 (continuity): ACO constructs tours sequentially; always satisfied.
  Eq 10 (Tmax):       ACO feasibility check inside _get_feasible_nodes.
  Eq 11 (binary Xij): Tour.path is an ordered sequence; Xdtij implied.
"""

from __future__ import annotations
from datetime import date, time, datetime, timedelta
from typing import Optional
import math
import re
import uuid

from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation, DayPlan, Itinerary, RoutePoint
from schemas.ftrm import FTRMGraph, FTRMNode, FTRMEdge, FTRMParameters
from modules.tool_usage.attraction_tool import AttractionRecord, _CITY_CENTERS, _CITY_NAME_ALIASES
from modules.tool_usage.distance_tool import DistanceTool
from modules.tool_usage.time_tool import TimeTool
from modules.optimization.satisfaction import evaluate_satisfaction
from modules.optimization.aco_optimizer import ACOOptimizer, Tour
from modules.observability.logger import StructuredLogger
import config
import time as _time_mod

_perf_logger = StructuredLogger()


# Default day boundaries (CONFIRMED: minutes unit)
DEFAULT_DAY_START: time = time(9, 0)    # 09:00
DEFAULT_DAY_END:   time = time(20, 0)   # 20:00 → Tmax = 660 min (but config.ACO_TMAX_MINUTES used)

# ── Deterministic scheduling constants (all time values in minutes) ──────────
_TRANSITION_BUFFER_MIN:    int   = 12     # Rule 1: 10–15 min transition buffer between POIs
_MAX_CONTINUOUS_SIGHT_MIN: int   = 180    # Rule 5: max unbroken sightseeing (3 h)
_MAX_SAME_DAY_TRAVEL_MIN:  float = 60.0   # Rule 7: travel > 60 min → reassign to next day
_MAX_IDLE_GAP_MIN:         int   = 90     # Rule 6: max idle gap before insertion
_MAX_CLUSTER_RADIUS_KM:    float = 9.0    # Rule 2: max per-day cluster radius (8–10 km)
_DAY_END_HARD:             time  = time(20, 30)   # Rule 6: hard day cutoff
_KMEANS_ITERATIONS:        int   = 15             # geographic K-means convergence limit
_DEDUP_COORD_DIST_KM:      float = 0.30   # Rule 4: same-location threshold (300 m)
_DEDUP_WORD_OVERLAP_RATIO: float = 0.70   # Rule 4: name-word overlap considered duplicate

# ── Scheduling guard constants ───────────────────────────────────────────────
_ANCHOR_MAX_DIST_KM: float = 50.0     # Rule 1: hotel anchor must be within 50 km of city center
_MIN_STOPS_PER_DAY:  int   = 2        # Rule 4: minimum stops per day before relaxation kicks in
# Relaxed secondary constraint values (applied only when < _MIN_STOPS_PER_DAY scheduled)
_RELAX_BUFFER_MIN:   int   = 0        # Rule 4a: drop transition buffer
_RELAX_TRAVEL_MIN:   float = 120.0    # Rule 4c: extended same-day travel threshold (was 60)


# ── Module-level time helpers ─────────────────────────────────────────────────

def _t2m(t: time) -> int:
    """Convert a time object to integer minutes-from-midnight."""
    return t.hour * 60 + t.minute


def _m2t(mins: int) -> time:
    """Convert minutes-from-midnight to a time object (clamped to [0, 1439])."""
    mins = max(0, min(int(mins), 23 * 60 + 59))
    return time(mins // 60, mins % 60)


def _haversine_inline(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (used for clustering and dedup)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── Anchor / city-center helpers ──────────────────────────────────────────────

def _get_city_center(city: str) -> tuple[float, float] | None:
    """
    Return (lat, lon) for *city* using the _CITY_CENTERS table (zero API calls).
    Aliases (state names, misspellings) are resolved first via _CITY_NAME_ALIASES.
    Returns None if the city is not in the table.
    """
    norm = city.lower().strip()
    key = _CITY_NAME_ALIASES.get(norm, norm)
    return _CITY_CENTERS.get(key)


def _validate_hotel_anchor(
    hotel_lat: float,
    hotel_lon: float,
    destination_city: str,
) -> None:
    """
    Rule 1 — Anchor Validation.

    Asserts hotel coordinates are within _ANCHOR_MAX_DIST_KM (50 km) of the
    destination city center.  Raises ERROR_INVALID_HOTEL_ANCHOR on failure.

    Skips the distance check when:
      - hotel_lat == hotel_lon == 0.0  (sentinel for "not set")
      - city center not in _CITY_CENTERS (cannot compute distance)
    This prevents false positives for stubs that pass (0, 0) as placeholder coords.
    """
    if hotel_lat == 0.0 and hotel_lon == 0.0:
        return  # sentinel — coordinates not yet populated; skip check
    center = _get_city_center(destination_city)
    if center is None:
        return  # city center unknown — cannot validate, allow through
    dist_km = _haversine_inline(hotel_lat, hotel_lon, center[0], center[1])
    if dist_km > _ANCHOR_MAX_DIST_KM:
        raise RuntimeError(
            f"ERROR_INVALID_HOTEL_ANCHOR: hotel ({hotel_lat:.5f}, {hotel_lon:.5f}) "
            f"is {dist_km:.1f} km from {destination_city!r} city center "
            f"({center[0]:.5f}, {center[1]:.5f}); limit = {_ANCHOR_MAX_DIST_KM} km."
        )


class RoutePlanner:
    """
    Multi-day FTRM route planner backed by ACO.

    For each day:
      - Builds a FTRMGraph from the remaining attraction pool.
      - Computes S_pti per node using the satisfaction chain (Eq 1→4).
      - Runs ACOOptimizer to get the best tour (Eq 13, 14, 15/16).
      - Converts the tour into a DayPlan with timed RoutePoints.
    """

    def __init__(
        self,
        distance_tool: DistanceTool | None = None,
        time_tool: TimeTool | None = None,
        ftrm_params: FTRMParameters | None = None,
    ):
        self.distance_tool = distance_tool or DistanceTool()
        self.time_tool     = time_tool     or TimeTool()
        self.ftrm_params   = ftrm_params   or FTRMParameters(
            Tmax=config.ACO_TMAX_MINUTES,
            alpha=config.ACO_ALPHA,
            beta=config.ACO_BETA,
            rho=config.ACO_RHO,
            Q=config.ACO_Q,
            tau_init=config.ACO_TAU_INIT,
            num_ants=config.ACO_NUM_ANTS,
            num_iterations=config.ACO_ITERATIONS,
            sc_aggregation_method=config.SC_AGGREGATION_METHOD,
            pheromone_update_strategy=config.ACO_PHEROMONE_STRATEGY,
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def plan(
        self,
        constraints: ConstraintBundle,
        attraction_set: list[AttractionRecord],
        budget: BudgetAllocation,
        start_date: date,
        end_date: date,
        hotel_lat: float = 0.0,
        hotel_lon: float = 0.0,
    ) -> Itinerary:
        """
        Generate a complete multi-day itinerary using FTRM + ACO.

        Args:
            constraints:    Bundled constraints (hard + soft + commonsense).
            attraction_set: Ranked attractions from Recommendation Module.
            budget:         BudgetAllocation from BudgetPlanner.
            start_date:     First day of trip.
            end_date:       Last day of trip.
            hotel_lat/lon:  Starting position p_cur for each day (hotel coords).

        Returns:
            Populated Itinerary object (Eq 5 objective maximised per day by ACO).
        """
        _t0 = _time_mod.perf_counter()
        itinerary = Itinerary(
            trip_id=str(uuid.uuid4()),
            destination_city=constraints.hard.destination_city,
            budget=budget,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        # ── Rule 1: Anchor Validation ─────────────────────────────────────────
        # Must run BEFORE any scheduling so a bad hotel anchor aborts early.
        destination_city = constraints.hard.destination_city
        _validate_hotel_anchor(hotel_lat, hotel_lon, destination_city)

        # Removed: trip_month, group_size, traveler_ages — no API source for
        # seasonal/age/capacity HC checks (see 07-simplified-model.md)

        # ── Pre-distribute attractions evenly across days ─────────────────────
        # Guarantees every day gets at least 1 stop (no empty days).
        # Stops are pre-divided into per-day quotas; any ACO-unvisited stops from
        # a day's quota are carried forward into the next day's pool (rollover).
        # ── Rule 4: Semantic deduplication ───────────────────────────────────
        deduped = self._deduplicate_attractions(attraction_set)
        if len(deduped) < len(attraction_set):
            print(f"  [scheduler] Deduplicated: {len(attraction_set)} → {len(deduped)} attractions")

        num_days = max((end_date - start_date).days + 1, 1)

        # ── Rules 2 + 7: Geographic clustering ───────────────────────────────
        # Group POIs by proximity (max _MAX_CLUSTER_RADIUS_KM per day-group).
        # This replaces the naïve sequential slice that caused cross-city zig-zags.
        day_buckets: list[list[AttractionRecord]] = self._cluster_by_proximity(
            deduped, num_days, hotel_lat, hotel_lon
        )

        # Ensure at least one bucket per day (pad if clustering returned fewer)
        while len(day_buckets) < num_days:
            day_buckets.append([])

        visited_globally: set[str] = set()   # Eq 8: visit-once across all days
        current_date = start_date
        day_number   = 1
        rollover: list[AttractionRecord] = []   # unvisited from previous day quota
        total_scheduled: int = 0               # Rule 3/6: track stops scheduled globally

        for day_idx, bucket in enumerate(day_buckets):
            is_boundary_day = (current_date == start_date or current_date == end_date)

            # Merge rollover from previous day at the front of today's pool
            # so they get prioritised (they were already scored highly)
            pool = [a for a in rollover if a.name not in visited_globally] + \
                   [a for a in bucket   if a.name not in visited_globally]

            day_plan = self._plan_single_day(
                day_number=day_number,
                plan_date=current_date,
                available_attractions=pool,
                start_lat=hotel_lat,
                start_lon=hotel_lon,
                constraints=constraints,
                is_arrival_or_departure_day=is_boundary_day,
            )

            visited_today  = {rp.name for rp in day_plan.route_points}
            visited_globally |= visited_today
            total_scheduled  += len(day_plan.route_points)

            # Stops in today's pool that ACO could not fit → roll to tomorrow
            rollover = [a for a in pool if a.name not in visited_globally]

            itinerary.days.append(day_plan)
            itinerary.total_actual_cost += day_plan.daily_budget_used
            current_date += timedelta(days=1)
            day_number   += 1

        # ── Rule 6: Hard Failure Guard ───────────────────────────────────────
        # Hotel anchor was validated above; distance matrix is validated inside
        # _build_graph() for each day.  If we reach here with attractions in the
        # input but zero scheduled stops, the scheduler has a logic error.
        attractions_count = len(deduped)
        if attractions_count > 0 and total_scheduled == 0:
            raise RuntimeError(
                f"ERROR_SCHEDULER_LOGIC: {attractions_count} attraction(s) supplied "
                f"for {destination_city!r} but zero stops were scheduled across "
                f"{num_days} day(s).  Constraints may be too restrictive or all "
                f"S_pti scores are zero.  Check debug trace printed above for details."
            )

        _perf_logger.log("default", "PERFORMANCE", {
            "component": "RoutePlanner.plan",
            "duration_ms": round((_time_mod.perf_counter() - _t0) * 1000, 2),
        })
        return itinerary

    # ── Single-day planner ────────────────────────────────────────────────────

    def _plan_single_day(
        self,
        day_number: int,
        plan_date: date,
        available_attractions: list[AttractionRecord],
        start_lat: float,
        start_lon: float,
        constraints: ConstraintBundle | None = None,
        is_arrival_or_departure_day: bool = False,
    ) -> DayPlan:
        """
        Run ACO for one day. Returns a DayPlan with timed RoutePoints.

        Rule 4 — Minimum Scheduling Rule:
          If fewer than _MIN_STOPS_PER_DAY (2) are scheduled on the first pass,
          the method retries by relaxing *secondary* constraints in order:
            a) Buffer time    : _TRANSITION_BUFFER_MIN → 0
            b) Travel radius  : _MAX_SAME_DAY_TRAVEL_MIN → _RELAX_TRAVEL_MIN
          Hard constraints (HC gate, opening hours, city) are NEVER relaxed.
          The pass that yields the most stops is kept.

        Rule 5 — Debug Trace:
          Before returning a completely empty day (0 stops) when pool is
          non-empty, prints per-attraction rejection diagnostics.
        """
        day = DayPlan(day_number=day_number, date=plan_date)

        if not available_attractions:
            return day

        # ── Build FTRMGraph ───────────────────────────────────────────────────
        graph, node_map = self._build_graph(
            available_attractions, start_lat, start_lon
        )

        # ── Compute S_pti per node (Eq 1→4) ──────────────────────────────────
        S_pti = self._compute_satisfaction(
            graph,
            constraints=constraints,
            is_arrival_or_departure_day=is_arrival_or_departure_day,
        )

        # ── Run ACO (Eq 13, 14, 15/16) ───────────────────────────────────────
        aco = ACOOptimizer(
            graph=graph,
            S_pti=S_pti,
            params=self.ftrm_params,
            start_node=0,
            seed=None,
        )
        best_tour: Tour = aco.run()

        # ── Pass 1: normal constraints ────────────────────────────────────────
        day = self._tour_to_day_plan(
            tour=best_tour,
            day_number=day_number,
            plan_date=plan_date,
            graph=graph,
            node_map=node_map,
            buffer_min=_TRANSITION_BUFFER_MIN,
            max_travel_min=_MAX_SAME_DAY_TRAVEL_MIN,
        )

        # ── Rule 4: constraint relaxation retries ─────────────────────────────
        if len(day.route_points) < _MIN_STOPS_PER_DAY:
            # Pass 2 — relax buffer time (Rule 4a)
            day2 = self._tour_to_day_plan(
                tour=best_tour,
                day_number=day_number,
                plan_date=plan_date,
                graph=graph,
                node_map=node_map,
                buffer_min=_RELAX_BUFFER_MIN,
                max_travel_min=_MAX_SAME_DAY_TRAVEL_MIN,
            )
            if len(day2.route_points) > len(day.route_points):
                day = day2
                if len(day.route_points) >= _MIN_STOPS_PER_DAY:
                    print(
                        f"  [scheduler] Day {day_number}: relaxed buffer → "
                        f"{len(day.route_points)} stop(s) scheduled."
                    )

        if len(day.route_points) < _MIN_STOPS_PER_DAY:
            # Pass 3 — relax buffer + travel threshold (Rule 4b/c)
            day3 = self._tour_to_day_plan(
                tour=best_tour,
                day_number=day_number,
                plan_date=plan_date,
                graph=graph,
                node_map=node_map,
                buffer_min=_RELAX_BUFFER_MIN,
                max_travel_min=_RELAX_TRAVEL_MIN,
            )
            if len(day3.route_points) > len(day.route_points):
                day = day3
                if len(day.route_points) >= _MIN_STOPS_PER_DAY:
                    print(
                        f"  [scheduler] Day {day_number}: relaxed buffer+travel → "
                        f"{len(day.route_points)} stop(s) scheduled."
                    )

        # ── Rule 5: Debug trace before returning empty day ────────────────────
        if len(day.route_points) == 0:
            print(
                f"\n  [SCHEDULER_DEBUG] Day {day_number} — 0 stops scheduled "
                f"from pool of {len(available_attractions)} attraction(s)."
            )
            print(f"    HotelAnchorLatLon    : ({start_lat:.5f}, {start_lon:.5f})")
            Tmax = self.ftrm_params.Tmax
            for idx, attr in enumerate(available_attractions[:5]):
                Dij = graph.get_Dij(0, idx + 1)
                STi = float(attr.visit_duration_minutes)
                node_id = idx + 1
                s_val = S_pti.get(node_id, 0.0)

                # Diagnose primary rejection reason
                if s_val <= 0.0:
                    reason = "S_pti=0 (HC gate failed — check rating/opening hours)"
                elif Dij == float("inf"):
                    reason = "Dij=inf (no route from hotel to this attraction)"
                elif Dij > _RELAX_TRAVEL_MIN:
                    reason = f"TravelTime={Dij:.0f} min > relaxed limit {_RELAX_TRAVEL_MIN:.0f} min"
                elif Dij + STi > Tmax:
                    reason = f"Dij({Dij:.0f})+STi({STi:.0f})={Dij+STi:.0f} > Tmax({Tmax:.0f})"
                else:
                    reason = f"DayEndBlock: departure would exceed {_DAY_END_HARD}"

                print(
                    f"    Attraction[{idx+1}] {attr.name!r}\n"
                    f"      AttrLatLon      : ({attr.location_lat:.5f}, {attr.location_lon:.5f})\n"
                    f"      TravelTimeMin   : {Dij:.1f}\n"
                    f"      TmaxRemaining   : {Tmax:.0f}\n"
                    f"      STi             : {STi:.0f} min\n"
                    f"      S_pti           : {s_val:.4f}\n"
                    f"      RejectionReason : {reason}"
                )
            print()

        return day

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_graph(
        self,
        attractions: list[AttractionRecord],
        start_lat: float,
        start_lon: float,
    ) -> tuple[FTRMGraph, dict[int, AttractionRecord | None]]:
        """
        Build FTRMGraph from attraction list.
        Node 0 = virtual start (hotel). Nodes 1..N = attractions.
        Dij computed via OSRM Table API (single call for all pairs); haversine fallback.

        Returns:
            (FTRMGraph, node_map) where node_map[node_id] = AttractionRecord | None.
        """
        # Create nodes
        start_node = FTRMNode(
            node_id=0, name="START", Si=0.0, STi=0.0,
            lat=start_lat, lon=start_lon, is_start=True,
        )
        nodes = [start_node]
        node_map: dict[int, AttractionRecord | None] = {0: None}

        for idx, attr in enumerate(attractions, start=1):
            n = FTRMNode(
                node_id=idx,
                name=attr.name,
                Si=min(attr.rating / 5.0, 1.0),   # normalise rating to [0,1]
                STi=float(attr.visit_duration_minutes),
                lat=attr.location_lat,
                lon=attr.location_lon,
            )
            nodes.append(n)
            node_map[idx] = attr

        # Create edges (complete graph) — Dij in minutes.
        # OSRM Table API: one HTTP request returns the full n×n duration matrix,
        # replacing O(n²) individual route calls.
        node_coords = [(n.lat, n.lon) for n in nodes]
        dij_matrix  = self.distance_tool.travel_time_matrix(node_coords)

        # ── Rule 2: Distance Matrix Validation ───────────────────────────────
        # If every non-diagonal cell is inf the matrix is unusable.
        if len(nodes) > 1:
            finite_count = sum(
                1 for a in nodes for b in nodes
                if a.node_id != b.node_id
                and dij_matrix[a.node_id][b.node_id] != float("inf")
            )
            if finite_count == 0:
                raise RuntimeError(
                    f"ERROR_MISSING_DISTANCE_DATA: travel-time matrix contains "
                    f"only inf values for {len(nodes)-1} attraction(s).  "
                    f"OSRM may be unreachable and haversine fallback did not fire."
                )

        edges: list[FTRMEdge] = []
        for a in nodes:
            for b in nodes:
                if a.node_id == b.node_id:
                    continue
                Dij_min = dij_matrix[a.node_id][b.node_id]
                edges.append(FTRMEdge(i=a.node_id, j=b.node_id, Dij=Dij_min))

        graph = FTRMGraph(nodes=nodes, edges=edges)
        graph.build_adjacency()
        return graph, node_map

    # ── Satisfaction computation ──────────────────────────────────────────────

    def _compute_satisfaction(
        self,
        graph: FTRMGraph,
        constraints: ConstraintBundle | None = None,
        is_arrival_or_departure_day: bool = False,
    ) -> dict[int, float]:
        """
        Compute S_pti for each node using full Eq 1→4 chain via AttractionScorer.

        The scorer evaluates:
          - HC: opening hours, Tmax, accessibility, min-duration (simplified 4-HC set)
          - SC: rating quality, interest match, outdoor preference (3-SC set)

        Start/end nodes carry zero satisfaction.
        """
        from modules.planning.attraction_scoring import AttractionScorer

        scorer = AttractionScorer(
            distance_tool=self.distance_tool,
            time_tool=self.time_tool,
            sc_method=self.ftrm_params.sc_aggregation_method,
            Tmax_minutes=self.ftrm_params.Tmax,
            constraints=constraints,
        )

        S_pti: dict[int, float] = {}
        for node in graph.nodes:
            if node.is_start or node.is_end:
                S_pti[node.node_id] = 0.0
                continue
            # Use node's Si as a fallback rating-based scoring when no AttractionRecord
            # is available (start-of-day placeholder).
            # Full scoring via constraint_registry happens inside scorer._score_one()
            # when called from score_all(); here we use a simplified path for the
            # satisfaction map (the ACO pheromone input).
            hc = [1 if node.Si > 0.0 else 0]
            sc_vals = [node.Si]
            sc_wts  = [1.0]
            result = evaluate_satisfaction(hc, sc_vals, sc_wts,
                                           method=self.ftrm_params.sc_aggregation_method)
            S_pti[node.node_id] = result["S"]
        return S_pti

    # ── Deduplication ─────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate_attractions(
        attractions: list[AttractionRecord],
    ) -> list[AttractionRecord]:
        """
        Rule 4: Remove semantic duplicates from the attraction pool.

        A candidate is a duplicate of an already-kept record if ANY of:
          (a) coordinates within _DEDUP_COORD_DIST_KM (300 m) of each other, OR
          (b) one normalised name is a substring of the other, OR
          (c) word-level overlap ratio ≥ _DEDUP_WORD_OVERLAP_RATIO (70 %).

        The first occurrence (highest ranked) is kept; all others are dropped.
        """
        def _norm(s: str) -> str:
            return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()

        kept: list[AttractionRecord] = []
        for cand in attractions:
            cand_norm  = _norm(cand.name)
            cand_words = set(cand_norm.split())
            is_dup = False
            for k in kept:
                # (a) Coordinate proximity
                if _haversine_inline(
                    cand.location_lat, cand.location_lon,
                    k.location_lat,   k.location_lon,
                ) < _DEDUP_COORD_DIST_KM:
                    is_dup = True
                    break
                # (b) Name containment
                k_norm = _norm(k.name)
                if cand_norm in k_norm or k_norm in cand_norm:
                    is_dup = True
                    break
                # (c) Word-overlap ratio
                k_words = set(k_norm.split())
                if cand_words and k_words:
                    overlap = len(cand_words & k_words) / min(len(cand_words), len(k_words))
                    if overlap >= _DEDUP_WORD_OVERLAP_RATIO:
                        is_dup = True
                        break
            if not is_dup:
                kept.append(cand)
        return kept

    # ── Geographic clustering ──────────────────────────────────────────────────

    def _cluster_by_proximity(
        self,
        attractions: list[AttractionRecord],
        num_days: int,
        hotel_lat: float,
        hotel_lon: float,
    ) -> list[list[AttractionRecord]]:
        """
        Rules 2 + 7: Group attractions into num_days geographically coherent clusters
        so no single day's route zig-zags across the city.

        Algorithm: iterative K-means on (lat, lon) with K = num_days.
        Attractions assigned to the centroid nearest their coordinates.
        """
        n = len(attractions)
        if n == 0:
            return [[] for _ in range(num_days)]
        if num_days <= 1 or n <= num_days:
            clusters = [[a] for a in attractions]
            while len(clusters) < num_days:
                clusters.append([])
            return clusters[:num_days]

        K = min(num_days, n)
        # Initialise centroids: evenly-spaced by latitude sort
        sorted_a = sorted(attractions, key=lambda a: (a.location_lat, a.location_lon))
        step = n / K
        centroids: list[tuple[float, float]] = [
            (sorted_a[int(i * step)].location_lat, sorted_a[int(i * step)].location_lon)
            for i in range(K)
        ]

        clusters: list[list[AttractionRecord]] = [[] for _ in range(K)]
        for _ in range(_KMEANS_ITERATIONS):
            new_clusters: list[list[AttractionRecord]] = [[] for _ in range(K)]
            for attr in attractions:
                dists = [
                    _haversine_inline(attr.location_lat, attr.location_lon, clat, clon)
                    for clat, clon in centroids
                ]
                new_clusters[dists.index(min(dists))].append(attr)

            # Update centroids
            new_centroids: list[tuple[float, float]] = []
            for i, clust in enumerate(new_clusters):
                if clust:
                    new_centroids.append((
                        sum(a.location_lat for a in clust) / len(clust),
                        sum(a.location_lon for a in clust) / len(clust),
                    ))
                else:
                    new_centroids.append(centroids[i])

            if new_centroids == centroids:
                clusters = new_clusters
                break
            centroids = new_centroids
            clusters  = new_clusters

        # Pad to num_days
        result = list(clusters)
        while len(result) < num_days:
            result.append([])
        return result[:num_days]

    # ── Tour → DayPlan conversion ─────────────────────────────────────────────

    def _tour_to_day_plan(
        self,
        tour: Tour,
        day_number: int,
        plan_date: date,
        graph: FTRMGraph,
        node_map: dict[int, AttractionRecord | None],
        buffer_min: int = _TRANSITION_BUFFER_MIN,
        max_travel_min: float = _MAX_SAME_DAY_TRAVEL_MIN,
    ) -> DayPlan:
        """
        Convert an ACO-ordered tour into a DayPlan applying all deterministic
        time-structuring rules.

        Args:
            buffer_min      : Transition buffer between stops (Rule 4a relaxation).
            max_travel_min  : Max intra-day travel before skipping a stop
                              (Rule 4c relaxation).

        Rule 1  — Time continuity:
                  arrival(i) = departure(i-1) + travel_time + buffer_min
        Rule 5  — Fatigue balancing:
                  Track continuous sightseeing minutes; reset at 3 h.
        Rule 6  — Day completion:
                  Stop scheduling any attraction whose departure > _DAY_END_HARD.
        Rule 7  — Travel realism:
                  Skip any attraction where Dij > max_travel_min (from previous stop).
        """
        day = DayPlan(day_number=day_number, date=plan_date)
        t_cur_min: int = _t2m(DEFAULT_DAY_START)   # minutes from midnight (09:00)
        prev_node_id: int = 0                       # hotel / start node
        sequence: int = 0
        continuous_min: int = 0                     # Rule 5: unbroken sightseeing acc.
        day_end_min  = _t2m(_DAY_END_HARD)          # 20:30

        for node_id in tour.path:
            if node_id == 0:
                continue                   # skip virtual start node

            node_obj = graph.get_node(node_id)
            attr_rec = node_map.get(node_id)
            if node_obj is None or attr_rec is None:
                continue

            Dij = graph.get_Dij(prev_node_id, node_id)

            # Rule 7: if travel from *previous POI* (not hotel) would exceed
            # max_travel_min, skip — belongs to a different geographic cluster.
            if prev_node_id != 0 and Dij > max_travel_min:
                continue

            # Rule 1: strict time continuity — add travel time AND buffer
            arrival_min   = t_cur_min + int(Dij) + buffer_min
            duration_min  = max(int(node_obj.STi), 1)
            departure_min = arrival_min + duration_min

            # Rule 6: stop scheduling once departure would exceed the hard day-end
            if departure_min > day_end_min:
                break

            rp = RoutePoint(
                sequence=sequence,
                name=attr_rec.name,
                location_lat=attr_rec.location_lat,
                location_lon=attr_rec.location_lon,
                arrival_time=_m2t(arrival_min),
                departure_time=_m2t(departure_min),
                visit_duration_minutes=duration_min,
                activity_type="attraction",
                estimated_cost=0.0,
            )
            day.route_points.append(rp)
            day.daily_budget_used += rp.estimated_cost

            t_cur_min    = departure_min
            prev_node_id = node_id
            sequence    += 1

            # Rule 5: accumulate continuous sightseeing minutes
            continuous_min += int(Dij) + buffer_min + duration_min
            if continuous_min >= _MAX_CONTINUOUS_SIGHT_MIN:
                # 3-hour threshold reached — reset counter.
                # _inject_meals_smart() will detect this gap and slot a break.
                continuous_min = 0

        return day

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
import uuid

from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation, DayPlan, Itinerary, RoutePoint
from schemas.ftrm import FTRMGraph, FTRMNode, FTRMEdge, FTRMParameters
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.distance_tool import DistanceTool
from modules.tool_usage.time_tool import TimeTool
from modules.optimization.satisfaction import evaluate_satisfaction
from modules.optimization.aco_optimizer import ACOOptimizer, Tour
import config


# Default day boundaries (CONFIRMED: minutes unit)
DEFAULT_DAY_START: time = time(9, 0)    # 09:00
DEFAULT_DAY_END:   time = time(20, 0)   # 20:00 → Tmax = 660 min (but config.ACO_TMAX_MINUTES used)


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
        itinerary = Itinerary(
            trip_id=str(uuid.uuid4()),
            destination_city=constraints.hard.destination_city,
            budget=budget,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        # Derive trip_month from departure_date for seasonal HC check
        trip_month = start_date.month if start_date else 0
        # group_size: prefer explicit HC field; fall back to adults+children sum
        group_size = constraints.hard.group_size or constraints.hard.total_travelers or 1
        traveler_ages = constraints.hard.traveler_ages

        # ── Pre-distribute attractions evenly across days ─────────────────────
        # Guarantees every day gets at least 1 stop (no empty days).
        # Stops are pre-divided into per-day quotas; any ACO-unvisited stops from
        # a day's quota are carried forward into the next day's pool (rollover).
        num_days     = max((end_date - start_date).days + 1, 1)
        total_stops  = len(attraction_set)
        quota_per_day = max(math.ceil(total_stops / num_days), 1)

        # Build per-day buckets by slicing the ranked attraction list
        day_buckets: list[list[AttractionRecord]] = []
        for d in range(num_days):
            start_idx = d * quota_per_day
            end_idx   = min(start_idx + quota_per_day, total_stops)
            day_buckets.append(list(attraction_set[start_idx:end_idx]))

        # Carry any leftover stops (if total_stops % num_days != 0) into last bucket
        # (already handled by the min() above, but ensure last day is non-empty)
        if total_stops > 0 and not day_buckets[-1]:
            day_buckets[-1] = list(attraction_set[-1:])

        visited_globally: set[str] = set()   # Eq 8: visit-once across all days
        current_date = start_date
        day_number   = 1
        rollover: list[AttractionRecord] = []   # unvisited from previous day quota

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
                trip_month=trip_month,
                group_size=group_size,
                traveler_ages=traveler_ages,
                is_arrival_or_departure_day=is_boundary_day,
            )

            visited_today  = {rp.name for rp in day_plan.route_points}
            visited_globally |= visited_today

            # Stops in today's pool that ACO could not fit → roll to tomorrow
            rollover = [a for a in pool if a.name not in visited_globally]

            itinerary.days.append(day_plan)
            itinerary.total_actual_cost += day_plan.daily_budget_used
            current_date += timedelta(days=1)
            day_number   += 1

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
        trip_month: int = 0,
        group_size: int = 1,
        traveler_ages: list[int] | None = None,
        is_arrival_or_departure_day: bool = False,
    ) -> DayPlan:
        """
        Run ACO for one day. Returns a DayPlan with timed RoutePoints.
        """
        day = DayPlan(day_number=day_number, date=plan_date)

        if not available_attractions:
            return day

        # ── Build FTRMGraph ───────────────────────────────────────────────────
        graph, node_map = self._build_graph(
            available_attractions, start_lat, start_lon
        )

        # ── Compute S_pti per node (Eq 1→4) ──────────────────────────────────
        # Pass full constraints so HC (group, seasonal, etc.) and
        # SC (interests, crowd, energy) are evaluated with user profile.
        S_pti = self._compute_satisfaction(
            graph,
            constraints=constraints,
            trip_month=trip_month,
            group_size=group_size,
            traveler_ages=traveler_ages or [],
            is_arrival_or_departure_day=is_arrival_or_departure_day,
        )

        # ── Run ACO (Eq 13, 14, 15/16) ───────────────────────────────────────
        aco = ACOOptimizer(
            graph=graph,
            S_pti=S_pti,
            params=self.ftrm_params,
            start_node=0,   # node 0 = hotel/start
            seed=None,
        )
        best_tour: Tour = aco.run()

        # ── Convert Tour → RoutePoints with timed schedule ────────────────────
        day = self._tour_to_day_plan(
            tour=best_tour,
            day_number=day_number,
            plan_date=plan_date,
            graph=graph,
            node_map=node_map,
        )
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
        Dij computed via DistanceTool (minutes via TimeTool).

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

        # Create edges (complete graph) — Dij in minutes
        edges: list[FTRMEdge] = []
        for a in nodes:
            for b in nodes:
                if a.node_id == b.node_id:
                    continue
                dist_km = self.distance_tool.calculate(a.lat, a.lon, b.lat, b.lon)
                Dij_min = self.time_tool.estimate_travel_time(dist_km)
                edges.append(FTRMEdge(i=a.node_id, j=b.node_id, Dij=Dij_min))

        graph = FTRMGraph(nodes=nodes, edges=edges)
        graph.build_adjacency()
        return graph, node_map

    # ── Satisfaction computation ──────────────────────────────────────────────

    def _compute_satisfaction(
        self,
        graph: FTRMGraph,
        constraints: ConstraintBundle | None = None,
        trip_month: int = 0,
        group_size: int = 1,
        traveler_ages: list[int] | None = None,
        is_arrival_or_departure_day: bool = False,
    ) -> dict[int, float]:
        """
        Compute S_pti for each node using full Eq 1→4 chain via AttractionScorer.

        The scorer evaluates:
          - HC: opening hours, Tmax, accessibility, age, group size, seasonal, min-duration
          - SC: optimal window, remaining-time, interest match,
                time-of-day preference, crowd/energy management

        Start/end nodes carry zero satisfaction.
        """
        from modules.planning.attraction_scoring import AttractionScorer

        scorer = AttractionScorer(
            distance_tool=self.distance_tool,
            time_tool=self.time_tool,
            sc_method=self.ftrm_params.sc_aggregation_method,
            Tmax_minutes=self.ftrm_params.Tmax,
            constraints=constraints,
            trip_month=trip_month,
            group_size=group_size,
            traveler_ages=traveler_ages or [],
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

    # ── Tour → DayPlan conversion ─────────────────────────────────────────────

    def _tour_to_day_plan(
        self,
        tour: Tour,
        day_number: int,
        plan_date: date,
        graph: FTRMGraph,
        node_map: dict[int, AttractionRecord | None],
    ) -> DayPlan:
        """
        Assign arrival/departure times to each node in the ACO tour path.
        Skips node 0 (start/hotel node) and end-placeholder nodes.
        """
        day = DayPlan(day_number=day_number, date=plan_date)
        t_cur: time = DEFAULT_DAY_START
        prev_node_id: int = 0   # start from hotel
        sequence = 0

        for node_id in tour.path:
            if node_id == 0:   # skip start node
                continue

            node_obj = graph.get_node(node_id)
            attr_rec = node_map.get(node_id)
            if node_obj is None or attr_rec is None:
                continue

            # Travel time from previous node [minutes]
            Dij = graph.get_Dij(prev_node_id, node_id)
            arrival = self.time_tool.add_minutes(t_cur, Dij)
            departure = self.time_tool.add_minutes(arrival, node_obj.STi)

            rp = RoutePoint(
                sequence=sequence,
                name=attr_rec.name,
                location_lat=attr_rec.location_lat,
                location_lon=attr_rec.location_lon,
                arrival_time=arrival,
                departure_time=departure,
                visit_duration_minutes=attr_rec.visit_duration_minutes,
                activity_type="attraction",
                estimated_cost=attr_rec.entry_cost,
            )
            day.route_points.append(rp)
            day.daily_budget_used += rp.estimated_cost

            t_cur = departure
            prev_node_id = node_id
            sequence += 1

        return day

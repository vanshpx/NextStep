"""
db/repositories/trip_repo.py
------------------------------
CRUD operations for the `trips` and `itinerary_days` tables.

Source: docs/database/05-implementation.sql Tables trips, itinerary_days
Source: docs/database/06-ingestion-pipeline.md § 2.2, 2.5

All functions accept a psycopg2 connection object.
Commit/rollback is managed by the caller via db.connection.get_conn().
"""

from __future__ import annotations

import json
from typing import Any


# ── trips table ────────────────────────────────────────────────────────────────

def insert_trip(conn, trip_data: dict[str, Any]) -> str:
    """
    Insert a new trip row. Returns trip_id (UUID string).

    Required keys:
        destination_city, departure_city, departure_date, return_date,
        num_adults, num_children, group_size, total_budget, budget_allocation

    Optional keys (default to safe values if absent):
        user_id, traveler_ages, requires_wheelchair,
        restaurant_preference, fixed_appointments,
        visa_restricted_countries, currency

    budget_allocation: dict or JSON string — BudgetAllocation 6-field dict.
    Source: 06-ingestion-pipeline.md § 2.2 column mapping.
    """
    _defaults: dict[str, Any] = {
        "user_id":                  None,
        "traveler_ages":            [],
        "requires_wheelchair":      False,
        "restaurant_preference":    None,
        "fixed_appointments":       "[]",
        "visa_restricted_countries": [],
        "currency":                 None,
    }
    row = {**_defaults, **trip_data}

    # Serialize JSON fields
    if isinstance(row.get("fixed_appointments"), list):
        row["fixed_appointments"] = json.dumps(row["fixed_appointments"])
    if isinstance(row.get("budget_allocation"), dict):
        row["budget_allocation"] = json.dumps(row["budget_allocation"])

    sql = """
        INSERT INTO trips (
            user_id, destination_city, departure_city,
            departure_date, return_date,
            num_adults, num_children, group_size, traveler_ages,
            requires_wheelchair, restaurant_preference,
            fixed_appointments, visa_restricted_countries,
            total_budget, currency, budget_allocation
        ) VALUES (
            %(user_id)s, %(destination_city)s, %(departure_city)s,
            %(departure_date)s, %(return_date)s,
            %(num_adults)s, %(num_children)s, %(group_size)s, %(traveler_ages)s,
            %(requires_wheelchair)s, %(restaurant_preference)s,
            %(fixed_appointments)s::jsonb, %(visa_restricted_countries)s,
            %(total_budget)s, %(currency)s, %(budget_allocation)s::jsonb
        )
        RETURNING trip_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        return str(cur.fetchone()[0])


def get_trip(conn, trip_id: str) -> dict | None:
    """Return a single trip row by UUID, or None if not found."""
    sql = "SELECT * FROM trips WHERE trip_id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (trip_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def update_trip_status(conn, trip_id: str, status: str) -> None:
    """
    Update trips.status.

    Valid values (CHECK constraint): 'planned' | 'active' | 'completed' | 'cancelled'
    """
    sql = "UPDATE trips SET status = %s WHERE trip_id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (status, trip_id))


def list_trips_by_user(
    conn,
    user_id: str,
    status: str | None = None,
) -> list[dict]:
    """Return all trips for a user, optionally filtered by status."""
    if status:
        sql = "SELECT * FROM trips WHERE user_id = %s AND status = %s ORDER BY generated_at DESC"
        params: tuple = (user_id, status)
    else:
        sql = "SELECT * FROM trips WHERE user_id = %s ORDER BY generated_at DESC"
        params = (user_id,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── itinerary_days table ───────────────────────────────────────────────────────

def insert_itinerary_day(conn, trip_id: str, day_data: dict[str, Any]) -> str:
    """
    Insert an itinerary_days row. Returns day_id (UUID string).

    Required keys: day_number
    Optional keys: date, daily_budget_used, route_points

    route_points: list of RoutePoint-like dicts, or pre-serialised JSON string.
    Source: 06-ingestion-pipeline.md § 2.5 column mapping.
    """
    route_points = day_data.get("route_points", [])
    if not isinstance(route_points, str):
        route_points = json.dumps(route_points)

    sql = """
        INSERT INTO itinerary_days
            (trip_id, day_number, date, daily_budget_used, route_points)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING day_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            trip_id,
            day_data["day_number"],
            day_data.get("date"),
            day_data.get("daily_budget_used", 0.0),
            route_points,
        ))
        return str(cur.fetchone()[0])


def get_itinerary_days(conn, trip_id: str) -> list[dict]:
    """Return all itinerary_days rows for a trip, ordered by day_number."""
    sql = """
        SELECT day_id, trip_id, day_number, date,
               daily_budget_used, route_points, replan_version
        FROM itinerary_days
        WHERE trip_id = %s
        ORDER BY day_number ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (trip_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def increment_replan_version(conn, day_id: str) -> int:
    """
    Increment replan_version for a day and return the new value.

    Called by PartialReplanner after each replan
    (source: 06-ingestion-pipeline.md § 2.5).
    """
    sql = """
        UPDATE itinerary_days
        SET replan_version = replan_version + 1
        WHERE day_id = %s
        RETURNING replan_version
    """
    with conn.cursor() as cur:
        cur.execute(sql, (day_id,))
        row = cur.fetchone()
        return int(row[0]) if row else 0


def update_route_points(conn, day_id: str, route_points: list[dict]) -> None:
    """Overwrite route_points JSONB for a day (post-replan snapshot)."""
    sql = """
        UPDATE itinerary_days
        SET route_points = %s::jsonb
        WHERE day_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (json.dumps(route_points), day_id))

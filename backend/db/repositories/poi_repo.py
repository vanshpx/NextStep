"""
db/repositories/poi_repo.py
------------------------------
CRUD operations for the `poi` and `poi_graph_edges` tables.

Source: docs/database/05-implementation.sql Tables poi, poi_graph_edges
Source: docs/database/06-ingestion-pipeline.md § 4.1 (Dij computation)

All functions accept a psycopg2 connection object.
Commit/rollback is managed by the caller via db.connection.get_conn().
"""

from __future__ import annotations

import json
from typing import Any


# ── poi table ──────────────────────────────────────────────────────────────────

def upsert_poi(conn, poi: dict[str, Any]) -> str:
    """
    Insert or update a POI row.

    On conflict (same city + name), updates all mutable fields and
    refreshes fetched_at to NOW().

    Args:
        conn: psycopg2 connection
        poi:  dict with any subset of poi column keys.
              Required: city, name, location_lat, location_lon.

    Returns:
        poi_id (UUID string) of the inserted/updated row.
    """
    _defaults: dict[str, Any] = {
        "opening_hours":              None,
        "rating":                     None,
        "visit_duration_minutes":     60,
        "min_visit_duration_minutes": 15,
        "entry_cost":                 0.0,
        "category":                   None,
        "optimal_visit_time":         None,
        "wheelchair_accessible":      True,
        "min_age":                    0,
        "ticket_required":            False,
        "min_group_size":             1,
        "max_group_size":             999,
        "seasonal_open_months":       [],
        "is_outdoor":                 False,
        "intensity_level":            "low",
        "historical_importance":      None,
        "source_api":                 "manual",
        "raw_api_response":           "{}",
    }
    row = {**_defaults, **poi}
    if isinstance(row.get("raw_api_response"), dict):
        row["raw_api_response"] = json.dumps(row["raw_api_response"])

    sql = """
        INSERT INTO poi (
            city, name, location_lat, location_lon,
            opening_hours, rating,
            visit_duration_minutes, min_visit_duration_minutes, entry_cost,
            category, optimal_visit_time, wheelchair_accessible, min_age,
            ticket_required, min_group_size, max_group_size,
            seasonal_open_months, is_outdoor, intensity_level,
            historical_importance, source_api, raw_api_response
        ) VALUES (
            %(city)s, %(name)s, %(location_lat)s, %(location_lon)s,
            %(opening_hours)s, %(rating)s,
            %(visit_duration_minutes)s, %(min_visit_duration_minutes)s,
            %(entry_cost)s, %(category)s, %(optimal_visit_time)s,
            %(wheelchair_accessible)s, %(min_age)s, %(ticket_required)s,
            %(min_group_size)s, %(max_group_size)s, %(seasonal_open_months)s,
            %(is_outdoor)s, %(intensity_level)s, %(historical_importance)s,
            %(source_api)s, %(raw_api_response)s::jsonb
        )
        ON CONFLICT (city, name) DO UPDATE SET
            location_lat               = EXCLUDED.location_lat,
            location_lon               = EXCLUDED.location_lon,
            opening_hours              = EXCLUDED.opening_hours,
            rating                     = EXCLUDED.rating,
            visit_duration_minutes     = EXCLUDED.visit_duration_minutes,
            min_visit_duration_minutes = EXCLUDED.min_visit_duration_minutes,
            entry_cost                 = EXCLUDED.entry_cost,
            category                   = EXCLUDED.category,
            wheelchair_accessible      = EXCLUDED.wheelchair_accessible,
            min_age                    = EXCLUDED.min_age,
            historical_importance      = EXCLUDED.historical_importance,
            source_api                 = EXCLUDED.source_api,
            raw_api_response           = EXCLUDED.raw_api_response,
            fetched_at                 = NOW()
        RETURNING poi_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
        return str(cur.fetchone()[0])


def get_pois_by_city(conn, city: str) -> list[dict]:
    """Return all POI rows for a city as a list of dicts."""
    sql = """
        SELECT poi_id, city, name, location_lat, location_lon,
               opening_hours, rating, visit_duration_minutes,
               min_visit_duration_minutes, entry_cost, category,
               optimal_visit_time, wheelchair_accessible, min_age,
               ticket_required, min_group_size, max_group_size,
               seasonal_open_months, is_outdoor, intensity_level,
               historical_importance, source_api, raw_api_response, fetched_at
        FROM poi
        WHERE city = %s
        ORDER BY fetched_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (city,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_poi_by_id(conn, poi_id: str) -> dict | None:
    """Return a single POI row by UUID."""
    sql = "SELECT * FROM poi WHERE poi_id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (poi_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def update_historical_importance(conn, poi_id: str, text: str) -> None:
    """
    Set historical_importance on an existing POI.

    Called by HistoricalInsightTool when an empty column is detected at first
    trip request to that POI (source: 06-ingestion-pipeline.md § 3.2).
    """
    sql = "UPDATE poi SET historical_importance = %s WHERE poi_id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (text, poi_id))


def delete_pois_older_than(conn, city: str, days: int = 30) -> int:
    """
    Delete stale POI rows for a city (age > `days` days).

    Used by the scheduled 30-day refresh job
    (source: 06-ingestion-pipeline.md § 3.2).
    Returns count of deleted rows.
    """
    sql = """
        DELETE FROM poi
        WHERE city = %s
          AND fetched_at < NOW() - INTERVAL '%s days'
    """
    with conn.cursor() as cur:
        cur.execute(sql, (city, days))
        return cur.rowcount


# ── poi_graph_edges table ──────────────────────────────────────────────────────

def upsert_graph_edge(
    conn,
    city: str,
    poi_a_id: str,
    poi_b_id: str,
    transport_mode: str,
    travel_time_minutes: float,
) -> None:
    """
    Insert or update a travel-time edge.

    On conflict (unique constraint uq_poi_graph_edges), updates
    travel_time_minutes and last_updated.

    Source: 06-ingestion-pipeline.md § 4.1 (Dij matrix upsert).
    """
    sql = """
        INSERT INTO poi_graph_edges
            (city, poi_a_id, poi_b_id, transport_mode, travel_time_minutes, last_updated)
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, NOW())
        ON CONFLICT (city, poi_a_id, poi_b_id, transport_mode)
        DO UPDATE SET
            travel_time_minutes = EXCLUDED.travel_time_minutes,
            last_updated        = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(sql, (city, poi_a_id, poi_b_id, transport_mode, travel_time_minutes))


def get_graph_edges_by_city(
    conn,
    city: str,
    transport_mode: str | None = None,
) -> list[dict]:
    """
    Return poi_graph_edges rows for a city.

    Optionally filter by transport_mode.
    Returns list of dicts: {poi_a_id, poi_b_id, transport_mode, travel_time_minutes}.
    """
    if transport_mode:
        sql = """
            SELECT poi_a_id::text, poi_b_id::text,
                   transport_mode, travel_time_minutes
            FROM poi_graph_edges
            WHERE city = %s AND transport_mode = %s
        """
        params: tuple = (city, transport_mode)
    else:
        sql = """
            SELECT poi_a_id::text, poi_b_id::text,
                   transport_mode, travel_time_minutes
            FROM poi_graph_edges
            WHERE city = %s
        """
        params = (city,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def delete_poi_edges(conn, poi_id: str) -> int:
    """
    Delete all edges involving a POI (both directions).

    Called when a POI is removed from the city catalog
    (source: 06-ingestion-pipeline.md § 4.2).
    Returns count of deleted rows.
    """
    sql = """
        DELETE FROM poi_graph_edges
        WHERE poi_a_id = %s::uuid OR poi_b_id = %s::uuid
    """
    with conn.cursor() as cur:
        cur.execute(sql, (poi_id, poi_id))
        return cur.rowcount

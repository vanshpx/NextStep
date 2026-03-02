"""
db/repositories/disruption_repo.py
-------------------------------------
CRUD for the `disruption_events` table.

Source: docs/database/05-implementation.sql Table disruption_events
Source: docs/database/06-ingestion-pipeline.md § 2.6

All functions accept a psycopg2 connection object.
Commit/rollback is managed by the caller via db.connection.get_conn().
"""

from __future__ import annotations

import json
from typing import Any


# Values allowed by the CHECK constraint on disruption_events.event_type
_VALID_EVENT_TYPES = frozenset({
    "weather", "traffic", "crowd", "hunger", "fatigue",
    "venue_closed", "user_skip", "user_replace",
    "user_reorder", "manual_reopt", "generic",
})

# Values allowed by the CHECK constraint on disruption_events.user_response
_VALID_USER_RESPONSES = frozenset({
    "APPROVE", "REJECT", "MODIFY", "accepted", "skipped",
})


def insert_disruption_event(conn, trip_id: str, event: dict[str, Any]) -> str:
    """
    Insert one row into disruption_events. Returns event_id (UUID string).

    Mandatory key:
        event_type  — normalized to 'generic' if not in allowlist

    Optional keys (default to None / empty / 0.0 if absent):
        day_number, trigger_time, severity, impacted_stops,
        action_taken, user_response, s_pti_affected, metadata

    Column mapping source: 06-ingestion-pipeline.md § 2.6.
    """
    event_type = event.get("event_type", "generic")
    if event_type not in _VALID_EVENT_TYPES:
        event_type = "generic"

    user_response = event.get("user_response")
    if user_response not in _VALID_USER_RESPONSES:
        user_response = None

    metadata = event.get("metadata", {})
    if not isinstance(metadata, str):
        metadata = json.dumps(metadata)

    impacted_stops = event.get("impacted_stops", [])
    if isinstance(impacted_stops, str):
        impacted_stops = [impacted_stops]

    sql = """
        INSERT INTO disruption_events (
            trip_id, day_number, event_type, trigger_time,
            severity, impacted_stops, action_taken,
            user_response, s_pti_affected, metadata
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s::jsonb
        )
        RETURNING event_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            trip_id,
            event.get("day_number", 1),
            event_type,
            event.get("trigger_time"),
            float(event.get("severity", 0.0)),
            impacted_stops,
            event.get("action_taken"),
            user_response,
            event.get("s_pti_affected"),
            metadata,
        ))
        return str(cur.fetchone()[0])


def get_disruption_events(
    conn,
    trip_id: str,
    event_type: str | None = None,
) -> list[dict]:
    """
    Return disruption_events rows for a trip, ordered by recorded_at.

    Optionally filter by event_type.
    """
    if event_type:
        sql = """
            SELECT * FROM disruption_events
            WHERE trip_id = %s AND event_type = %s
            ORDER BY recorded_at ASC
        """
        params: tuple = (trip_id, event_type)
    else:
        sql = """
            SELECT * FROM disruption_events
            WHERE trip_id = %s
            ORDER BY recorded_at ASC
        """
        params = (trip_id,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

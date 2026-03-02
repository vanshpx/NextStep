"""
db/promoter.py
--------------
Promotes in-memory DisruptionMemory records to the `disruption_events`
Postgres table at trip completion or session end.

Architecture
────────────
This module is the bridge between the in-process reoptimization session and
the persistent DB tier:

    Session end (trip completed / cancelled):
        promote_disruption_memory(conn, trip_id, memory)
            → iterates each record type
            → calls disruption_repo.insert_disruption_event() for each
            → returns total rows inserted

Data exclusion rules observed (source: 04-data-exclusions.md):
    Rule 6 — Hunger/fatigue level TIME-SERIES beyond session → NOT promoted
             (we store one row per event, not the full time-series)
    Rule 7 — TripState.deferred_stops / skipped_stops post-trip → NOT stored
             (those fields live only in TripState Redis hash during the session)
    Rule 1 — ACO pheromone matrix → never touched here

Column mapping: docs/database/06-ingestion-pipeline.md § 2.6
"""

from __future__ import annotations

from modules.memory.disruption_memory import (
    DisruptionMemory,
    WeatherRecord,
    TrafficRecord,
    ReplacementRecord,
    HungerRecord,
    FatigueRecord,
)
from db.repositories.disruption_repo import insert_disruption_event


def promote_disruption_memory(
    conn,
    trip_id:    str,
    memory:     DisruptionMemory,
    day_number: int = 1,
) -> int:
    """
    Write all in-memory disruption records to the disruption_events table.

    Args:
        conn:       psycopg2 connection. Commit/rollback handled by caller.
        trip_id:    UUID string matching trips.trip_id.
        memory:     DisruptionMemory instance collected during the session.
        day_number: Day context for record types that don't carry their own
                    day number (default 1). Pass the final day of the session
                    or compute per-record if available.

    Returns:
        Total number of rows inserted.
    """
    inserted = 0

    # ── Weather events ────────────────────────────────────────────────────────
    for rec in memory.weather_history:
        insert_disruption_event(conn, trip_id, _from_weather(rec, day_number))
        inserted += 1

    # ── Traffic events ────────────────────────────────────────────────────────
    for rec in memory.traffic_history:
        insert_disruption_event(conn, trip_id, _from_traffic(rec, day_number))
        inserted += 1

    # ── Replacement events ────────────────────────────────────────────────────
    # event_type = "user_replace" (closest enum value in CHECK constraint)
    for rec in memory.replacement_history:
        insert_disruption_event(conn, trip_id, _from_replacement(rec, day_number))
        inserted += 1

    # ── Hunger events ─────────────────────────────────────────────────────────
    for rec in memory.hunger_history:
        insert_disruption_event(conn, trip_id, _from_hunger(rec, day_number))
        inserted += 1

    # ── Fatigue events ────────────────────────────────────────────────────────
    for rec in memory.fatigue_history:
        insert_disruption_event(conn, trip_id, _from_fatigue(rec, day_number))
        inserted += 1

    return inserted


# ── Private converters ─────────────────────────────────────────────────────────

def _from_weather(rec: WeatherRecord, day_number: int) -> dict:
    action = "BLOCKED" if rec.blocked_count else "DEFERRED"
    return {
        "day_number":    day_number,
        "event_type":    "weather",
        "trigger_time":  None,
        "severity":      rec.severity,
        "impacted_stops": [],
        "action_taken":  action,
        "user_response": "accepted" if rec.replan_accepted else "skipped",
        "s_pti_affected": None,
        "metadata": {
            "condition":         rec.condition,
            "threshold":         rec.threshold,
            "blocked_count":     rec.blocked_count,
            "deferred_count":    rec.deferred_count,
            "alternatives_used": rec.alternatives_used,
        },
    }


def _from_traffic(rec: TrafficRecord, day_number: int) -> dict:
    # Determine primary action taken: DEFER if stops were deferred, else REPLACE
    action = "DEFER" if rec.deferred_stops else "REPLACE"
    return {
        "day_number":    day_number,
        "event_type":    "traffic",
        "trigger_time":  None,
        "severity":      rec.traffic_level,
        "impacted_stops": rec.deferred_stops + rec.replaced_stops,
        "action_taken":  action,
        "user_response": "accepted" if rec.replan_accepted else "skipped",
        "s_pti_affected": None,
        "metadata": {
            "traffic_level": rec.traffic_level,
            "threshold":     rec.threshold,
            "delay_minutes": rec.delay_minutes,
            "delay_factor":  rec.delay_factor,
        },
    }


def _from_replacement(rec: ReplacementRecord, day_number: int) -> dict:
    return {
        "day_number":     day_number,
        "event_type":     "user_replace",
        "trigger_time":   None,
        "severity":       0.0,
        "impacted_stops": [rec.original_stop],
        "action_taken":   f"REPLACE→{rec.replacement_stop}",
        "user_response":  "APPROVE",
        "s_pti_affected": rec.S_pti_original,
        "metadata": {
            "original_stop":     rec.original_stop,
            "replacement_stop":  rec.replacement_stop,
            "reason":            rec.reason,
            "S_pti_original":    rec.S_pti_original,
            "S_pti_replacement": rec.S_pti_replacement,
        },
    }


def _from_hunger(rec: HungerRecord, day_number: int) -> dict:
    return {
        "day_number":     day_number,
        "event_type":     "hunger",
        "trigger_time":   rec.trigger_time,
        "severity":       rec.hunger_level,
        "impacted_stops": [rec.restaurant_name] if rec.restaurant_name else [],
        "action_taken":   rec.action_taken,
        "user_response":  rec.user_response,
        "s_pti_affected": rec.S_pti_inserted,
        "metadata": {
            "hunger_level":    rec.hunger_level,
            "restaurant_name": rec.restaurant_name,
        },
    }


def _from_fatigue(rec: FatigueRecord, day_number: int) -> dict:
    return {
        "day_number":     day_number,
        "event_type":     "fatigue",
        "trigger_time":   rec.trigger_time,
        "severity":       rec.fatigue_level,
        "impacted_stops": rec.stops_deferred,
        "action_taken":   rec.action_taken,
        "user_response":  rec.user_response,
        "s_pti_affected": None,
        "metadata": {
            "fatigue_level":  rec.fatigue_level,
            "rest_duration":  rec.rest_duration,
            "stops_deferred": rec.stops_deferred,
        },
    }

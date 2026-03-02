"""
db/redis_client.py
-------------------
redis-py client — singleton plus helpers for the two key schemas.

Key schemas (source: docs/database/05-implementation.sql PART 2):

  1. dij:{city}:{poi_a_id}:{poi_b_id}:{transport_mode}
       Type : String (float as text)
       TTL  : DIJ_CACHE_TTL  (default 2,592,000 s = 30 days)
       Value: travel_time_minutes  e.g. "18.5"

  2. tripstate:{trip_id}:{user_id}
       Type : Hash
       TTL  : TRIP_STATE_TTL (default 86,400 s = 24 hours; reset on each write)
       Fields: current_time, current_lat, current_lon, current_day,
               visited_stops, skipped_stops, deferred_stops,
               hunger_level, fatigue_level, last_meal_time, last_rest_time,
               minutes_on_feet, replan_pending, pending_decision,
               budget_spent, disruption_memory_snapshot

Environment variables (set in config.py):
    REDIS_HOST        default: localhost
    REDIS_PORT        default: 6379
    REDIS_DB          default: 0
    REDIS_PASSWORD    default: ""  (empty = no auth)
    DIJ_CACHE_TTL     default: 2592000
    TRIP_STATE_TTL    default: 86400
"""

from __future__ import annotations

import json
from typing import Any

import redis

import config

# Module-level singleton; initialised lazily on first call to get_redis()
_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return the singleton Redis client, creating it on first call."""
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {
            "host":             config.REDIS_HOST,
            "port":             config.REDIS_PORT,
            "db":               config.REDIS_DB,
            "decode_responses": True,   # return str, not bytes
        }
        if config.REDIS_PASSWORD:
            kwargs["password"] = config.REDIS_PASSWORD
        _client = redis.Redis(**kwargs)
    return _client


# ── Dij edge cache ─────────────────────────────────────────────────────────────

def _dij_key(city: str, poi_a_id: str, poi_b_id: str, mode: str) -> str:
    return f"dij:{city}:{poi_a_id}:{poi_b_id}:{mode}"


def get_dij(
    city: str,
    poi_a_id: str,
    poi_b_id: str,
    mode: str,
) -> float | None:
    """
    Lookup a travel time from the Redis dij cache.

    Returns float minutes, or None on cache miss.
    Caller should fall back to Postgres poi_graph_edges on None.
    """
    val = get_redis().get(_dij_key(city, poi_a_id, poi_b_id, mode))
    return float(val) if val is not None else None


def set_dij(
    city: str,
    poi_a_id: str,
    poi_b_id: str,
    mode: str,
    minutes: float,
) -> None:
    """Write one dij entry with DIJ_CACHE_TTL expiry."""
    get_redis().setex(
        _dij_key(city, poi_a_id, poi_b_id, mode),
        config.DIJ_CACHE_TTL,
        str(minutes),
    )


def warm_dij_cache(city: str, edges: list[dict]) -> int:
    """
    Bulk-load Dij edges into Redis using a pipeline (single round-trip).

    Args:
        city:  City name matching the cache key pattern.
        edges: List of dicts with keys:
               poi_a_id, poi_b_id, transport_mode, travel_time_minutes

    Returns:
        Number of keys written.
    """
    r = get_redis()
    pipe = r.pipeline()
    for edge in edges:
        key = _dij_key(
            city,
            str(edge["poi_a_id"]),
            str(edge["poi_b_id"]),
            edge["transport_mode"],
        )
        pipe.setex(key, config.DIJ_CACHE_TTL, str(edge["travel_time_minutes"]))
    pipe.execute()
    return len(edges)


def invalidate_dij_city(city: str) -> int:
    """
    Delete all dij cache keys for a city.

    Called when poi_graph_edges for the city are updated in Postgres
    (source: 06-ingestion-pipeline.md § 3.3 Cache Invalidation Rules).

    Returns: number of keys deleted.
    """
    r = get_redis()
    keys = list(r.scan_iter(f"dij:{city}:*"))
    if keys:
        return r.delete(*keys)
    return 0


# ── TripState hash ─────────────────────────────────────────────────────────────

def _ts_key(trip_id: str, user_id: str) -> str:
    return f"tripstate:{trip_id}:{user_id}"


def set_trip_state(
    trip_id: str,
    user_id: str,
    fields: dict[str, Any],
) -> None:
    """
    Set/update TripState hash fields, then reset the 24-hour TTL.

    Dict/list values are JSON-encoded automatically.
    Numeric/bool values are stored as plain strings.

    TTL is reset on every call to align with session activity
    (source: 05-implementation.sql § 2.1 — "reset on every HSET").
    """
    r = get_redis()
    key = _ts_key(trip_id, user_id)
    encoded = {
        k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
        for k, v in fields.items()
    }
    r.hset(key, mapping=encoded)
    r.expire(key, config.TRIP_STATE_TTL)


def get_trip_state(trip_id: str, user_id: str) -> dict | None:
    """
    Return all TripState hash fields as a str→str dict.

    Returns None if the key does not exist (session expired or never created).
    """
    r = get_redis()
    data = r.hgetall(_ts_key(trip_id, user_id))
    return data if data else None


def delete_trip_state(trip_id: str, user_id: str) -> None:
    """
    Delete the TripState hash.

    Called when a trip is completed or cancelled
    (source: 05-implementation.sql § 3.3).
    """
    get_redis().delete(_ts_key(trip_id, user_id))

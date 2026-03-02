"""
db/
----
Database access layer for the Travel Itinerary Optimizer.

Storage architecture:
  PostgreSQL (psycopg2) — persistent backing store
    tables: users, user_memory_profile, trips, poi, poi_graph_edges,
            itinerary_days, disruption_events
    schema: docs/database/05-implementation.sql
    apply:  python scripts/run_migrations.py

  Redis (redis-py) — volatile hot cache
    dij:{city}:{poi_a}:{poi_b}:{mode}  TTL = DIJ_CACHE_TTL   (30 days)
    tripstate:{trip_id}:{user_id}       TTL = TRIP_STATE_TTL  (24 h)
    schema: docs/database/05-implementation.sql PART 2

Public exports (import from here for convenience):
    from db import get_conn, get_redis
    from db.repositories import poi_repo, trip_repo, disruption_repo
    from db.promoter import promote_disruption_memory
"""

from db.connection import get_conn, close_pool
from db.redis_client import get_redis

__all__ = ["get_conn", "close_pool", "get_redis"]

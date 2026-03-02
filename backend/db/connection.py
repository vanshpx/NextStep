"""
db/connection.py
-----------------
psycopg2 ThreadedConnectionPool — singleton, shared across the process.

Usage:
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

The context manager borrows a connection from the pool, commits on clean
exit, rolls back on exception, and returns the connection to the pool.

Environment variables (set in config.py):
    POSTGRES_HOST       default: localhost
    POSTGRES_PORT       default: 5432
    POSTGRES_DB         default: nextstep
    POSTGRES_USER       default: nextstep_user
    POSTGRES_PASSWORD   default: nextstep_pass
    POSTGRES_MIN_CONN   default: 1
    POSTGRES_MAX_CONN   default: 10
"""

from __future__ import annotations

import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from typing import Generator

import config

# Module-level singleton; initialised lazily on first call to get_conn()
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _build_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Create and return a new ThreadedConnectionPool from config values."""
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=config.POSTGRES_MIN_CONN,
        maxconn=config.POSTGRES_MAX_CONN,
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the singleton connection pool, creating it on first call."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = _build_pool()
    return _pool


@contextmanager
def get_conn() -> Generator:
    """
    Context manager: borrow a psycopg2 connection from the pool.

    On success: commits and returns the connection.
    On exception: rolls back and re-raises.
    Always: returns the connection to the pool.

    Example::

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO poi ...")
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_pool() -> None:
    """Close all connections in the pool (call at application shutdown)."""
    global _pool
    if _pool and not _pool.closed:
        _pool.closeall()
    _pool = None

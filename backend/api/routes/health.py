"""
api/routes/health.py
--------------------
Health-check endpoint — used by load balancers, Docker health probes, etc.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health check")
def health() -> dict:
    """Returns 200 OK when the service is running."""
    return {"status": "ok", "service": "nextstep-backend"}

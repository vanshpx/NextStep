"""
api/server.py
-------------
FastAPI application entry point.

Run dev server:
    cd backend
    uvicorn api.server:app --reload --port 8000

Endpoints:
    GET  /v1/health
    POST /v1/itinerary/generate
    POST /v1/reoptimize/advance
    POST /v1/reoptimize/event
    POST /v1/reoptimize/check
    POST /v1/reoptimize/resolve
    GET  /v1/reoptimize/summary/{session_id}
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import health, itinerary, reoptimize

app = FastAPI(
    title="NextStep Travel Optimizer API",
    version="1.0.0",
    description=(
        "FTRM+ACO travel itinerary optimizer backend. "
        "Integrates Google Places, OSRM, OpenWeatherMap, and Google Routes."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the Next.js frontend (any origin during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,      prefix="/v1",            tags=["Health"])
app.include_router(itinerary.router,   prefix="/v1/itinerary",  tags=["Itinerary"])
app.include_router(reoptimize.router,  prefix="/v1/reoptimize", tags=["ReOptimize"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)

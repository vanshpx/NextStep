"""
scripts/bootstrap_city.py
--------------------------
One-time city data bootstrap job.

For each city it:
  1. Fetches real attractions via AttractionTool (Google Places)
  2. Validates every POI record (§ 5.5 checks)
  3. Computes the Dij travel-time matrix via DistanceTool (OSRM / haversine)
  4. Validates every graph edge (travel_time >= 0; no self-edges; no NULLs)
  5. Saves a canonical JSON snapshot to --output

The output JSON is the authoritative pre-computed dataset for a city.
It can be:
  - Served directly by the optimizer (load-from-file mode)
  - Ingested into PostgreSQL `poi` + `poi_graph_edges` tables (task 9)
  - Warmed into Redis Dij cache (task 10)

Usage:
    cd backend
    python scripts/bootstrap_city.py --city Delhi
    python scripts/bootstrap_city.py --city Paris --output data/bootstrap/paris.json
    python scripts/bootstrap_city.py --city Delhi --mode walking
    python scripts/bootstrap_city.py --city Delhi --mode driving

Options:
    --city     City name (must match a key in _CITY_CENTERS or be geocodable)
    --output   Output JSON path (default: data/bootstrap/<city_slug>.json)
    --mode     OSRM travel mode: walking (default) | driving
    --stub     Use stub AttractionTool data (no API call; for offline testing)
    --dry-run  Fetch + validate but do NOT write the output file; print summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ── Make sure backend root is on path ─────────────────────────────────────────
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ── Imports (after path fix) ───────────────────────────────────────────────────
import config  # noqa: E402  (must come after sys.path fix)
from modules.tool_usage.attraction_tool import AttractionTool, AttractionRecord
from modules.tool_usage.distance_tool import DistanceTool
from modules.validation import (
    validate_attraction, validate_graph_edge, filter_valid,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _city_slug(city: str) -> str:
    """E.g. "New Delhi" → "new_delhi"."""
    return city.strip().lower().replace(" ", "_")


def _record_to_poi_dict(r: AttractionRecord, city: str) -> dict:
    """Convert AttractionRecord to the canonical poi-table shape."""
    return {
        "city":                       city,
        "name":                       r.name,
        "location_lat":               r.location_lat,
        "location_lon":               r.location_lon,
        "opening_hours":              r.opening_hours,
        "rating":                     r.rating,
        "category":                   r.category,
        "visit_duration_minutes":     r.visit_duration_minutes,
        "min_visit_duration_minutes": r.min_visit_duration_minutes,
        "wheelchair_accessible":      r.wheelchair_accessible,
        "is_outdoor":                 r.is_outdoor,
        "historical_importance":      r.historical_importance,
        "source_api":                 "google_places",
        "fetched_at":                 datetime.now(timezone.utc).isoformat(),
    }


def _build_edge_records(
    records: list[AttractionRecord],
    city: str,
    mode: str,
) -> list[dict]:
    """
    Compute the full N×N Dij matrix (one OSRM Table call) and return
    edge records in poi_graph_edges shape.
    OSRM mode string: "foot" → walking, "driving" → driving.
    """
    if not records:
        return []

    transport_map = {"foot": "walking", "driving": "car"}
    transport_label = transport_map.get(mode, mode)

    coords = [(r.location_lat, r.location_lon) for r in records]

    print(f"  [Dij] Computing {len(records)}×{len(records)} matrix via OSRM (mode={mode}) …")
    dt = DistanceTool()
    matrix = dt.travel_time_matrix(coords, mode=mode)

    edges: list[dict] = []
    n = len(records)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue   # self-edges excluded
            tt = matrix[i][j]
            if tt is None or tt < 0:
                continue   # no route or invalid
            edges.append(
                {
                    "city":                 city,
                    "poi_a_name":           records[i].name,   # resolved to poi_id at DB insert
                    "poi_b_name":           records[j].name,
                    "poi_a_lat":            records[i].location_lat,
                    "poi_a_lon":            records[i].location_lon,
                    "poi_b_lat":            records[j].location_lat,
                    "poi_b_lon":            records[j].location_lon,
                    "transport_mode":       transport_label,
                    "travel_time_minutes":  tt,
                }
            )
    return edges


# ── Main bootstrap function ────────────────────────────────────────────────────

def bootstrap_city(
    city: str,
    output_path: str,
    mode: str = "foot",
    use_stub: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Run the full bootstrap pipeline for one city.

    Returns the output dict (whether or not it was written to disk).
    """
    print(f"\n{'='*60}")
    print(f"  BOOTSTRAP: {city.upper()}")
    print(f"{'='*60}")
    print(f"  mode={mode}  stub={use_stub}  dry_run={dry_run}")

    # ── Step 1: Fetch POIs ─────────────────────────────────────────────────
    print(f"\n[Step 1] Fetching attractions …")
    if use_stub:
        os.environ["USE_STUB_ATTRACTIONS"] = "true"
    else:
        os.environ["USE_STUB_ATTRACTIONS"] = "false"

    records: list[AttractionRecord] = AttractionTool().fetch(city)
    print(f"  Fetched {len(records)} records.")

    # ── Step 2: Validate POIs ──────────────────────────────────────────────
    print(f"\n[Step 2] Validating {len(records)} POI records …")
    valid_records = filter_valid(
        records,
        validate_attraction,
        to_dict=lambda r: r.__dict__,
        log=True,
    )
    print(f"  → {len(valid_records)} valid POIs after validation.")

    if not valid_records:
        print("  ERROR: No valid POIs remain. Aborting bootstrap.")
        return {}

    poi_dicts = [_record_to_poi_dict(r, city) for r in valid_records]

    # ── Step 3: Compute Dij matrix ─────────────────────────────────────────
    print(f"\n[Step 3] Computing Dij travel-time matrix …")
    raw_edges = _build_edge_records(valid_records, city, mode)
    print(f"  Computed {len(raw_edges)} raw edges.")

    # ── Step 4: Validate edges ─────────────────────────────────────────────
    print(f"\n[Step 4] Validating edge records …")
    valid_edges = filter_valid(
        raw_edges,
        validate_graph_edge,
        to_dict=lambda e: e,   # already dicts
        log=True,
    )
    print(f"  → {len(valid_edges)} valid edges after validation.")

    # ── Step 5: Build output ───────────────────────────────────────────────
    output = {
        "city":           city,
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "travel_mode":    mode,
        "poi_count":      len(poi_dicts),
        "edge_count":     len(valid_edges),
        "pois":           poi_dicts,
        "edges":          valid_edges,
    }

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  SUMMARY")
    print(f"{'─'*60}")
    print(f"  City              : {city}")
    print(f"  Valid POIs        : {len(poi_dicts)}")
    print(f"  Valid edges       : {len(valid_edges)}")
    print(f"  Travel mode       : {mode}")
    if not dry_run:
        print(f"  Output file       : {output_path}")

    if dry_run:
        print("  (dry-run — output file NOT written)")
        return output

    # ── Step 5: Write JSON ─────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False, default=str)
    print(f"\n  ✓ Written → {output_path}")

    return output


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Bootstrap city POI + Dij data from Google Places + OSRM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--city",    required=True, help="City name e.g. 'Delhi'")
    p.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: data/bootstrap/<city_slug>.json)",
    )
    p.add_argument(
        "--mode",
        default="foot",
        choices=["foot", "driving"],
        help="OSRM travel mode (default: foot)",
    )
    p.add_argument(
        "--stub",
        action="store_true",
        help="Use stub attraction data (offline / testing)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Fetch + validate but do NOT write the output file",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    output_path = args.output or os.path.join(
        _BACKEND_DIR, "data", "bootstrap", f"{_city_slug(args.city)}.json"
    )

    result = bootstrap_city(
        city=args.city,
        output_path=output_path,
        mode=args.mode,
        use_stub=args.stub,
        dry_run=args.dry_run,
    )

    if not result:
        sys.exit(1)

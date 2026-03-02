"""
modules/validation/ingestion_validator.py
------------------------------------------
Data-quality guards applied before any POI, graph-edge, or trip record
is written to storage (DB, cache, or bootstrap JSON).

Implements the checks specified in 06-ingestion-pipeline.md § 5.5:

  POI (attraction / restaurant / hotel / flight):
    ✓ Non-null coordinates
    ✓ Latitude in [-90, 90]
    ✓ Longitude in [-180, 180]
    ✓ Coordinates are not both exactly 0.0 (likely missing)
    ✓ Non-empty name
    ✓ Rating in [1, 5] if present (0.0 treated as absent)

  Graph edge (poi_graph_edges):
    ✓ travel_time_minutes is not NULL
    ✓ travel_time_minutes >= 0
    ✓ poi_a_id ≠ poi_b_id  (self-edge exclusion)

  Trip:
    ✓ total_budget >= 0
    ✓ return_date >= departure_date
    ✓ day_number > 0

Usage:
    from modules.validation import validate_attraction, validate_graph_edge

    result = validate_attraction(record.__dict__)
    if not result.valid:
        print(result.errors)

    clean_records = filter_valid(records, validate_attraction)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, TypeVar

T = TypeVar("T")


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Outcome of a single validation run.

    Attributes:
        valid:  True iff there are zero errors.
        errors: Human-readable list of failure reasons.
        record: The input record dict (for logging purposes).
    """
    valid: bool
    errors: list[str] = field(default_factory=list)
    record: dict = field(default_factory=dict, repr=False)

    def __bool__(self) -> bool:
        return self.valid


# ── POI validation ─────────────────────────────────────────────────────────────

def validate_attraction(record: dict[str, Any]) -> ValidationResult:
    """
    Validate a POI record (attraction / restaurant / hotel / flight)
    before writing to the `poi` table or bootstrap JSON.

    Checks (§ 5.5):
      - location_lat / location_lon: non-null, in valid range, not both 0.0
      - name: non-empty
      - rating: in [1, 5] if present
    """
    errors: list[str] = []

    # ── Coordinates ────────────────────────────────────────────────────────
    lat = record.get("location_lat")
    lon = record.get("location_lon")

    if lat is None or lon is None:
        errors.append(
            f"location_lat/location_lon must not be NULL "
            f"(got lat={lat!r}, lon={lon!r})"
        )
    else:
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            errors.append(
                f"location_lat/location_lon must be numeric "
                f"(got lat={lat!r}, lon={lon!r})"
            )
            return ValidationResult(valid=False, errors=errors, record=record)

        if not (-90.0 <= lat <= 90.0):
            errors.append(f"location_lat={lat} is outside valid range [-90, 90]")

        if not (-180.0 <= lon <= 180.0):
            errors.append(f"location_lon={lon} is outside valid range [-180, 180]")

        if lat == 0.0 and lon == 0.0:
            errors.append(
                "location_lat=0.0 and location_lon=0.0: likely a missing/default "
                "value — the null island (0°N, 0°E) is not a valid attraction"
            )

    # ── Name ───────────────────────────────────────────────────────────────
    name = record.get("name", "")
    if not name or not str(name).strip():
        errors.append("name must not be empty or NULL")

    # ── Rating ─────────────────────────────────────────────────────────────
    rating = record.get("rating")
    if rating is not None:
        try:
            r = float(rating)
            # 0.0 is the sentinel for "absent" — treated as NULL, not invalid
            if r != 0.0 and not (1.0 <= r <= 5.0):
                errors.append(
                    f"rating={r} is outside valid range [1, 5] "
                    f"(use 0.0 or None to signal absent)"
                )
        except (TypeError, ValueError):
            errors.append(f"rating={rating!r} must be numeric")

    return ValidationResult(valid=len(errors) == 0, errors=errors, record=record)


# ── Graph edge validation ──────────────────────────────────────────────────────

def validate_graph_edge(record: dict[str, Any]) -> ValidationResult:
    """
    Validate a `poi_graph_edges` record before write.

    Checks (§ 5.5):
      - travel_time_minutes: not NULL, >= 0
      - poi_a_id ≠ poi_b_id  (self-edge excluded)
    """
    errors: list[str] = []

    # ── Travel time ────────────────────────────────────────────────────────
    tt = record.get("travel_time_minutes")
    if tt is None:
        errors.append(
            "travel_time_minutes must not be NULL — OSRM returned null for "
            "this pair, meaning no route exists; skip this edge"
        )
    else:
        try:
            tt_f = float(tt)
            if tt_f < 0.0:
                errors.append(
                    f"travel_time_minutes={tt_f} must be >= 0"
                )
        except (TypeError, ValueError):
            errors.append(f"travel_time_minutes={tt!r} must be numeric")

    # ── Self-edge ──────────────────────────────────────────────────────────
    a = record.get("poi_a_id")
    b = record.get("poi_b_id")
    if a is not None and b is not None and a == b:
        errors.append(
            f"poi_a_id == poi_b_id == {a!r}: self-edges are not allowed"
        )

    return ValidationResult(valid=len(errors) == 0, errors=errors, record=record)


# ── Trip validation ────────────────────────────────────────────────────────────

def validate_trip(record: dict[str, Any]) -> ValidationResult:
    """
    Validate a `trips` table record before write.

    Checks (§ 5.5):
      - total_budget >= 0
      - return_date >= departure_date
    """
    errors: list[str] = []

    # ── Budget ─────────────────────────────────────────────────────────────
    budget = record.get("total_budget")
    if budget is not None:
        try:
            b = float(budget)
            if b < 0:
                errors.append(f"total_budget={b} must be >= 0")
        except (TypeError, ValueError):
            errors.append(f"total_budget={budget!r} must be numeric")

    # ── Date ordering ──────────────────────────────────────────────────────
    dep = record.get("departure_date")
    ret = record.get("return_date")
    if dep is not None and ret is not None:
        # Accept date objects or YYYY-MM-DD strings
        try:
            dep_d = dep if isinstance(dep, date) else date.fromisoformat(str(dep))
            ret_d = ret if isinstance(ret, date) else date.fromisoformat(str(ret))
            if ret_d < dep_d:
                errors.append(
                    f"return_date={ret_d} is before departure_date={dep_d}"
                )
        except ValueError:
            errors.append(
                f"departure_date={dep!r} or return_date={ret!r} is not a valid ISO-8601 date"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors, record=record)


# ── Day number validation ──────────────────────────────────────────────────────

def validate_day_number(record: dict[str, Any]) -> ValidationResult:
    """
    Validate the `day_number` field of an `itinerary_days` record.

    Checks (§ 5.5):
      - day_number > 0
    """
    errors: list[str] = []
    day_num = record.get("day_number")

    if day_num is not None:
        try:
            d = int(day_num)
            if d <= 0:
                errors.append(f"day_number={d} must be > 0")
        except (TypeError, ValueError):
            errors.append(f"day_number={day_num!r} must be a positive integer")

    return ValidationResult(valid=len(errors) == 0, errors=errors, record=record)


# ── Batch filter helper ────────────────────────────────────────────────────────

def filter_valid(
    items: list[T],
    validator: Callable[[dict], ValidationResult],
    to_dict: Callable[[T], dict] | None = None,
    log: bool = True,
) -> list[T]:
    """
    Apply a validator to every item in a list, return only the valid ones.

    Args:
        items:     List of items (dataclass instances or dicts).
        validator: One of validate_attraction / validate_graph_edge / validate_trip.
        to_dict:   Optional callable to convert each item to a dict.
                   If None, items are assumed to already be dicts or have __dict__.
        log:       If True, print a warning for every rejected record.

    Returns:
        List containing only items that passed validation.
    """
    valid_items: list[T] = []
    rejected = 0

    for item in items:
        record_dict = (
            to_dict(item)
            if to_dict is not None
            else (item if isinstance(item, dict) else item.__dict__)
        )
        result = validator(record_dict)
        if result.valid:
            valid_items.append(item)
        else:
            rejected += 1
            if log:
                name = record_dict.get("name", record_dict.get("poi_a_id", "?"))
                print(
                    f"  [Validator] REJECTED '{name}': {'; '.join(result.errors)}"
                )

    if log and rejected:
        print(
            f"  [Validator] {rejected}/{len(items)} records rejected; "
            f"{len(valid_items)} passed."
        )

    return valid_items

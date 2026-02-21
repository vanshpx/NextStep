"""
modules/tool_usage/time_tool.py
---------------------------------
Arithmetic tool: performs time-related calculations (duration arithmetic, travel time).
Local computation — no external API required (architecture doc confirms arithmetic tool).

TODO (MISSING from architecture doc):
  - Time unit not specified (minutes assumed; configurable via config.TIME_UNIT).
  - Whether travel time uses real transit/road data (would need Google Maps API) or
    a simple distance/speed approximation. Currently implements speed approximation.
    Replace with Maps API call if real transit data is required.
"""

from __future__ import annotations
from datetime import datetime, time, timedelta
from typing import Optional
import config


# Default travel speed assumptions (TODO: MISSING — not specified in architecture doc)
_DEFAULT_SPEED_KM_PER_H = 30.0  # urban travel average (assumed)


class TimeTool:
    """
    Wraps time-arithmetic operations used by the Route Planner.
    Provides t_cur advancement and travel-time estimation.
    """

    def __init__(self, unit: str = config.TIME_UNIT, speed_kmh: float = _DEFAULT_SPEED_KM_PER_H):
        self.unit = unit if unit != "UNSPECIFIED" else "minutes"
        self.speed_kmh = speed_kmh

    def estimate_travel_time(self, distance_km: float) -> float:
        """
        Estimate travel time from a distance value.

        Args:
            distance_km: Distance in kilometres (output of DistanceTool).

        Returns:
            Travel time in self.unit (default: minutes).

        TODO: MISSING — actual travel mode and speed are unspecified.
              Replace with routing API call for road/transit accuracy.
        """
        hours = distance_km / self.speed_kmh
        minutes = hours * 60
        if self.unit == "seconds":
            return minutes * 60
        return minutes  # default: minutes

    @staticmethod
    def add_minutes(base_time: time, minutes: float) -> time:
        """
        Advance a time value by a number of minutes.

        Args:
            base_time: Current time (datetime.time).
            minutes:   Minutes to add.

        Returns:
            New time after addition.
            NOTE: Does NOT handle day overflow — date tracking is handled by Route Planner.
        """
        dt = datetime.combine(datetime.today(), base_time)
        dt += timedelta(minutes=minutes)
        return dt.time()

    @staticmethod
    def minutes_until(current: time, end: time) -> float:
        """
        Compute remaining minutes between current time and an end time.

        Args:
            current: t_cur (datetime.time).
            end:     end_time for the day.

        Returns:
            Remaining minutes as float. Returns 0.0 if end <= current.
        """
        c_dt = datetime.combine(datetime.today(), current)
        e_dt = datetime.combine(datetime.today(), end)
        delta = (e_dt - c_dt).total_seconds()
        return max(0.0, delta / 60.0)

    @staticmethod
    def is_within_window(current: time, window_start: str, window_end: str) -> bool:
        """
        Check if current time falls within an optimal visit window.

        Args:
            current:      t_cur.
            window_start: Window start as "HH:MM" string.
                          TODO: MISSING — window format not specified in doc.
            window_end:   Window end as "HH:MM" string.

        Returns:
            True if current is inside [window_start, window_end].
        """
        try:
            ws = datetime.strptime(window_start, "%H:%M").time()
            we = datetime.strptime(window_end, "%H:%M").time()
        except ValueError:
            # TODO: MISSING — handle other time formats if specified later
            return False
        return ws <= current <= we

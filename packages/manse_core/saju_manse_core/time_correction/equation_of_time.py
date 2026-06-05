"""Equation of time (균시차) — NOAA approximation, result in minutes."""

from __future__ import annotations

import math
from datetime import datetime


def equation_of_time_minutes(dt: datetime) -> float:
    """Minutes to add to mean solar time to obtain apparent (true) solar time."""
    day_of_year = dt.timetuple().tm_yday
    hour = dt.hour + dt.minute / 60 + dt.second / 3600
    gamma = 2 * math.pi / 365 * (day_of_year - 1 + (hour - 12) / 24)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )

"""Generate the solar-term table used by the runtime engine.

Self-contained: computes the Sun's apparent geocentric longitude with Meeus'
abridged algorithm (accuracy ~0.01°, i.e. well under a minute of time) and finds
each instant where it crosses a multiple of 15°. No network or ephemeris file is
required, so the output is fully reproducible.

Usage:
    python scripts/generate_solar_terms.py [start_year] [end_year]

A higher-precision regeneration via skyfield is possible (extra ``[astro]``) but
the Meeus result is more than sufficient for month-boundary determination.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "solar_terms"
    / "solar_terms_1900_2100.json"
)
VERSION = "meeus-1900_2100-v1"

# degree → (term name). 춘분 = 0°.
TERMS_BY_DEGREE: dict[int, str] = {
    315: "입춘", 330: "우수", 345: "경칩", 0: "춘분", 15: "청명", 30: "곡우",
    45: "입하", 60: "소만", 75: "망종", 90: "하지", 105: "소서", 120: "대서",
    135: "입추", 150: "처서", 165: "백로", 180: "추분", 195: "한로", 210: "상강",
    225: "입동", 240: "소설", 255: "대설", 270: "동지", 285: "소한", 300: "대한",
}


def julian_day(dt: datetime) -> float:
    """JD (float) for a UTC datetime."""
    y, m = dt.year, dt.month
    d = (
        dt.day
        + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    )
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (y + 4716))
        + int(30.6001 * (m + 1))
        + d
        + b
        - 1524.5
    )


def jd_to_datetime(jd: float) -> datetime:
    """Inverse of :func:`julian_day` → UTC datetime (second precision)."""
    jd += 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    day_int = int(day)
    frac = day - day_int
    seconds = round(frac * 86400)
    base = datetime(year, month, day_int, tzinfo=UTC)
    return base + timedelta(seconds=seconds)


def delta_t_seconds(year: float) -> float:
    """ΔT = TT - UT, Espenak & Meeus polynomials (covers 1900-2150)."""
    if 1900 <= year < 1920:
        t = year - 1900
        return -2.79 + 1.494119 * t - 0.0598939 * t**2 + 0.0061966 * t**3 - 0.000197 * t**4
    if 1920 <= year < 1941:
        t = year - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
    if 1941 <= year < 1961:
        t = year - 1950
        return 29.07 + 0.407 * t - t**2 / 233 + t**3 / 2547
    if 1961 <= year < 1986:
        t = year - 1975
        return 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
    if 1986 <= year < 2005:
        t = year - 2000
        return (
            63.86 + 0.3345 * t - 0.060374 * t**2 + 0.0017275 * t**3
            + 0.000651814 * t**4 + 0.00002373599 * t**5
        )
    if 2005 <= year < 2050:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t**2
    # 2050-2150
    return -20 + 32 * ((year - 1820) / 100) ** 2 - 0.5628 * (2150 - year)


def sun_apparent_longitude(jd_utc: float, year: float) -> float:
    """Apparent geocentric longitude of the Sun (degrees, 0-360)."""
    jde = jd_utc + delta_t_seconds(year) / 86400.0
    t = (jde - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t**2
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t**2
    m_rad = math.radians(m % 360)
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t**2) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000289 * math.sin(3 * m_rad)
    )
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    apparent = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega % 360))
    return apparent % 360


def _signed_delta(lon: float, target: float) -> float:
    return ((lon - target + 180) % 360) - 180


def find_crossing(jd_lo: float, jd_hi: float, target: int) -> float:
    """Bisect for the JD where the Sun's longitude equals *target* degrees."""
    for _ in range(60):
        mid = (jd_lo + jd_hi) / 2
        year = jd_to_datetime(mid).year
        f = _signed_delta(sun_apparent_longitude(mid, year), target)
        f_lo = _signed_delta(
            sun_apparent_longitude(jd_lo, jd_to_datetime(jd_lo).year), target
        )
        if (f_lo <= 0) == (f <= 0):
            jd_lo = mid
        else:
            jd_hi = mid
    return (jd_lo + jd_hi) / 2


def generate(start_year: int, end_year: int) -> list[dict]:
    step = 0.25  # days
    start = julian_day(datetime(start_year, 1, 1, tzinfo=UTC))
    end = julian_day(datetime(end_year, 12, 31, 23, tzinfo=UTC))

    terms: list[dict] = []
    jd = start
    prev_lon = sun_apparent_longitude(jd, jd_to_datetime(jd).year)
    jd += step
    while jd <= end:
        year = jd_to_datetime(jd).year
        lon = sun_apparent_longitude(jd, year)
        k_prev = int(prev_lon // 15)
        k_cur = int(lon // 15)
        if k_prev != k_cur:
            target = (k_cur * 15) % 360
            cross = find_crossing(jd - step, jd, target)
            dt = jd_to_datetime(cross)
            terms.append(
                {
                    "datetime_utc": dt.isoformat(),
                    "term": TERMS_BY_DEGREE[target],
                    "longitude": target,
                }
            )
        prev_lon = lon
        jd += step
    return terms


def main() -> None:
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 1900
    end_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2100
    terms = generate(start_year, end_year)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {"version": VERSION, "range": [start_year, end_year], "terms": terms},
            ensure_ascii=False,
            indent=0,
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(terms)} terms to {OUT_PATH}")


if __name__ == "__main__":
    main()

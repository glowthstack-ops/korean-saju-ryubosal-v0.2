"""Service-layer checks for chart_id identity and calculate() memoization.

Covers the contracts added in the service layer:
- chart_id is year-granular w.r.t. reference_date (same person + same options +
  same reference YEAR → same chart_id), so client-side calibration answers keyed
  by chart_id survive day-to-day changes of ``reference_date = today``.
- calculate() is memoized per FULL canonical input: the heavy pipeline runs only
  once for repeated identical requests, while different reference dates (even in
  the same year) are distinct cache entries because luck anchoring depends on
  the full date.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from saju_api.services import manse_service
from saju_api.services.manse_service import _chart_id, calculate
from saju_shared_types.birth_input import BirthInput


def _birth(reference_date: str | None = None) -> BirthInput:
    """Build a canonical test BirthInput (1980-11-22 09:08 Seoul male)."""
    return BirthInput(
        calendar_type="solar",
        birth_date=date(1980, 11, 22),
        birth_time="09:08",
        birth_place_name="서울",
        gender="male",
        reference_date=reference_date,
    )


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    """Isolate each test from the module-level in-process LRU cache."""
    with manse_service._cache_lock:
        manse_service._cache.clear()
    yield
    with manse_service._cache_lock:
        manse_service._cache.clear()


def test_chart_id_same_reference_year_is_stable() -> None:
    """Different reference dates within the same year → identical chart_id."""
    a = _chart_id(_birth("2026-06-10"))
    b = _chart_id(_birth("2026-06-11"))
    c = _chart_id(_birth("2026-12-31"))
    assert a == b == c


def test_chart_id_differs_across_reference_years() -> None:
    """Reference dates in different years → different chart_id."""
    a = _chart_id(_birth("2025-12-31"))
    b = _chart_id(_birth("2026-01-01"))
    assert a != b


def test_chart_id_differs_for_different_person_or_options() -> None:
    """Any chart-changing input (birth field / time option) changes chart_id."""
    base = _birth("2026-06-10")
    other_time = base.model_copy(update={"birth_time": "23:30"})
    other_gender = base.model_copy(update={"gender": "female"})
    no_tst = base.model_copy(deep=True)
    no_tst.time_options.apply_true_solar_time = False
    ids = {_chart_id(b) for b in (base, other_time, other_gender, no_tst)}
    assert len(ids) == 4


def test_calculate_same_input_runs_pipeline_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same input twice → identical chart_id and only one pipeline run."""
    calls = {"n": 0}
    real = manse_service._calculate

    def counting(birth: BirthInput) -> object:
        """Delegate to the real pipeline while counting invocations."""
        calls["n"] += 1
        return real(birth)

    monkeypatch.setattr(manse_service, "_calculate", counting)

    a = calculate(_birth("2026-06-10"))
    b = calculate(_birth("2026-06-10"))
    assert calls["n"] == 1
    assert a.chart_id == b.chart_id
    assert a.model_dump_json() == b.model_dump_json()


def test_calculate_cache_keys_on_full_reference_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same reference YEAR but different dates share chart_id, not cache entry."""
    calls = {"n": 0}
    real = manse_service._calculate

    def counting(birth: BirthInput) -> object:
        """Delegate to the real pipeline while counting invocations."""
        calls["n"] += 1
        return real(birth)

    monkeypatch.setattr(manse_service, "_calculate", counting)

    a = calculate(_birth("2026-06-10"))
    b = calculate(_birth("2026-06-11"))
    assert calls["n"] == 2  # full reference_date is part of the cache key
    assert a.chart_id == b.chart_id  # but chart identity is year-granular


def test_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The LRU evicts oldest entries and never grows beyond _CACHE_MAXSIZE."""
    monkeypatch.setattr(manse_service, "_CACHE_MAXSIZE", 3)
    for year in (2020, 2021, 2022, 2023, 2024):
        calculate(_birth(f"{year}-06-15"))
    with manse_service._cache_lock:
        assert len(manse_service._cache) == 3

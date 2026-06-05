"""Golden snapshot regression across regions / DST / 자시경계 / 윤달.

Each fixture in data/test_fixtures/manse/golden/ locks the engine's core output
(pillars + tz behavior + headline analysis) and is checked for determinism and
required reproducibility fields.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "test_fixtures" / "manse" / "golden"
_FIXTURES = sorted(_GOLDEN.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _FIXTURES, ids=[p.stem for p in _FIXTURES])
def test_golden_core_locked(path: Path) -> None:
    fx = _load(path)
    r = calculate(BirthInput(**fx["input"]))
    exp = fx["expected"]
    assert r.pillars is not None and r.time_correction is not None
    assert r.force_analysis is not None and r.geokguk is not None
    p, tc = r.pillars, r.time_correction

    assert p.year.ganji == exp["year_pillar"]
    assert p.month.ganji == exp["month_pillar"]
    assert p.day.ganji == exp["day_pillar"]
    assert (p.hour.ganji if p.hour else None) == exp["hour_pillar"]
    assert p.day_master == exp["day_master"]
    # tz / DST behavior is externally verifiable, not just a snapshot.
    assert tc.timezone_offset_minutes == exp["timezone_offset_minutes"]
    assert tc.daylight_saving_applied == exp["daylight_saving_applied"]
    assert tc.local_time_status == exp["local_time_status"]
    assert (
        tc.hour_pillar_changed_by_true_solar_time
        == exp["hour_pillar_changed_by_true_solar_time"]
    )
    lunar = tc.lunar_converted_solar_date.isoformat() if tc.lunar_converted_solar_date else None
    assert lunar == exp["lunar_converted_solar_date"]
    assert r.force_analysis.strength.band == exp["strength_band"]
    assert r.geokguk.main_structure == exp["geokguk_main_structure"]


@pytest.mark.parametrize("path", _FIXTURES, ids=[p.stem for p in _FIXTURES])
def test_golden_deterministic_and_versioned(path: Path) -> None:
    fx = _load(path)
    a = calculate(BirthInput(**fx["input"]))
    b = calculate(BirthInput(**fx["input"]))
    assert a.model_dump_json() == b.model_dump_json()  # 동일 입력 → 동일 JSON
    assert a.force_analysis is not None
    # 재현성 필드(버전·trace) 존재.
    assert a.metadata.engine_version and a.metadata.solar_terms_version
    assert a.metadata.tzdata_version
    assert a.trace.get("absolute_instant_utc")
    assert a.force_analysis.five_elements.calculation_trace


def test_dst_cases_actually_apply_dst() -> None:
    # 회귀 가드: DST를 무시하면 실패해야 한다.
    for name in ("us_newyork_dst", "uk_london_bst", "australia_dst"):
        fx = _load(_GOLDEN / f"{name}.json")
        r = calculate(BirthInput(**fx["input"]))
        assert r.time_correction is not None
        assert r.time_correction.daylight_saving_applied is True


def test_cross_process_hashseed_determinism() -> None:
    # 서로 다른 PYTHONHASHSEED에서도 동일 JSON이어야 한다(set→list 순서 누수 가드).
    code = (
        "from saju_api.services.manse_service import calculate;"
        "from saju_shared_types.birth_input import BirthInput;"
        "print(calculate(BirthInput(calendar_type='solar',birth_date='1980-11-22',"
        "birth_time='09:08',birth_place_name='서울',gender='male')).model_dump_json())"
    )

    def run(seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
        )
        return out.stdout

    assert run("1") == run("2")


def test_zi_hour_boundary_rolls_day_pillar() -> None:
    # 23:30 출생(23:00 일자경계) → 일주가 다음날로 넘어간다(己亥→庚子).
    fx = _load(_GOLDEN / "zi_hour_boundary.json")
    r = calculate(BirthInput(**fx["input"]))
    assert r.pillars is not None
    assert r.pillars.day.ganji == "庚子"

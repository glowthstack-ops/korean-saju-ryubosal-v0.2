"""사주 비교 사례집 85사례·180명식 — 명식(4주) 재현 회귀 (C0 완료 기준, 2026-10-08 데굴님 승인).

`CASEBOOK_CALIBRATION_PLAN.md` C0 는 "180명식 4주 일치" 회귀 테스트를 완료 기준으로 적었으나 파일이
없었다(2026-10-08 정정). 이 테스트는 날짜·시각이 주어진 명식에 대해 만세력 코어가 문서 명식을 그대로
재현하는지 검증한다. 재현 규칙은 `scripts/casebook_replay.py` `_calc_matching` 과 같다 — 시간 보정
변형(default → no_dst → no_dst_no_lon → no_tst) × 시각 이동(0, ±1h, ±2h) 중 하나라도 일치하면 재현.
1954~1961 출생은 엔진(UTC+8:30·서머타임)과 화면 프로그램(−30분)이 달라 변형이 필요한 것이
알려진 사실이다.

날짜가 없는 명식(23건)은 역법 탐색 대상이라 여기서는 다루지 않는다(replay 가 구조 전용으로 처리).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput, TimeCalculationOptions

_CASES = Path(__file__).resolve().parents[1] / "fixtures" / "comparison_casebook" / "cases.jsonl"

#: casebook_replay.py `_VARIANTS` 와 동일 순서(변형 이름, TimeCalculationOptions kwargs).
_VARIANTS: list[tuple[str, dict[str, Any]]] = [
    ("default", {}),
    ("no_dst", {"apply_daylight_saving": False}),
    ("no_dst_no_lon", {"apply_daylight_saving": False, "apply_longitude_correction": False}),
    ("no_tst", {"apply_true_solar_time": False}),
]
_SHIFTS = (0, -1, 1, -2, 2)
_GENDER = {"M": "male", "F": "female", "U": "male"}


def _load_cases() -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in _CASES.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _shift(t: str, hours: int) -> tuple[str, int]:
    """시각을 시간 단위로 이동 — (새 시각, 날짜 이동일수)."""
    h, m = map(int, t.split(":"))
    h += hours
    dd = 0
    while h < 0:
        h += 24
        dd -= 1
    while h >= 24:
        h -= 24
        dd += 1
    return f"{h:02d}:{m:02d}", dd


def _ganji4(result: Any) -> list[str]:
    p = result.pillars
    return [p.year.ganji, p.month.ganji, p.day.ganji, p.hour.ganji if p.hour else "--"]


CASES = _load_cases()
DATED: list[tuple[str, dict[str, Any]]] = [
    (c["case_id"], s) for c in CASES for s in c["subjects"] if s.get("date") and s.get("time")
]


def test_fixture_shape() -> None:
    """85사례·180명식, 날짜·시각 보유 157명식(2026-10-07 큐레이션 수치)."""
    subjects = [s for c in CASES for s in c["subjects"]]
    assert len(CASES) == 85
    assert len(subjects) == 180
    assert len(DATED) == 157
    assert all(len(s["pillars"]) == 4 for s in subjects)


@pytest.mark.parametrize(
    "case_id, subj", DATED, ids=[f"{cid}/{s['key']}" for cid, s in DATED],
)
def test_pillars_reproduced(case_id: str, subj: dict[str, Any]) -> None:
    """문서 명식 4주가 시간 보정 변형·시각 이동 중 하나로 재현된다."""
    d, t = str(subj["date"]), str(subj["time"])
    gender = _GENDER[str(subj["gender"])]
    expected: list[str] = list(subj["pillars"])
    tried: list[str] = []
    for name, var in _VARIANTS:
        for hshift in _SHIFTS:
            t2, dd = _shift(t, hshift)
            d2 = (date.fromisoformat(d) + timedelta(days=dd)).isoformat()
            kw: dict[str, Any] = {}
            if var:
                kw["time_options"] = TimeCalculationOptions(**var)
            result = calculate(BirthInput(
                calendar_type="solar", birth_date=d2, birth_time=t2,
                birth_place_name="서울", gender=gender, **kw,
            ))
            got = _ganji4(result)
            if got == expected:
                return
            tried.append(f"{name}{hshift:+d}h={''.join(got)}")
    pytest.fail(
        f"{case_id}/{subj['key']} {d} {t}: 문서 {''.join(expected)} 재현 실패 — "
        + ", ".join(tried[:6])
    )

"""시두 경계 민감도(P5, 2026-07-13 데굴님 감수) — 구조화 필드·대체 시주."""

from __future__ import annotations

import pytest

from saju_api.services import manse_service
from saju_shared_types.birth_input import BirthInput


def _calc(birth_time: str, *, eot: bool = True):
    birth = BirthInput.model_validate({
        "birth_date": "2015-03-01",
        "birth_time": birth_time,
        "birth_place_name": "서울",
        "gender": "male",
        "time_options": {"apply_equation_of_time": eot},
    })
    return manse_service.calculate(birth)


def test_boundary_sensitive_with_alternative_pillar() -> None:
    # 감수 기준 사례: 균시차 미적용 진태양시 03:01:54 = 寅시 시작 +114초.
    # 출생기록 2~3분 오차로 丑시(己丑)가 될 수 있어 대체 시주를 제공해야 한다.
    r = _calc("03:34", eot=False)
    tc = r.time_correction
    assert r.pillars.hour.ganji == "庚寅"
    assert tc.hour_boundary_distance_seconds == pytest.approx(114.0, abs=2.0)
    assert tc.boundary_sensitive is True
    assert tc.alternative_hour_pillar == "己丑"


def test_boundary_not_sensitive_when_far() -> None:
    # 균시차 적용판(02:48:56)은 丑시 경계에서 ±180초 밖 — 플래그·대체 시주 없음.
    tc = _calc("03:34", eot=True).time_correction
    assert tc.boundary_sensitive is False
    assert tc.alternative_hour_pillar is None
    assert abs(tc.hour_boundary_distance_seconds) > 180


def test_boundary_fields_absent_when_time_unknown() -> None:
    birth = BirthInput.model_validate({
        "birth_date": "2015-03-01",
        "birth_time": None,
        "birth_time_unknown": True,
        "birth_place_name": "서울",
        "gender": "male",
    })
    tc = manse_service.calculate(birth).time_correction
    assert tc.hour_boundary_distance_seconds is None
    assert tc.boundary_sensitive is False
    assert tc.alternative_hour_pillar is None

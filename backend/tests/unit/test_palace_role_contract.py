"""궁성 자리역할(_PALACE_ROLE) 계약 — C7 D6 (2026-10-08 데굴님 승인).

서술 보조 전용 매핑(점수 입력 아님). 월주 천간=부친·지지=모친, 일주 지지=배우자, 시주=자녀가
명식 구조 블록 `palace_role` 로 그대로 전달되는지만 고정한다(통설 궁위, docs/09 M04/M05 비고).
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import _PALACE_ROLE, build_chart_interpretation
from saju_shared_types.birth_input import BirthInput


def test_palace_role_mapping_contract() -> None:
    assert set(_PALACE_ROLE) == {"year", "month", "day", "hour"}
    assert "부친" in _PALACE_ROLE["month"] and "모친" in _PALACE_ROLE["month"]
    assert "배우자" in _PALACE_ROLE["day"]
    assert "조부" in _PALACE_ROLE["year"] and "조모" in _PALACE_ROLE["year"]
    assert "아들" in _PALACE_ROLE["hour"] and "딸" in _PALACE_ROLE["hour"]


def test_palace_role_exposed_in_structure_block() -> None:
    r = calculate(BirthInput(calendar_type="solar", birth_date="1985-10-29", birth_time="22:20",
                             birth_place_name="서울", gender="female"))
    block = build_chart_interpretation(r)
    roles = {d.palace: d.palace_role for d in block.pillar_details}
    assert roles == _PALACE_ROLE

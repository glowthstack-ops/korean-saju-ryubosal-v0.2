"""운 십성 × 도메인 교차 작용 줄 회귀(2026-10-01, 데굴님 승인).

실로그: '내 10월 금전 운세는 어때?'(己亥 일주, 戊戌월 = 겁재·용신)에서 겁재가 재성을 극하는
쟁재 작용이
용신 톤("결단과 추진")에 묻혔다. 길흉=용기신 원칙은 유지하고 십성의 작용 방향을 별도 줄로 준다.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from saju_api.services import chat_service
from saju_engines.chart_interpretation import _group_relation, domain_interaction_note
from saju_shared_types.birth_input import BirthInput

_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}  # 己 일간 예시 역할맵


@pytest.mark.parametrize(
    "incoming, base, expected",
    [
        ("peer", "wealth", "controls"),       # 비겁탈재
        ("output", "wealth", "generates"),    # 식상생재
        ("resource", "wealth", "controlled_by"),  # 재극인(재성이 인성을 극)
        ("wealth", "wealth", "same"),
        ("officer", "wealth", "generated_by"),  # 재생관(설기)
        ("output", "officer", "controls"),    # 상관견관
        ("resource", "output", "controls"),   # 인극식
    ],
)
def test_group_relation_cycle(incoming: str, base: str, expected: str) -> None:
    assert _group_relation(incoming, base) == expected


def test_geomjae_month_on_wealth_question_mentions_jaengjae_with_favorable_tone() -> None:
    """己일간 × 戊戌(겁재·용신) × 재물 → '비겁탈재·쟁재' 작용 + 용신 톤."""
    line = domain_interaction_note("己", "戊戌", "wealth", _FAV)
    assert "겁재(비겁) → 재성 극(克, 비겁탈재·쟁재)" in line
    assert "용·희신" in line  # 톤은 결과 방향만 바꾼다


def test_gisin_tone_and_no_domain() -> None:
    # 甲=정관(木 기신) × 관살 기준 → same
    line = domain_interaction_note("己", "甲寅", "career", _FAV)
    assert "동류" in line and "기·구신" in line
    assert domain_interaction_note("己", "戊戌", None, _FAV) == ""
    assert domain_interaction_note("己", "戊戌", "general", _FAV) == ""


def test_branch_group_adds_second_clause_when_different() -> None:
    """丙午 × 己일간(丙 정인·午 편인 — 같은 군) → 1절 / 甲申(정관·상관 — 다른 군) → 2절."""
    one = domain_interaction_note("己", "丙午", "wealth", _FAV)
    assert one.count(" / ") == 0
    two = domain_interaction_note("己", "甲申", "wealth", _FAV)
    assert two.count(" / ") == 1


def test_payload_carries_interaction_line_for_wealth_question() -> None:
    b = BirthInput(
        birth_date=date(1980, 11, 22), birth_time=time(9, 8), birth_place_name="서울",
        gender="male",
    )
    res = chat_service.chat(b, "내 10월 금전 운세는 어때?", date(2026, 10, 1), dry_run=True)
    text = res.prompt_preview or ""
    assert "  교차 작용: " in text and "비겁탈재·쟁재" in text
    assert "십성의 작용 방향" in text  # _MEANING_INSTRUCTION 보강

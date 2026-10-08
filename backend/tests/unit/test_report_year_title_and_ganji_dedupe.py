"""한해풀이 제목 연도 표기(_year_title)·간지 독음 중복 병기 정리(_dedupe_ganji_ko) — 2026-10-08.

데굴님 요청: RPT_YEAR 섹션 제목의 '올해…'는 선택 연도로 표기하고, Y-12 본문에서 LLM이
'癸丑(계축) (계축)'처럼 독음을 겹쳐 쓴 병기는 결정론적으로 한 번으로 정리한다.
"""

from __future__ import annotations

import pytest

from saju_api.services.report_service import _dedupe_ganji_ko, _year_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("올해 한눈에", "2027년 한눈에"),
        ("올해가 속한 대운 맥락", "2027년이 속한 대운 맥락"),
        ("올해의 행동 전략", "2027년의 행동 전략"),
        ("올해의 방위 활용과 삼재 흐름", "2027년의 방위 활용과 삼재 흐름"),
        ("올해는 어떤 해", "2027년은 어떤 해"),
        ("재물 흐름", "재물 흐름"),  # '올해' 없으면 원문 유지
    ],
)
def test_year_title_replaces_this_year_with_selected_year(title: str, expected: str) -> None:
    """'올해'→'{y}년', 조사('가'→'이', '는'→'은')까지 자연스럽게 바뀐다."""
    assert _year_title(title, 2027) == expected


def test_dedupe_ganji_ko_collapses_repeated_reading() -> None:
    """'癸丑(계축) (계축)'·'壬寅(임인)(임인)' → 한 번 병기. 정상 병기·간지 자체는 불변."""
    text = (
        "- 01월: 癸丑(계축) (계축)\n- 02월: 壬寅(임인)(임인)\n"
        "- 03월: 癸卯(계묘)\n| 2월 | 壬寅(임인) | 壬 정재 |"
    )
    out = _dedupe_ganji_ko(text)
    assert out == (
        "- 01월: 癸丑(계축)\n- 02월: 壬寅(임인)\n- 03월: 癸卯(계묘)\n| 2월 | 壬寅(임인) | 壬 정재 |"
    )


def test_dedupe_ganji_ko_keeps_different_readings() -> None:
    """뒤따르는 괄호가 같은 독음이 아니면 건드리지 않는다(예: 설명 괄호)."""
    text = "癸丑(계축) (물의 기운)"
    assert _dedupe_ganji_ko(text) == text

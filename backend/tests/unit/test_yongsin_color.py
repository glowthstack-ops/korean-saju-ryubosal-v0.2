"""오행 보완 색 첨언 — 색 질문 감지·지목 색 사전 조회·역할별 후보표 회귀(2026-10-01).

실로그: 엔진은 용신 火·희신 金·기신 木을 줬으나 색 후보표가 없어 LLM이 상생 연쇄로 기신 색
(연두·초록)을
추천했고, 희신 金 색은 한 번도 제시하지 않았다(용신 일변도). 엔진이 역할별 후보를 모두 제시한다.
"""

from __future__ import annotations

import pytest

from saju_engines.yongsin_color import (
    YONGSIN_COLOR_INSTRUCTION,
    build_yongsin_color_note,
    color_element_of,
    detect_asked_colors,
    format_yongsin_color_lines,
    is_color_question,
)

_FAV = {"火": "용신", "金": "희신", "木": "기신", "水": "구신", "土": "한신"}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("이 사주의 학업운을 향상시킬 수 있는 색깔은 뭐야?", True),
        ("커텐으로 할건데 붉은색은 좀 그래. 다른색을 추천해줘.", True),
        ("니가 연두색이나 초록색계열 커튼을 추천해줬잖아", True),
        ("올해 재물운 어때?", False),
        ("결혼식 날짜 추천해줘", False),
    ],
)
def test_is_color_question(text: str, expected: bool) -> None:
    assert is_color_question(text) is expected


def test_detect_asked_colors_longest_first_and_order() -> None:
    asked = detect_asked_colors("니가 연두색이나 초록색계열 커튼을 추천해줬잖아")
    assert asked == ["연두색", "초록색"]
    # 보류 큐 어휘도 지목으로 잡는다
    assert detect_asked_colors("보라색 커튼은 어때?") == ["보라색"]
    assert detect_asked_colors("올해 재물운 어때?") == []


def test_color_element_mapping_and_review_queue() -> None:
    assert color_element_of("초록") == "木" and color_element_of("분홍") == "火"
    assert color_element_of("보라색") is None  # 통설이 갈려 사전 미등재(검수 큐)
    assert color_element_of("을") is None  # 1글자 오탐 방지


def test_note_lists_every_role_and_marks_asked_colors() -> None:
    note = build_yongsin_color_note(_FAV, ["연두색", "보라색"])
    assert note is not None
    roles = [e.role for e in note.entries]
    assert roles == ["용신", "희신", "한신", "기신", "구신"]
    hee = next(e for e in note.entries if e.role == "희신")
    assert hee.element == "金" and "흰색" in hee.colors  # 희신 색이 반드시 표에 있다
    assert note.asked_entries[0].element == "木" and note.asked_entries[0].role == "기신"
    assert note.unmapped_colors == ["보라색"]
    lines = format_yongsin_color_lines(note)
    assert any("희신 金" in ln and "보완 색·보조" in ln for ln in lines)
    assert any("'보라색' = 오행 배정 보류" in ln for ln in lines)
    assert any("기신 木" in ln and "삼가" in ln and "피" not in ln for ln in lines)  # 완화 어휘


def test_note_none_without_favorability() -> None:
    assert build_yongsin_color_note({}, ["초록"]) is None
    assert format_yongsin_color_lines(None) == []


def test_instruction_forbids_chain_and_yongsin_only() -> None:
    assert "상생 연쇄" in YONGSIN_COLOR_INSTRUCTION
    # 용신 일변도 금지(2026-10-01 데굴님 지적)
    assert "희신 색이 1차 대안" in YONGSIN_COLOR_INSTRUCTION
    assert "인과" in YONGSIN_COLOR_INSTRUCTION  # 효과 단정 금지

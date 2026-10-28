"""오행 보완 음식 첨언 — 음식 질문 감지·지목 음식 조회·역할별 후보표·파서 승격 회귀(2026-10-28).

실로그: "오늘 점심은 뭘 먹는게 좋을까"가 도메인어 없음 → Q1 총운 폴백 → '오늘' 하나로 일운 5영역
총운이 되어 점심을 한 글자도 답하지 않았다. 색(2026-10-01)과 같은 모델로 음식 층을 두고, 룰이 Q1로
폴백한 경우에만 Q10(오행 생활화)으로 승격한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.query_parser import parse_message
from saju_engines.yongsin_food import (
    YONGSIN_FOOD_CLOSING_DIRECTIVE,
    YONGSIN_FOOD_INSTRUCTION,
    build_yongsin_food_note,
    detect_asked_foods,
    food_element_of,
    format_yongsin_food_lines,
    is_food_question,
)
from saju_shared_types.intent import Domain, QueryType

_FAV = {"火": "용신", "金": "희신", "木": "기신", "水": "구신", "土": "한신"}
_TODAY = date(2026, 10, 28)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("오늘 점심은 뭘 먹는게 좋을까", True),
        ("내 사주를 바탕으로 나에게 맞는 음식과 안 맞는 음식", True),
        ("저녁 메뉴 추천해줘", True),
        ("뭐 먹을까", True),
        # 제외 — 일정·복약·생계 관용구·비유
        ("점심 약속 잡아도 될까", False),
        ("약 먹어도 돼?", False),
        ("내 사주로 뭘 해먹고 살아야 할까", False),
        ("나이 먹으면 좋아질까", False),
        ("올해 재물운 어때?", False),
        ("커튼 색 추천해줘", False),
    ],
)
def test_is_food_question(text: str, expected: bool) -> None:
    assert is_food_question(text) is expected


def test_detect_asked_foods_longest_first_and_review_queue() -> None:
    assert detect_asked_foods("시금치나물이랑 토마토 중에 뭐 먹을까") == ["시금치나물", "토마토"]
    assert detect_asked_foods("김치찌개 어때") == ["김치찌개"]  # 복합 요리 — 보류 큐
    assert detect_asked_foods("올해 재물운 어때?") == []


def test_food_element_mapping_and_review_queue() -> None:
    assert food_element_of("토마토") == "火" and food_element_of("미역국") == "水"
    assert food_element_of("김치찌개") is None  # 복합 요리 — 임의 배정 금지
    assert food_element_of("무") is None  # 1글자 오탐 방지(표에는 남고 지목 감지만 제외)


def test_note_lists_every_role_and_marks_asked_foods() -> None:
    note = build_yongsin_food_note(_FAV, ["시금치", "김치찌개"])
    assert note is not None
    assert [e.role for e in note.entries] == ["용신", "희신", "한신", "기신", "구신"]
    hee = next(e for e in note.entries if e.role == "희신")
    assert hee.element == "金" and "두부" in hee.foods and hee.menus  # 희신 후보가 반드시 표에 있다
    assert note.asked_entries[0].element == "木" and note.asked_entries[0].role == "기신"
    assert note.unmapped_foods == ["김치찌개"]
    lines = format_yongsin_food_lines(note)
    assert lines[1].startswith("[오행 보완 음식")
    assert any("'김치찌개' = 오행 배정 보류" in line for line in lines)
    assert any("몰아 먹지는 말기" in line for line in lines)  # 기신 완화 톤


def test_note_none_without_favorability() -> None:
    assert build_yongsin_food_note({}) is None
    assert format_yongsin_food_lines(None) == []


def test_instructions_fix_answer_shape_and_forbid_chain() -> None:
    assert "상생 연쇄" in YONGSIN_FOOD_INSTRUCTION
    assert "희신 음식이 1차 대안" in YONGSIN_FOOD_INSTRUCTION
    assert "영양·의료 조언" in YONGSIN_FOOD_INSTRUCTION
    assert "메뉴 추천" in YONGSIN_FOOD_CLOSING_DIRECTIVE
    assert "영역별 총운" in YONGSIN_FOOD_CLOSING_DIRECTIVE


# ── 파서 승격 규칙 ────────────────────────────────────────────────


def test_parser_promotes_q1_fallback_to_remedy_and_keeps_today() -> None:
    intent = parse_message("오늘 점심은 뭘 먹는게 좋을까", _TODAY).intents[0]
    assert intent.food_question is True
    assert intent.query_type is QueryType.REMEDY
    assert intent.domain is Domain.GENERAL
    assert intent.time_range is not None and intent.time_range.start == _TODAY.isoformat()


def test_parser_keeps_rule_confirmed_types() -> None:
    # '내 사주' 표지 → Q8 명식 구조는 그대로(블록만 더함). '안 맞'만으로 관계 도메인이 되지 않는다.
    intent = parse_message("내 사주에 맞는 음식과 안 맞는 음식", _TODAY).intents[0]
    assert intent.food_question is True
    assert intent.query_type is QueryType.CHART_ANALYSIS
    assert intent.domain is Domain.GENERAL
    # 관계어('연애')가 따로 있으면 관계 도메인 유지
    intent2 = parse_message("연애에 잘 맞는 음식이 있을까", _TODAY).intents[0]
    assert intent2.food_question is True and intent2.domain is Domain.RELATIONSHIP


def test_parser_non_food_questions_unchanged() -> None:
    i1 = parse_message("오늘 운세 봐줘", _TODAY).intents[0]
    assert i1.food_question is False and i1.query_type is QueryType.FORTUNE_OVERVIEW
    i2 = parse_message("점심 약속 잡아도 될까", _TODAY).intents[0]
    assert i2.food_question is False
    i3 = parse_message("올해 재물운 어때?", _TODAY).intents[0]
    assert i3.food_question is False and i3.query_type is QueryType.DOMAIN_ANALYSIS
    # 색 질문 층 비회귀
    i4 = parse_message("커튼 색 추천해줘", _TODAY).intents[0]
    assert i4.color_question is True and i4.food_question is False

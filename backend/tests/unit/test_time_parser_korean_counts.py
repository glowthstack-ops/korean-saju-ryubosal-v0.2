"""한글 수사 기간 — '앞으로 두 달 안에'가 숫자 기간과 같은 창으로 (2026-10-13 데굴님 지시).

실로그: '앞으로 두 달 안에 누가 취업 제안을 해올까?'가 기간 미파싱 → 12개월 지평으로 새서 관계 대상
후보가 2027년 2·5월로 나왔다('2달안에'는 2026-10~11로 정상). 기간 표지가 붙은 경우만 숫자로
바꿔 기존 숫자 규칙을 그대로 쓰고, 빈도·관용 표현은 바꾸지 않는다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.time_parser import normalize_korean_counts, parse_time_with_constraints

_TODAY = date(2026, 10, 13)


def _window(text: str):
    tr, _scope, _items = parse_time_with_constraints(text, _TODAY, current_month_label="2026-10")
    return (tr.start, tr.end, tr.end_offset_days) if tr else None


@pytest.mark.parametrize(
    ("korean", "digits"),
    [
        ("앞으로 두 달 안에 누가 제안을 해올까?", "앞으로 2달 안에 누가 제안을 해올까?"),
        ("세 달 이내에 이직할까", "3달 이내에 이직할까"),
        ("석 달 후에 이사", "3달 후에 이사"),
        ("지난 여섯 달 동안 왜 안됐을까", "지난 6달 동안 왜 안됐을까"),
        ("삼 개월 안에", "3개월 안에"),
        ("일 년 뒤", "1년 뒤"),
        ("열두 달 안에", "12달 안에"),
        ("향후 다섯 달", "향후 5달"),
    ],
)
def test_korean_count_matches_digit_window(korean, digits):
    """한글 수사 기간은 같은 뜻의 숫자 기간과 같은 창이 된다."""
    assert normalize_korean_counts(korean) == digits
    assert _window(korean) == _window(digits) and _window(korean) is not None


@pytest.mark.parametrize(
    "text",
    [
        "한 달에 한 번 운동하면 좋을까", "이 년은 별로", "올 한 해 운세", "세 달이 지나도 그대로야",
        "앞으로 한달음에 달려갈까",  # 합성어 — 뒤에 한글이 바로 이어지면 기간이 아니다(2026-10-14)
    ],
)
def test_non_period_phrases_unchanged(text):
    """기간 표지가 없는 빈도·관용 표현은 바꾸지 않는다."""
    assert normalize_korean_counts(text) == text


def test_two_month_window_for_original_question():
    """원 실로그 문장 — 현재 절기월부터 두 달(2026-10~2026-11)."""
    assert _window("앞으로 두 달 안에 누가 취업 제안을 해올까?") == ("2026-10", "2026-11", None)

"""특정일 질문 상세화 회귀 (2026-07-22 테스터 신고 — '9/30 이사 주의점' 두루뭉술 답변).

결함 체인: ①단일 날짜(start==end)가 일별 일운 surface에서 제외돼 당일 간지·길흉이
입력에 없음 → LLM이 월·연 후보로 기간 서술 + 임의 간지 서술 ②시제 정정 발화
('오늘은 7월 22일이고 … 미래의 일이야')의 '7월 22일'이 분석 시점으로 채택돼 앵커 이탈
③'이미 계약도 끝냈고'(축약 과거형)가 명시 미래 창(9/30) 후속을 회고 모드로 뒤집어
과거형 서술("풀리는 날이었어요") 발생.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import _is_single_day, _question_time_direction
from saju_engines.time_parser import parse_time_with_constraints
from saju_shared_types.intent import (
    Domain,
    IntentJson,
    QueryType,
    TimeRange,
    TimeScope,
)

_TODAY = date(2026, 7, 22)


def _intent(start: str, end: str, gran: str = "day") -> IntentJson:
    return IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.RELOCATION,
        time_range=TimeRange(type="absolute", start=start, end=end, granularity=gran),
        time_scope=TimeScope.DATE_LEVEL,
    )


# ── ① 단일 날짜 판정 ──────────────────────────────────────────

def test_single_day_detected() -> None:
    assert _is_single_day(_intent("2026-09-30", "2026-09-30"))


def test_day_range_not_single() -> None:
    assert not _is_single_day(_intent("2026-09-28", "2026-10-02"))


def test_month_granularity_not_single() -> None:
    assert not _is_single_day(_intent("2026-09-01", "2026-09-30", gran="month"))


# ── ② 현재 날짜 진술의 시점 미채택 ───────────────────────────

def test_today_statement_not_target() -> None:
    tr, scope, _ = parse_time_with_constraints(
        "오늘은 7월 22일이고 이사는 아직 진행이 안된 미래의 일이야.. "
        "미래의 주의점을 물어보는거야",
        _TODAY,
    )
    assert tr is None  # 시점 미확정 → 대화 계층이 직전 창(9/30)을 승계한다
    assert scope is TimeScope.TIMELESS


def test_plain_today_request_still_parses() -> None:
    tr, _, _ = parse_time_with_constraints("오늘 운세 봐줘", _TODAY)
    assert tr is not None and tr.start == "2026-07-22"


def test_now_month_statement_keeps_other_target() -> None:
    # '지금은 7월인데' 진술은 제거되고 '12월' 목표는 살아남는다.
    tr, _, _ = parse_time_with_constraints("지금은 7월인데 12월에 이사해도 될까", _TODAY)
    assert tr is not None and tr.start == "2026-12"


# ── ③ 명시 미래 창의 회고 반전 방지 ──────────────────────────

def test_future_window_with_completed_facts_not_retro() -> None:
    q = (
        "아니 ㅠㅠ 9월 30일날 딱 이사를 간다니까??? 이미 계약도 끝냈고 인테리어와 이사, "
        "잔금만 남았는데 그때까지 주의할 점을 얘기해달라고.."
    )
    assert _question_time_direction(q, _intent("2026-09-30", "2026-09-30"), None, _TODAY) is False


def test_past_window_retro_preserved() -> None:
    i = _intent("2025-08-01", "2025-08-31", gran="month")
    assert _question_time_direction("작년 8월에 왜 힘들었을까", i, None, _TODAY) is True


# ── 절기 경계 — 다른 절기월 후보 제거·앵커 주입 (2026-07-22 재발 신고) ──

def test_single_day_before_jeolgi_prunes_other_month_candidates() -> None:
    """7/4(소서 전=甲午월) 질문 입력에서 乙未월(2026-07) 월 후보가 제거되고 앵커가 붙는다."""
    from saju_api.services import chat_service
    from saju_shared_types.birth_input import BirthInput

    me = BirthInput(
        calendar_type="solar", birth_date="1981-01-29", birth_time="13:05",
        birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(
        me, "내가 7월 4일에 서울 중구로 이사했어. 잘한걸까?",
        date(2026, 7, 22), True, subject_label="데굴님",
    )
    p = res.prompt_preview or ""
    assert "절기월은 甲午월(라벨 2026-06)" in p  # 특정일 지시문에 절기월 앵커
    assert not any("@ 2026-07(" in line for line in p.splitlines())  # 乙未 월 후보 제거


def test_single_day_inside_month_no_anchor() -> None:
    """절기월과 양력 달이 일치하는 날(7/15=乙未월)은 특정일 지시문에 앵커를 붙이지 않는다."""
    from saju_api.services import chat_service
    from saju_shared_types.birth_input import BirthInput

    me = BirthInput(
        calendar_type="solar", birth_date="1981-01-29", birth_time="13:05",
        birth_place_name="서울", gender="female",
    )
    res = chat_service.chat(
        me, "7월 15일에 계약해도 될까?", date(2026, 7, 8), True, subject_label="데굴님",
    )
    p = res.prompt_preview or ""
    assert "특정일 질문" in p
    assert "양력 7월이지만 절기 경계상" not in p  # 어긋나는 날에만 붙는 앵커

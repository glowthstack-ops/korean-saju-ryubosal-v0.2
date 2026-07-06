"""기간 없이 '달/날짜' 입도만 물은 질문의 라우팅 (실로그 회귀, 2026-07-03 데굴님 지적).

버그: '연애를 시작하는 달은 언제야?'가 기간 미지정이라 vague_future(10년 연 단위
digest)로 빠져 연 나열로 오답 + 만남 디렉티브의 '연·반기·계절 제시'가 월 요청과 충돌.
수정: 입도 명시 감지 → 오늘 기준 12개월 롤링 월별 흐름 + 달 단위 응답 지시. '언제'만
있는 입도 미지정 질문은 기존 10년 digest 유지(2026-06-18 결정 보존).
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.chat_service import _timing_granularity
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 7, 3)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:40",
    birth_place_name="서울", gender="male", reference_date="2026-07-03",
)

_YEAR_DIGEST_MARK = "올해부터 약 10년의 흐름을"
_MONTH_PICK_MARK = "[응답 형식 — '어느 달' 질문]"
_DAY_PICK_MARK = "[응답 형식 — '어느 날(날짜)' 질문]"
_MEETING_SEASON_MARK = "연·반기·계절 단위로 제시하라"
_MEETING_MONTH_MARK = "[인연·만남 시기 — 달 단위 요청]"


def _prompt(q: str) -> str:
    res = chat_service.chat(_BIRTH, q, _TODAY, dry_run=True)
    return res.prompt_preview or ""


# ── 입도 감지 헬퍼 ───────────────────────────────────────────────


def test_month_granularity_detected() -> None:
    assert _timing_granularity("연애를 시작하는 달은 언제야?") == "month"
    assert _timing_granularity("몇 월에 이사하면 좋아?") == "month"
    assert _timing_granularity("이직하기 좋은 달 추천해줘") == "month"
    assert _timing_granularity("어느 달이 유리해?") == "month"


def test_day_granularity_detected() -> None:
    assert _timing_granularity("연인을 만나게 될 날은 언제야?") == "day"
    assert _timing_granularity("개업하기 좋은 날 언제야?") == "day"
    assert _timing_granularity("며칠쯤이 좋을까?") == "day"


def test_granularity_not_overdetected() -> None:
    """입도 미지정·기간 표현·오탐 후보는 None — '언제'만으로는 입도 아님."""
    assert _timing_granularity("언제쯤 결혼할 수 있을까?") is None
    assert _timing_granularity("앞으로 재물운 어때?") is None
    assert _timing_granularity("한 달 안에 취업될까?") is None
    assert _timing_granularity("다음 주에 뭐가 좋아?") is None
    assert _timing_granularity("요즘 좋은 날씨네, 올해 운세 어때?") is None
    assert _timing_granularity("성격이 달라질 수 있어?") is None


# ── 라우팅 E2E(dry_run 프롬프트) ────────────────────────────────


def test_month_question_routes_to_month_pick_not_year_digest() -> None:
    """실사례 질문 — 12개월 월별 흐름 + 달 단위 지시, 10년 연 digest 미적용."""
    t = _prompt("연애를 시작하는 달은 언제야?")
    assert _MONTH_PICK_MARK in t
    assert _YEAR_DIGEST_MARK not in t
    # 오늘(2026-07) 기준 롤링 12개월 — 연도 경계를 넘어 2027년 달이 표에 포함된다.
    assert "2027-0" in t


def test_month_question_swaps_meeting_directive_to_month_variant() -> None:
    """연애 문맥 + 달 요청 — '연·반기·계절 제시' 지시 대신 달 단위 변형."""
    t = _prompt("연애를 시작하는 달은 언제야?")
    assert _MEETING_MONTH_MARK in t
    assert _MEETING_SEASON_MARK not in t


def test_career_month_question_gets_month_pick() -> None:
    t = _prompt("이직하기 좋은 달 추천해줘")
    assert _MONTH_PICK_MARK in t
    assert _YEAR_DIGEST_MARK not in t


def test_day_question_without_period_routes_to_day_pick() -> None:
    """비택일 이벤트의 날짜 질문 — 달로 좁혀 답하고 날짜 단정 금지 지시."""
    t = _prompt("연인을 만나게 될 날은 언제야?")
    assert _DAY_PICK_MARK in t
    assert _YEAR_DIGEST_MARK not in t


def test_vague_when_question_keeps_year_digest() -> None:
    """입도 미지정 '언제' 질문은 기존 10년 digest 유지(2026-06-18 결정 보존)."""
    t = _prompt("언제쯤 결혼할 수 있을까?")
    assert _YEAR_DIGEST_MARK in t
    assert _MONTH_PICK_MARK not in t
    assert _DAY_PICK_MARK not in t


def test_explicit_year_month_question_not_treated_as_no_period() -> None:
    """연도 명시 + 몇 월 질문 — 기간이 있으므로 입도-무기간 지시 미적용(기존 창 로직)."""
    t = _prompt("2027년에는 몇 월이 연애에 좋아?")
    assert _MONTH_PICK_MARK not in t
    assert _YEAR_DIGEST_MARK not in t


def test_date_recommendation_route_untouched() -> None:
    """택일 분류 질문(이사 좋은 날)은 기존 택일 라우트 유지 — day pick 미적용."""
    t = _prompt("8월에 이사하기 좋은 날 알려줘")
    assert _DAY_PICK_MARK not in t

"""대화 결함 3종 회귀 — 실로그(7/4 계약·이사) 기반.

A. 절기 월주: 절입(소서 7/7) 이전 초순일의 부모 월이 캘린더 월로 오인되던 결함
   (2026-07-04는 절기상 甲午인데 乙未로 잡힘 → 활성 간지·월지 관계 오류).
B. 단일 날짜 평가('X일에 계약·이사… 잘한 결정일까?')가 택일로 분류되지 않던 결함.
C. 날짜 사실 정정 후속('7월 4일은 갑오월이야')이 직전 계약·이사 의도를 잃고 일반 운세로
   리셋되던 결함.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate, luck_days
from saju_engines.conversation import ConversationEngine
from saju_engines.precompute import CompositeBuilder
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import QueryType
from saju_shared_types.precompute import CompositeLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1990, 3, 15), birth_time="10:00",
    birth_place_name="서울", gender="male",
)


def _day_parent_month(target: date) -> str | None:
    chart = calculate(_BIRTH.model_copy(update={"reference_date": target}))
    chart.luck_cycles.daily_luck = luck_days(_BIRTH, target.year, target.month)
    comps = CompositeBuilder(_DICTS).build(
        chart, "t", "1.0.0", f"{target.isoformat()}T00:00:00+00:00",
        levels={CompositeLevel.DAY, CompositeLevel.MONTH, CompositeLevel.YEAR},
    )
    day = next(
        c for c in comps
        if c.level is CompositeLevel.DAY and c.period_key == target.isoformat()
    )
    return day.parent_context.month


# ── A. 절기 월주 ─────────────────────────────────────────────────


def test_pre_seolgi_day_uses_prior_solar_month() -> None:
    """소서(7/7) 이전 7/4의 부모 월은 절기상 甲午(캘린더 乙未 아님)."""
    assert _day_parent_month(date(2026, 7, 4)) == "甲午"


def test_post_seolgi_day_uses_current_solar_month() -> None:
    """소서 이후 7/8의 부모 월은 乙未(회귀 — 경계 이후는 그대로)."""
    assert _day_parent_month(date(2026, 7, 8)) == "乙未"


# ── B. 단일 날짜 평가 → 택일 ─────────────────────────────────────


def test_date_decision_eval_routes_to_date_recommendation() -> None:
    """'X일에 계약·이사… 잘한 결정일까?'는 택일(date_recommendation)로 분류된다."""
    for q in ("7월 4일에 계약하고 이사하려고 해. 잘한 결정일까?",
              "7월 4일에 이사해도 될까?"):
        intent = parse_message(q, date(2026, 6, 17), birth_year=1990).intents[0]
        assert intent.query_type is QueryType.DATE_RECOMMENDATION, q


def test_vague_domain_question_not_date_recommendation() -> None:
    """시점 표지 없는 막연한 '올해 이사운 어때?'는 택일로 오분류되지 않는다."""
    intent = parse_message("올해 이사운 어때?", date(2026, 6, 17), birth_year=1990).intents[0]
    assert intent.query_type is not QueryType.DATE_RECOMMENDATION


# ── C. 대화 연속성 ───────────────────────────────────────────────


def test_date_correction_followup_inherits_prior_intent() -> None:
    """날짜 사실 정정 후속이 직전 계약·이사 의도(query_type·event_key)를 이어받는다."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    p1, state, _, _ = eng.process_turn(
        state, "7월 4일에 계약하고 이사하려고 해. 잘한 결정일까?", date(2026, 6, 17),
        birth_year=1990,
    )
    assert p1.intents[0].query_type is QueryType.DATE_RECOMMENDATION
    p2, state, _, link = eng.process_turn(
        state, "7월 4일은 갑오월이야", date(2026, 6, 17), birth_year=1990,
    )
    assert link.is_follow_up
    i2 = p2.intents[0]
    assert i2.query_type is QueryType.DATE_RECOMMENDATION  # 일반 운세로 리셋되지 않음
    assert str(i2.event_key) == "contract_document"
    assert i2.time_range is not None and i2.time_range.start == "2026-07-04"


def test_bare_affirmation_continues_prior_intent() -> None:
    """직전 답변의 제안에 대한 단순 수락('그래')이 직전 의도·시점 창을 그대로 잇는다(broad 차단)."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    _, state, _, _ = eng.process_turn(
        state, "다음 이사는 언제 어떤 이유로 할까? 1년 이후부터 확인해줘",
        date(2026, 6, 18), birth_year=1990,
    )
    prior = state.last_intent
    assert prior.domain.value == "relocation" and prior.time_range.start == "2027-06-01"
    p2, state, _, link = eng.process_turn(
        state, "그래", date(2026, 6, 18), birth_year=1990)
    assert link.is_follow_up  # is_followup_turn=True → broad 폴백 스킵
    i2 = p2.intents[0]
    assert i2.domain.value == "relocation"  # 직전 주제 유지
    assert i2.time_range is not None and i2.time_range.start == "2027-06-01"  # 2027 창 유지


def test_questioning_or_possessive_not_affirmation() -> None:
    """'그래?'(반문)·'네 사주 봐줘'(소유격 네)는 수락이 아니므로 직전 의도를 잇지 않는다."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    _, state, _, _ = eng.process_turn(
        state, "1년 이후부터 이사 언제 할까", date(2026, 6, 18), birth_year=1990)
    assert eng.link_question(state, "그래?").is_follow_up is False
    assert eng.link_question(state, "네 사주 봐줘").is_follow_up is False


def test_vague_period_uses_ten_year_year_digest() -> None:
    """막연한 시점 질문은 올해부터 10년 연(세운) digest + 대운 교운기 + 연도 지정 유도로 답한다.

    특정 연·월 미지정('결혼 때를 알고 싶어')에서 현재 연도 12개월로 좁혀 특정 달을 단정하던
    결함 보완(2026-06-18). 명시 연도 질문은 기존 월 단위 상세를 유지한다.
    """
    from saju_api.services.chat_service import chat
    from saju_shared_types.birth_input import BirthInput

    b = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    # 막연한 시점 → 연 digest 경로.
    vague = chat(b, "결혼을 둘러싼 계약과 거처 정리가 같이 움직이는 때를 알고 싶어",
                 dry_run=True, today=date(2026, 6, 18))
    p = vague.prompt_preview or ""
    assert "[월별 요약" not in p                  # 12개월 표 미생성
    assert "어느 해를 더 자세히" in p             # 연도 지정 유도 지시문
    assert "대운 흐름(배경)" in p                 # 대운 배경 + 교운기
    assert "교운기" in p
    # 명시 연도 질문은 기존 월 단위 상세(연 digest 지시문 미적용).
    specific = chat(b, "2027년 결혼운 어때?", dry_run=True, today=date(2026, 6, 18))
    assert "어느 해를 더 자세히" not in (specific.prompt_preview or "")


def test_weekly_question_surfaces_daily_overview() -> None:
    """주간(일 범위) 질문은 7일 일별 일운(간지·길흉) surface(월운 뭉뚱그림 방지, 2026-06-18)."""
    from saju_api.services.chat_service import _is_day_range, _weekly_overview_lines
    from saju_shared_types.birth_input import BirthInput

    intent = parse_message("다음주 운세는 어때?", date(2026, 6, 18)).intents[0]
    assert _is_day_range(intent)  # gran=day, 7일 범위
    b = BirthInput(
        calendar_type="solar", birth_date=date(1988, 3, 5), birth_time="10:30",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 18))
    lines = _weekly_overview_lines(b, intent, date(2026, 6, 18))
    assert lines and "일별 흐름" in lines[0]
    day_lines = [x for x in lines if x.startswith("- 2026-06-")]
    assert len(day_lines) == 7  # 7일 모두 일별 라인
    # 단일일 질문은 일 범위가 아니므로 주간 블록 미발생.
    single = parse_message("오늘 운세 어때?", date(2026, 6, 18)).intents[0]
    assert not _is_day_range(single)


# ── D. 월 후보 버킷팅 (절기 경계) ────────────────────────────────


def test_month_candidate_bucketing_uses_solar_term_bounds() -> None:
    """질문일(7/4)의 절기월(甲午=2026-06)이 '기간 내', 다음 절기월(乙未=2026-07)은 '기간 외'."""
    from saju_engines.context_reducer import _month_seolgi_bounds, in_question_range

    result = calculate(_BIRTH.model_copy(update={"reference_date": date(2026, 7, 4)}))
    mb = _month_seolgi_bounds(result)
    # 甲午(망종~소서 전일)는 7/4를 포함, 乙未(소서~)는 7/7부터.
    assert mb["2026-06"][0] <= "2026-07-04" <= mb["2026-06"][1]
    assert mb["2026-07"][0] > "2026-07-04"
    # 단일일 질문 버킷팅: 甲午 in / 乙未 out.
    assert in_question_range("2026-06", "2026-07-04", "2026-07-04", mb) is True
    assert in_question_range("2026-07", "2026-07-04", "2026-07-04", mb) is False
    # month_bounds 미제공(캘린더 경계)이면 옛 동작(7월=2026-07 in) — 하위호환.
    assert in_question_range("2026-07", "2026-07-04", "2026-07-04") is True

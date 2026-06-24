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


def test_followup_inherits_time_scope_even_on_domain_shift() -> None:
    """후속 턴이 자체 시점을 안 들고 오면(도메인 전환·link=NEW 포함) 직전 시점 창을 이어받는다.

    실로그 결함(2026-06-23): 8/31·9/30=2026 매매 맥락의 후속 '대출 안 나오나?'가 link=NEW로
    떨어져 막연한 미래(올해부터 10년) 흐름으로 빠짐. 시점은 스레드 레벨 슬롯으로 유지해야 한다.
    """
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    p1, state, _, _ = eng.process_turn(
        state, "8월 31일은 운이 어떤지, 9월 30일은 운이 어떤지 봐줄래?",
        date(2026, 6, 23), birth_year=1990,
    )
    assert p1.intents[0].time_range is not None and p1.intents[0].time_range.start
    # 후속(대출/계약 = 새 도메인, 자체 시점 없음) — link=NEW여도 직전 2026 시점 창 승계.
    p2, _state2, _, _ = eng.process_turn(
        state, "이미 집계약을 마친 후인데 대출이 안나온다거나 할까?",
        date(2026, 6, 23), birth_year=1990,
    )
    i2 = p2.intents[0]
    assert i2.time_range is not None and i2.time_range.start is not None
    assert i2.time_range.start.startswith("2026")  # 막연한 미래(10년)로 리셋되지 않음


def test_time_seeking_followup_does_not_inherit_prior_date() -> None:
    """날짜 지정 뒤 '언제/할 수 있을까' 시점-탐색 후속은 직전 날짜를 승계하지 않는다(스스로 탐색).

    실로그 결함(2026-06-23): 7/4 이사 지정 뒤 '연애 언제 시작?'까지 2026-07-04에 고정돼 풀이됨.
    """
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    _, state, _, _ = eng.process_turn(
        state, "이번 7월 4일에 이사해", date(2026, 6, 23), birth_year=1990,
    )
    assert state.last_intent.time_range.start == "2026-07-04"
    # '언제쯤 ~ 할 수 있어?' = 시점-탐색 → 7/4 미승계(open_when으로 스스로 탐색).
    p2, state, _, _ = eng.process_turn(
        state, "연애는 언제쯤 시작할 수 있어?", date(2026, 6, 23), birth_year=1990,
    )
    tr2 = p2.intents[0].time_range
    assert tr2 is None or tr2.start is None  # 7/4로 고정되지 않음
    # 이어진 '그 사람과 결혼할까?'(start 없는 직전 시점)도 7/4를 끌어오지 않는다.
    p3, _s, _, _ = eng.process_turn(
        state, "그 사람과 결혼하게 될까?", date(2026, 6, 23), birth_year=1990,
    )
    tr3 = p3.intents[0].time_range
    assert tr3 is None or tr3.start != "2026-07-04"


def test_new_explicit_time_resets_inheritance_baseline() -> None:
    """후속이 다른 시점을 새로 지정하면 그 시점이 이후 승계 기준이 된다(옛 시점 미승계)."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    _, state, _, _ = eng.process_turn(
        state, "8월 31일은 운이 어떤지 봐줄래?", date(2026, 6, 23), birth_year=1990,
    )
    # 다른 시점(2028) 지정 → 승계 기준 초기화.
    p2, state, _, _ = eng.process_turn(
        state, "그럼 2028년은 어때?", date(2026, 6, 23), birth_year=1990,
    )
    assert p2.intents[0].time_range is not None
    assert p2.intents[0].time_range.start.startswith("2028")
    # 이후 시점 없는 평가 후속은 옛 8/31이 아니라 새 기준(2028)을 승계.
    p3, _s, _, _ = eng.process_turn(
        state, "그럼 돈은 어때?", date(2026, 6, 23), birth_year=1990,
    )
    tr3 = p3.intents[0].time_range
    assert tr3 is not None and tr3.start.startswith("2028")


def test_followup_explicit_time_and_fresh_reading_skip_inheritance() -> None:
    """명시 시점을 새로 주거나 총운·새 풀이를 요청하면 직전 시점 창을 승계하지 않는다."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t1")
    _, state, _, _ = eng.process_turn(
        state, "8월 31일은 운이 어떤지 봐줄래?", date(2026, 6, 23), birth_year=1990,
    )
    # 새 풀이(총운·처음부터) — 미승계.
    p_fresh, _s, _, _ = eng.process_turn(
        state, "그럼 내 총운 처음부터 봐줘", date(2026, 6, 23), birth_year=1990,
    )
    tr = p_fresh.intents[0].time_range
    assert tr is None or not tr.start  # 직전 8/31 창을 끌고 오지 않음


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


# 절기월 경계(2026-06-22) — 7월 4일은 소서(7/7) 전이라 甲午월(절기월), 乙未월 아님.
def test_daily_question_uses_solar_month_not_calendar() -> None:
    from saju_api.services.chat_service import _build_period_fortune
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    b = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    tr = TimeRange(type="on_date", granularity=Granularity.DAY, start="2026-07-04")
    intent = IntentJson(
        intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.GENERAL, time_range=tr,
    )
    pf = _build_period_fortune(b, intent, date(2026, 6, 22), "daily")
    assert pf is not None
    # 절기월 안내가 甲午월 + 양력 범위로 주입되고, 乙未월(양력 7월 오인)은 노출되지 않는다.
    assert "甲午월" in pf.solar_month_note
    assert "2026-06-06" in pf.solar_month_note and "2026-07-06" in pf.solar_month_note
    import json
    assert "乙未" not in json.dumps(pf.model_dump(), ensure_ascii=False, default=str)


def test_date_question_selects_solar_month_candidate() -> None:
    """날짜(7/4) 질문은 월 후보를 양력 달(乙未/2026-07)이 아니라 절기월(甲午/2026-06)로 잡는다."""
    from saju_api.services.chat_service import _current_luck_month, _get_scorer
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import in_question_range
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 22),
    ))
    all_scored = _get_scorer().score_legacy(r)
    win = "2026-07-04"
    solar_m = _current_luck_month(date.fromisoformat(win), "Asia/Seoul")
    assert solar_m == "2026-06"  # 7/4는 소서 전 → 甲午월(2026-06)

    def _in_win(p: str) -> bool:
        if len(p) == 7:
            return p == solar_m
        return in_question_range(p, win, win)

    months = {c.period for c in all_scored if len(c.period) == 7 and _in_win(c.period)}
    assert months == {"2026-06"}  # 절기월만 (乙未/2026-07 제외)


def test_date_solar_month_directive_fact() -> None:
    """날짜 질문에 그 날의 절기 월간지를 '엔진 확정 사실'로 주입(LLM 양력 달 오답 차단)."""
    from saju_api.services.chat_service import _date_solar_month_note
    from saju_shared_types.birth_input import BirthInput

    b = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    # 7/4 = 소서(7/7) 전 → 甲午월(乙未 아님).
    note = _date_solar_month_note(b, date(2026, 7, 4), "Asia/Seoul")
    assert "甲午" in note and "乙未" not in note
    assert "2026-06-06" in note  # 절입 범위
    # 7/10 = 소서 후 → 乙未월.
    assert "乙未" in _date_solar_month_note(b, date(2026, 7, 10), "Asia/Seoul")


def test_specific_date_question_surfaces_day_fortune() -> None:
    """특정 날짜(다중 포함) 질문은 그 날의 일운(日運)을 사실로 주입하고 일운 중심 서술을 지시한다.

    실로그 결함(2026-06-23): '8/31·9/30 운' 질문에 월운(丙申월·丁酉월)만 답하고 일운이 빠짐.
    """
    from saju_api.services.chat_service import _date_day_fortune_note, _explicit_dates
    from saju_shared_types.birth_input import BirthInput

    b = BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    q = "중도금을 치르는 8월 31일은 운이 어떤지, 이사를 하는 9월 30일은 운이 어떤지 봐줄래?"
    dates = _explicit_dates(q, 2026)
    assert dates == [date(2026, 8, 31), date(2026, 9, 30)]  # 다중 날짜 추출
    note = _date_day_fortune_note(b, dates, "Asia/Seoul")
    # 두 날짜의 일운이 모두 사실로 들어가고, 일운 중심 서술 지시가 포함된다.
    assert "2026-08-31" in note and "2026-09-30" in note
    assert "일운(日運)" in note and "일운(日干支)을 중심으로" in note
    # 연도 생략 표기도 기준 연도로 보정.
    assert _explicit_dates("그럼 10월 5일은?", 2027) == [date(2027, 10, 5)]


def test_solar_term_boundary_day_emphasizes_continuation() -> None:
    """절기 경계 직전 날짜(양력 달 ≠ 절입 달)는 '절기월 X(N월 절입)의 기운이 아직 이어지는 날'로
    명시 — LLM 이 양력 달로 월운을 오인하던 결함 보정(2026-06-24 데굴님 지적).

    2026-07-04: 양력 7월이나 절기월은 6월 절입 甲午(소서 7/7 이전). 같은 달 날짜는 기존 형식 유지.
    """
    from datetime import date

    from saju_api.services.chat_service import _date_day_fortune_note
    from saju_shared_types.birth_input import BirthInput

    b = BirthInput(
        calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
        birth_place_name="Seoul", gender="male",
    )
    # 경계 직전(7/4, 절기월 6월 절입) → 이어짐 강조.
    boundary = _date_day_fortune_note(b, [date(2026, 7, 4)], "Asia/Seoul")
    assert "절기월 甲午(6월 절입)의 기운이 아직 이어지는 날" in boundary
    assert "일운(日運) 己卯" in boundary
    # 같은 달(6/20, 절기월도 6월 절입) → 기존 형식(오문구 방지).
    same = _date_day_fortune_note(b, [date(2026, 6, 20)], "Asia/Seoul")
    assert "기운이 아직 이어지는 날" not in same
    assert "그 날의 절기월 甲午" in same

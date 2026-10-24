"""실답 맥락 결함 5건 회귀(2026-10-19 데굴님 점검 — '이력서 넣기 좋은 날' → '이번달이나 다음달 중에
괜찮은 날은 없어?').

①이력서는 취업 사건 + 택일 ②'이번 달이나 다음 달'은 두 달 범위 ③'괜찮은 날' 날짜어 ④후속이
택일·사건을 승계(기존 process_turn 연속성으로 충족 — 회귀만 고정) ⑤총운·시기·택일 답의 일주 소개
문장 제거.
"""

from __future__ import annotations

from datetime import date

from saju_engines.conversation import ConversationEngine
from saju_engines.ilju_mention_audit import audit_ilju_mention, is_ilju_intro_sentence
from saju_engines.query_parser import parse_message
from saju_engines.time_parser import parse_time
from saju_shared_types.conversation import ConversationState
from saju_shared_types.events import EventKey
from saju_shared_types.intent import Domain, Granularity, QueryType

_TODAY = date(2026, 10, 19)
_CUR = "2026-10"


# ── ① 이력서 → 취업 사건 + 택일 ──────────────────────────────────────────


def test_resume_day_question_is_date_recommendation_with_job_event() -> None:
    it = parse_message("이력서 넣기 좋은 날을 알려줘", _TODAY, current_month_label=_CUR).intents[0]
    assert it.query_type is QueryType.DATE_RECOMMENDATION
    assert it.event_key is EventKey.JOB_GAIN
    assert it.domain is Domain.CAREER


def test_application_form_variants_route_to_date_recommendation() -> None:
    for q in ("지원서 제출하기 좋은 날짜 알려줘", "입사 지원 접수 괜찮은 날 있어?"):
        it = parse_message(q, _TODAY, current_month_label=_CUR).intents[0]
        assert it.query_type is QueryType.DATE_RECOMMENDATION, q


def test_career_overview_without_day_word_is_not_date_recommendation() -> None:
    """반례 — '이번 달 취업운 어때'는 날짜어가 없어 택일이 아니다."""
    it = parse_message("이번 달 취업운 어때?", _TODAY, current_month_label=_CUR).intents[0]
    assert it.query_type is not QueryType.DATE_RECOMMENDATION


def test_good_day_without_action_word_is_not_date_recommendation() -> None:
    """반례 — '요즘 좋은 날이 없네'처럼 행위어가 없으면 택일이 아니다."""
    it = parse_message("요즘 좋은 날이 없네", _TODAY, current_month_label=_CUR).intents[0]
    assert it.query_type is not QueryType.DATE_RECOMMENDATION


# ── ② '이번 달이나 다음 달' 두 달 범위 ───────────────────────────────────


def test_this_or_next_month_spans_two_months() -> None:
    tr, _scope = parse_time(
        "이번달이나 다음달 중에 괜찮은 날은 없어?", _TODAY, current_month_label=_CUR,
    )
    assert tr is not None
    assert (tr.start, tr.end, tr.granularity) == ("2026-10", "2026-11", Granularity.MONTH)


def test_this_month_and_next_month_variants() -> None:
    for text in ("이달과 내달 중에", "이번 달 아니면 다음 달"):
        tr, _ = parse_time(text, _TODAY, current_month_label=_CUR)
        assert tr is not None and (tr.start, tr.end) == ("2026-10", "2026-11"), text


def test_single_month_words_unchanged() -> None:
    """반례 — 한 달만 말하면 그 달 하나."""
    tr, _ = parse_time("이번 달은 어때?", _TODAY, current_month_label=_CUR)
    assert tr is not None and (tr.start, tr.end) == ("2026-10", "2026-10")
    tr, _ = parse_time("다음 달은 어때?", _TODAY, current_month_label=_CUR)
    assert tr is not None and (tr.start, tr.end) == ("2026-11", "2026-11")


# ── ④ 후속 승계(실답 2턴 재현) ───────────────────────────────────────────


def test_real_log_two_turns_keep_date_recommendation_and_job_event() -> None:
    eng = ConversationEngine()
    state = ConversationState(thread_id="x", turn_no=0)
    p1, state, _, _ = eng.process_turn(
        state, "이력서 넣기 좋은 날을 알려줘", _TODAY, current_month_label=_CUR,
    )
    assert p1.intents[0].query_type is QueryType.DATE_RECOMMENDATION
    p2, _, _, link = eng.process_turn(
        state, "이번달이나 다음달 중에 괜찮은 날은 없어?", _TODAY, current_month_label=_CUR,
    )
    i2 = p2.intents[0]
    assert link.is_follow_up is True
    assert i2.query_type is QueryType.DATE_RECOMMENDATION
    assert i2.event_key is EventKey.JOB_GAIN and i2.domain is Domain.CAREER
    assert i2.time_range is not None
    assert (i2.time_range.start, i2.time_range.end) == ("2026-10", "2026-11")


def test_new_domain_followup_is_not_swallowed() -> None:
    """반례 — 새 도메인이 명시된 후속('다음 달 연애운은?')은 택일을 승계하지 않는다."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="x", turn_no=0)
    _, state, _, _ = eng.process_turn(
        state, "이력서 넣기 좋은 날을 알려줘", _TODAY, current_month_label=_CUR,
    )
    p2, _, _, _ = eng.process_turn(
        state, "다음 달 연애운은 어때?", _TODAY, current_month_label=_CUR,
    )
    assert p2.intents[0].query_type is not QueryType.DATE_RECOMMENDATION


# ── ⑤ 일주 소개 문장 감사 ─────────────────────────────────────────────────

_INTRO = (
    "데굴님의 己亥(기해) 일주는 겉으로는 부드럽고 다정하고, 내면에는 냉철한 판단력을 품은 정원사 "
    "같은 구조입니다."
)


def test_ilju_intro_removed_in_timing_answer() -> None:
    answer = (
        "이력서는 11월 초가 나아요.\n\n" + _INTRO
        + " 현재 대운 교체기라 외부 제안이 갑자기 올 수 있어요.\n\n"
        "10월은 검토, 11월은 제출로 나누세요."
    )
    out = audit_ilju_mention(answer, QueryType.DATE_RECOMMENDATION, Domain.CAREER)
    assert out.removed and "정원사" not in out.text and "일주" not in out.text
    assert out.text.startswith("이력서는 11월 초가 나아요.")
    assert "현재 대운 교체기라 외부 제안이 갑자기 올 수 있어요." in out.text
    assert out.text.endswith("10월은 검토, 11월은 제출로 나누세요.")


def test_ilju_kept_for_relationship_and_education_questions() -> None:
    """반례 — 연애·적성(교육) 질문은 성향 근거가 필요하므로 그대로 둔다."""
    for qt, dom in ((QueryType.DOMAIN_ANALYSIS, Domain.RELATIONSHIP),
                    (QueryType.DOMAIN_ANALYSIS, Domain.EDUCATION),
                    (QueryType.CHART_ANALYSIS, Domain.GENERAL)):
        out = audit_ilju_mention(_INTRO, qt, dom)
        assert out.text == _INTRO and not out.removed


def test_ilju_luck_relation_sentence_kept() -> None:
    """반례 — 운 글자와의 관계(복음·일지 충)는 소개가 아니라 근거라 남긴다."""
    s = "이달 己亥(기해)월은 일주와 같은 간지인 복음이라 정체감이 겹쳐요."
    assert not is_ilju_intro_sentence(s)
    out = audit_ilju_mention(s, QueryType.FORTUNE_OVERVIEW, Domain.GENERAL)
    assert out.text == s


def test_ilju_audit_no_intent_is_noop() -> None:
    out = audit_ilju_mention(_INTRO, None, None)
    assert out.text == _INTRO and not out.gated

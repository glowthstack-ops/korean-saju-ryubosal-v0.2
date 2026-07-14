"""시점 정합 3계층 회귀 테스트 (2026-07-14 P0~P5).

실측 결함(아들 학업 스레드): "2026년 27년은 초딩때라 의미없고 2033년 시험운 합격운이
중요해"에서 time_parser C6이 첫 4자리 연도(2026)만 잡아 배제 대상이 스레드 시점으로
저장됐고, 후속 "그래서 원하는 대학에 붙는다는거야?"가 그 오염된 2026을 정상 승계해
현재 연도 월운을 통째 재서술했다.

계층 구성(P8):
  1. 파서 단위 — 다중 연도·부정·정정·비교·재요청 골든 패턴(P1)
  2. 상태 병합 단위 — 배제 누적·스코프 만료·명시적 재요청 해제·승계 가드(P2)
  3. 대화 E2E — 실패 전사 3턴 재현 + trace 검증(P0) / 커밋 가드·연령 지시문(P3·P5)
"""

from __future__ import annotations

from datetime import date

from saju_engines.conversation import (
    ConversationEngine,
    overlaps_exclusions,
    tr_year_span,
)
from saju_engines.time_parser import (
    extract_time_constraints,
    parse_time_with_constraints,
    resolve_time_target,
)
from saju_shared_types.conversation import ConversationState, TimeExclusion
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    TimeConstraintRole,
    TimeRange,
)

_TODAY = date(2026, 7, 14)


# ── 1계층: 파서 단위 (P1) ──────────────────────────────────────────


def _roles(text: str) -> list[tuple[str, int, int]]:
    return [
        (it.role.value, it.start_year, it.end_year)
        for it in extract_time_constraints(text, _TODAY)
    ]


def test_negation_multi_year_regression() -> None:
    """실측 결함 원문 — 배제 2026~27 + 대상 2033, 시점은 2033."""
    text = "2026년 27년은 초딩때라 의미없고 2033년 시험운 합격운이 중요해"
    assert _roles(text) == [("excluded", 2026, 2027), ("target", 2033, 2033)]
    tr, _, items = parse_time_with_constraints(text, _TODAY)
    assert tr is not None and (tr.start, tr.end) == ("2033", "2033")
    assert resolve_time_target(items) == (2033, 2033)


def test_golden_negation_patterns() -> None:
    """'A 말고 B'·'A가 아니라 B'·'A는 됐고 B'·'A까지는 아니고 B쯤' — 항상 B."""
    for text, want in [
        ("2026년 말고 2033년", 2033),
        ("2026년이 아니라 2033년인가?", 2033),
        ("2026년 이야기는 됐고, 아까 말한 2033년 결론은 뭐야?", 2033),
        ("2033년까지는 아니고 2030년쯤", 2030),
        ("2026년은 의미 없고 2033년을 봐줘", 2033),
        ("올해 말고 내년 봐줘", 2027),
    ]:
        tr, _, _ = parse_time_with_constraints(text, _TODAY)
        assert tr is not None and tr.start == str(want), text


def test_re_request_lifts_exclusion_within_turn() -> None:
    """'…의미 없다고 했지만 이번에는 다시 2026년을 봐줘' — 긍정이 승리, 배제 소멸."""
    text = "2026년이 의미 없다고 했지만 이번에는 다시 2026년을 봐줘"
    items = extract_time_constraints(text, _TODAY)
    assert [it.role for it in items] == [TimeConstraintRole.TARGET]
    tr, _, _ = parse_time_with_constraints(text, _TODAY)
    assert tr is not None and tr.start == "2026"


def test_comparison_span_kept() -> None:
    """'A와 B를 비교' — 양쪽 모두 후보(스팬), 첫 연도 단독 선택 금지."""
    tr, _, _ = parse_time_with_constraints("2027년과 2033년을 비교해줘", _TODAY)
    assert tr is not None and (tr.start, tr.end) == ("2027", "2033")


def test_all_years_excluded_returns_none() -> None:
    """언급 연도가 전부 배제면 시점 미확정(None) — 배제 연도 승격 금지."""
    tr, _, items = parse_time_with_constraints("2026년은 빼고 알려줘", _TODAY)
    assert tr is None
    assert [it.role for it in items] == [TimeConstraintRole.EXCLUDED]


def test_no_regression_on_plain_expressions() -> None:
    """단일·복합 시점 표현은 기존 규칙 결과 그대로(회귀 0)."""
    cases = {
        "2033년 운세 알려줘": ("2033", "2033", Granularity.YEAR),
        "올해 하반기 재물운": ("2026-07", "2026-12", Granularity.MONTH),
        "내년 이사운 어때?": ("2027", "2027", Granularity.YEAR),
    }
    for text, (s, e, g) in cases.items():
        tr, _, _ = parse_time_with_constraints(text, _TODAY)
        assert tr is not None and (tr.start, tr.end, tr.granularity) == (s, e, g), text
    # 데드라인('까지')·나이 기반 등 복합 표현은 재조준 대상이 아니다.
    tr, _, _ = parse_time_with_constraints("2026년 7월까지 붙을 수 있을까", _TODAY)
    assert tr is not None and tr.type == "deadline"


def test_birth_year_not_treated_as_constraint() -> None:
    """'2020년생' — 출생 표기는 연도 제약이 아니다."""
    assert _roles("2020년생 아들 학업운 봐줘") == []


# ── 2계층: 상태 병합 단위 (P2) ─────────────────────────────────────


def _turn(eng: ConversationEngine, state: ConversationState, text: str):
    return eng.process_turn(state, text, today=_TODAY)


def test_exclusion_accumulates_and_target_updates() -> None:
    """턴1 배제+대상 → 상태에 배제 저장, 대상 2033이 스레드 시점."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = _turn(eng, state, "2026년 27년은 의미없고 2033년 합격운이 중요해")
    assert [(e.start_year, e.end_year, e.scope) for e in state.time_exclusions] == [
        (2026, 2027, "current_topic")
    ]
    assert state.active_time_scope == "2033"
    assert state.active_time_meta["resolution_type"] == "explicit"


def test_followup_inherits_target_not_excluded() -> None:
    """후속 무시점 턴 — 배제 연도가 아니라 확정 대상(2033)을 승계."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = _turn(eng, state, "2026년 27년은 의미없고 2033년 합격운이 중요해")
    parsed, state, _, _ = _turn(eng, state, "그래서 원하는 대학에 붙는다는거야 아니라는거야?")
    tr = parsed.intents[0].time_range
    assert tr is not None and (tr.start, tr.end) == ("2033", "2033")
    assert state.active_time_meta["resolution_type"] == "inherited"


def test_inheritance_guard_blocks_excluded_time() -> None:
    """직전 시점이 배제 창과 겹치면 승계 차단(오염 전파 금지)."""
    eng = ConversationEngine()
    last = ConversationState(
        thread_id="t", turn_no=1,
        last_intent=IntentJson(
            intent_id="i1",
            query_type=QueryType.DOMAIN_ANALYSIS,
            domain=Domain.EDUCATION,
            time_range=TimeRange(
                type="absolute", granularity=Granularity.YEAR, start="2026", end="2026",
            ),
        ),
        time_exclusions=[TimeExclusion(start_year=2026, end_year=2027, source_turn=1)],
    )
    parsed, _, _, _ = _turn(eng, last, "합격 가능성은 어때?")
    assert parsed.intents[0].time_range is None  # 2026 승계 금지 — 미확정으로


def test_explicit_re_request_lifts_stored_exclusion() -> None:
    """이전 턴 배제(2026) 뒤 '이번에는 2026년만 다시 봐줘' — 배제 해제 + 시점 갱신."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = _turn(eng, state, "2026년은 의미없고 2033년 합격운이 중요해")
    assert state.time_exclusions
    _, state, _, _ = _turn(eng, state, "아까는 그랬지만 이번에는 2026년 학업운만 다시 봐줘")
    assert state.time_exclusions == []
    assert state.active_time_scope == "2026"


def test_topic_switch_expires_topic_scope() -> None:
    """주제 전환(link=NEW) — current_topic 스코프 배제 만료."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = _turn(eng, state, "2026년 27년은 의미없고 2033년 합격운이 중요해")
    assert state.time_exclusions
    # 새 도메인 + 완결 질문 → NEW 스레드: topic 배제가 따라가지 않는다.
    _, state, _, link = _turn(eng, state, "재물 투자 흐름 사주 전체 새로 봐줘")
    assert not link.is_follow_up
    assert state.time_exclusions == []


def test_span_helpers() -> None:
    """tr_year_span·overlaps_exclusions — 커밋 가드 공용 헬퍼."""
    tr = TimeRange(type="absolute", granularity=Granularity.MONTH, start="2033-01", end="2033-03")
    assert tr_year_span(tr) == (2033, 2033)
    excl = [TimeExclusion(start_year=2026, end_year=2027)]
    assert overlaps_exclusions((2027, 2028), excl) is True
    assert overlaps_exclusions((2033, 2033), excl) is False
    assert overlaps_exclusions(None, excl) is False


# ── 3계층: 대화 E2E — 실패 전사 재현 (P0) + P3·P4 ──────────────────


def test_e2e_failed_transcript_three_turns() -> None:
    """실패 전사 3턴 — turn2 target=2033·배제 저장, turn3 결론 요약 + 2033 승계."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    turns = [
        "학업잠재력을 그래도 100점 만점으로 환산해봐~~",
        "2026년 27년은 초딩때라 의미없고 2033년 시험운 합격운이 중요해",
        "그래서 원하는 대학에 붙는다는거야 아니라는거야?",
    ]
    parsed, state, _, _ = _turn(eng, state, turns[0])
    assert parsed.intents[0].domain is Domain.EDUCATION

    parsed, state, _, _ = _turn(eng, state, turns[1])
    assert parsed.trace["resolved_target"] == ("2033", "2033")
    assert parsed.trace["active_exclusions"][0]["start_year"] == 2026

    parsed, state, _, _ = _turn(eng, state, turns[2])
    intent = parsed.intents[0]
    assert intent.dialogue_act == "conclusion_summary"  # P4 — 재분석 아닌 결론 요약
    tr = intent.time_range
    assert tr is not None and tr.start == "2033"  # 2026 월운 재서술 회귀 차단
    assert parsed.trace["inherited_time"] == ("2033", "2033")
    assert overlaps_exclusions(tr_year_span(tr), state.time_exclusions) is False


def test_commit_guard_reverts_time_on_mismatch() -> None:
    """P3 — 답변 중심 연도가 엔진 창 밖이면 시점 슬롯 커밋을 되돌린다."""
    from saju_api.services.chat_service import _time_commit_guard

    intent = IntentJson(
        intent_id="i2", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2026", end="2026",
        ),
    )
    prior_tr = TimeRange(
        type="absolute", granularity=Granularity.YEAR, start="2033", end="2033",
    )
    state = ConversationState(
        thread_id="t", turn_no=2, active_time_scope="2026",
        last_intent=intent,
        active_time_meta={"value": "2026", "resolution_type": "explicit"},
    )
    prior = {
        "time_range": prior_tr, "active_time_scope": "2033",
        "active_time_meta": {"value": "2033", "resolution_type": "explicit"},
    }
    answer = "2033년 癸丑년은 교운기예요. 2033년의 합격 기류는 강하지만 2033년은 부담도 있어요."
    out = _time_commit_guard(state, prior, intent, answer, [])
    assert out.active_time_scope == "2033"  # 파서 2026 커밋 차단 → 직전 정상 상태 유지
    assert out.last_intent is not None and out.last_intent.time_range == prior_tr


def test_commit_guard_passes_consistent_answer() -> None:
    """P3 — 답변 중심 연도=엔진 연도면 커밋 유지(무간섭)."""
    from saju_api.services.chat_service import _time_commit_guard

    intent = IntentJson(
        intent_id="i2", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2033", end="2033",
        ),
    )
    state = ConversationState(
        thread_id="t", turn_no=2, active_time_scope="2033", last_intent=intent,
    )
    answer = "2033년 흐름은 이렇고, 준비는 2032년 말부터 하면 좋아요. 2033년이 관건이에요."
    out = _time_commit_guard(state, {}, intent, answer, [])
    assert out.active_time_scope == "2033"


def test_excluded_candidates_dropped() -> None:
    """후속① — 배제 연도(2026~27)의 세운·월운 후보를 산출 단계에서 제거(빈 결과 허용)."""
    from dataclasses import dataclass

    from saju_api.services.chat_service import _drop_excluded_candidates

    @dataclass
    class _C:
        period: str

    cands = [_C("2026"), _C("2026-07"), _C("2027-01"), _C("2033"), _C("2033-11")]
    excl = [TimeExclusion(start_year=2026, end_year=2027)]
    assert [c.period for c in _drop_excluded_candidates(cands, excl)] == ["2033", "2033-11"]
    # 전부 배제면 빈 결과 유지(배제는 사용자 지시 — fallback 원본 복원 금지).
    assert _drop_excluded_candidates([_C("2026"), _C("2027-03")], excl) == []


def test_conclusion_rule_covers_sori_tteut_variants() -> None:
    """후속② 룰 확장 — '~다는 소리야/뜻이야' 변형도 결론 요구형으로 감지."""
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = _turn(eng, state, "2033년 아들 합격운이 중요해")
    parsed, _, _, _ = _turn(eng, state, "그래서 우리 애가 합격한다는 소리야 뭐야")
    assert parsed.intents[0].dialogue_act == "conclusion_summary"


def test_dialogue_act_classifier_fallback() -> None:
    """후속② 임베딩 폴백 — 룰 미스 완곡 표현을 conclusion_summary로 제안(distractor 무오탐)."""
    import pytest

    from saju_engines.dialogue_act_similarity import (
        DIALOGUE_ACT_MIN_MARGIN,
        DIALOGUE_ACT_MIN_SCORE,
        get_dialogue_act_classifier,
    )

    clf = get_dialogue_act_classifier()
    if not clf.available():  # 의존성·모델 부재 환경 — graceful 비활성 확인만
        pytest.skip("intent ONNX 미설치 — 룰만으로 동작")
    sug = clf.classify("한마디로 되는 거야 마는 거야")
    assert (
        sug is not None and sug.label == "conclusion_summary"
        and sug.score >= DIALOGUE_ACT_MIN_SCORE and sug.margin >= DIALOGUE_ACT_MIN_MARGIN
    )
    # distractor(새 분석·근거 요청·재분석)는 conclusion_summary 게이트를 통과하지 않는다.
    for text in ["내년에 이사 가도 괜찮을까?", "왜 그 해가 좋다는 건지 근거를 알려줘",
                 "월별로 다시 자세히 봐줘"]:
        d = clf.classify(text)
        assert d is None or d.label != "conclusion_summary" or (
            d.score < DIALOGUE_ACT_MIN_SCORE or d.margin < DIALOGUE_ACT_MIN_MARGIN
        ), text


def test_minor_lifestage_directive() -> None:
    """P5 — 목표 연도 기준 만 나이로 미성년 지시문 생성(성인은 None)."""
    from saju_api.services.chat_service import _minor_lifestage_directive_text
    from saju_shared_types.birth_input import BirthInput

    birth = BirthInput(
        birth_date=date(2014, 5, 1), birth_place_name="서울", gender="male",
    )
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2033", end="2033",
        ),
    )
    text = _minor_lifestage_directive_text(birth, intent, _TODAY)
    assert text is not None and "2033년" in text and "고등" in text
    # 같은 대상이라도 성인이 되는 연도면 미적용.
    adult_intent = intent.model_copy(update={
        "time_range": TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2036", end="2036",
        ),
    })
    assert _minor_lifestage_directive_text(birth, adult_intent, _TODAY) is None

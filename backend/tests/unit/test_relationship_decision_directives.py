"""결혼·이혼 결정 디렉티브 게이트 — 운 저점 보류(E2)·이혼 사유 severity(T1).

궁합 자료: 운 저점엔 큰 결정 보류(조급함이 신호), 이혼 사유는 외도·폭력(회복 난) vs 성격·건강
(극복 가능)으로 결을 나눈다. 디렉티브는 결정 어미/이혼 키워드가 있을 때만 주입한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.chat_service import (
    _MEETING_TIMING_DIRECTIVE,
    _is_big_decision,
    _is_divorce_question,
    _is_relationship_context,
    _structural_context,
)
from saju_engines.query_parser import parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain, IntentJson, QueryType


def _intent(q: str):
    return parse_message(q, date(2026, 6, 20)).intents[0]


def test_big_decision_detected() -> None:
    for q in ("지금 결혼해도 될까?", "이혼하는 게 좋을까요?", "재혼해야 할까"):
        assert _is_big_decision(_intent(q), q), q


def test_big_decision_not_for_plain_relationship_question() -> None:
    # 결정 어미 없는 일반 관계 질문은 보류 디렉티브 대상이 아니다.
    q = "올해 연애운 어때?"
    assert not _is_big_decision(_intent(q), q)


def test_divorce_question_detected() -> None:
    assert _is_divorce_question("이혼 고민 중이에요")
    assert _is_divorce_question("별거 중인데 어떨까요")
    assert not _is_divorce_question("결혼운 좋아질까")


# 인연·만남 시기(Fix B) — GENERAL로 분류되는 '언제 만나' 질문도 관계 맥락으로 잡아 디렉티브 주입.
def test_relationship_context_catches_general_meeting_question() -> None:
    q = "그럼 그 연인은 어디서 언제쯤 만나는거야?"
    intent = IntentJson(intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.GENERAL)
    assert _is_relationship_context(intent, q)  # '연인' 키워드로 보강
    # 디렉티브가 만남=택일 아님·장소 단정 금지를 담는다.
    assert "택일이 아니다" in _MEETING_TIMING_DIRECTIVE
    assert "지어내지" in _MEETING_TIMING_DIRECTIVE


def test_relationship_context_false_for_unrelated() -> None:
    intent = IntentJson(intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.WEALTH)
    assert not _is_relationship_context(intent, "내년 재물운 어때?")


# 배우자성 가드(Fix A) — GENERAL 관계 질문의 구조 컨텍스트에도 성별 가드가 동반된다.
def test_spouse_guard_in_structural_context_for_general() -> None:
    from saju_api.services.manse_service import calculate

    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))
    intent = IntentJson(intent_id="x", query_type=QueryType.TIMING_SEARCH, domain=Domain.GENERAL)
    ctx = "\n".join(_structural_context(r, intent, date(2026, 6, 22)))
    assert "[배우자성 — 성별 기준]" in ctx  # general에도 가드 포함
    assert "배우자가 아니다" in ctx  # 남성 정관≠배우자


# 토픽 연속 후속(2026-06-22) — 활성 관계 스레드에서 새 도메인 없는 구체 후속은 too_broad 바운스 대신
# 직전 분야를 잇는 drill-down. '주변 사람 vs 새로운 사람?'이 시점 좁히기로 바운스되던 결함 차단.
def test_topic_continuity_followup_for_partner_source() -> None:
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState

    last = IntentJson(
        intent_id="i0", query_type=QueryType.TIMING_SEARCH, domain=Domain.RELATIONSHIP,
    )
    state = ConversationState(thread_id="t1", last_intent=last, turn_no=1)
    eng = ConversationEngine()
    # 핵심: 도메인·시점 없는 구체 관계 후속 → 팔로업(직전 관계 분야 상속).
    link = eng.link_question(state, "주변에 있는 사람이야 아니면 완전히 새로운 사람이야?")
    assert link.is_follow_up and link.inherited_domain is Domain.RELATIONSHIP
    # 가드: 짧은 반응어·새 풀이/리셋 요청은 팔로업 아님(별도 처리/새 스레드 보존).
    assert eng.link_question(state, "그래?").is_follow_up is False
    assert eng.link_question(state, "네 사주 봐줘").is_follow_up is False
    assert eng.link_question(state, "총운 처음부터 다시 봐줘").is_follow_up is False


def test_partner_source_question_and_directive() -> None:
    from saju_api.services.chat_service import _is_partner_source_question
    from saju_engines.structural_context import PARTNER_SOURCE_DIRECTIVE

    assert _is_partner_source_question("주변에 있는 사람이야 아니면 완전히 새로운 사람이야?")
    assert _is_partner_source_question("소개로 만나? 아니면 새 사람?")
    assert not _is_partner_source_question("언제 결혼해?")
    # 디렉티브는 합·도화=가까운 / 충·역마=새 인연 근거 + 비단정을 담는다.
    assert "합" in PARTNER_SOURCE_DIRECTIVE and "역마" in PARTNER_SOURCE_DIRECTIVE
    assert "확정할 수는 없" in PARTNER_SOURCE_DIRECTIVE

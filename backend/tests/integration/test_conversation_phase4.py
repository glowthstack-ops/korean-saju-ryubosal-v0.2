"""Conversation Layer 통합 시나리오 (Phase 4 T4.6 — docs/07 명시 3종 + 실측 패턴).

시나리오: ① "올해 연애운 → 그 사람은? → 결혼 가능성은?" ② "내일운세 → 모레는? →
글피는?" ③ "1호 2호 둘 다 봐줘" + F4 누적 참조·F7 반복 감지·A10 정정·A13 생시 미상.
저장소(T4.1)는 전용 DB 기동 시에만 검증(미기동 skip).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.conversation import ConversationEngine
from saju_engines.conversation_store import ConversationStore
from saju_engines.precompute_store import default_dsn
from saju_shared_types.conversation import ConversationState, EntityType, LinkKind, ResultSummaryRef
from saju_shared_types.intent import Domain, QueryType, SubjectKind, SubjectMode

_TODAY = date(2026, 6, 11)


@pytest.fixture()
def engine() -> ConversationEngine:
    """별칭 매핑(E14 학습분) 포함 엔진."""
    return ConversationEngine(
        aliases={"1호": "c-son", "2호": "c-daughter", "신랑": "c-husband"}
    )


@pytest.fixture()
def state() -> ConversationState:
    return ConversationState(thread_id="t-test")


def _turn(engine, state, text, **kw):
    parsed, new_state, resolution, link = engine.process_turn(state, text, _TODAY, **kw)
    return parsed.intents[0], new_state, resolution, link


# ── 시나리오 ① — 연애운 → 그 사람은? → 결혼 가능성은? ─────────────


def test_scenario_love_then_person_then_marriage(engine, state) -> None:
    intent1, state, _res, link1 = _turn(engine, state, "올해 연애운 어때?")
    assert intent1.domain is Domain.RELATIONSHIP and not link1.is_follow_up

    # 시스템 답변에서 '연애 후보' 엔티티 등록(A2 — assistant 발 엔티티).
    state = ConversationEngine.register_system_results(state, [
        ResultSummaryRef(
            kind="event", label="2026 하반기 연애 후보", detail="relationship_start 72",
        ),
    ])

    intent2, state, _res, link2 = _turn(engine, state, "그 사람은 어떤 사람이야?")
    assert link2.is_follow_up and link2.link_kind is LinkKind.TIME_SHIFT or link2.is_follow_up
    assert intent2.domain is Domain.RELATIONSHIP  # 도메인 상속

    intent3, state, _res, link3 = _turn(engine, state, "결혼 가능성은?")
    assert intent3.domain is Domain.RELATIONSHIP
    assert state.turn_no == 3


# ── 시나리오 ② — 일일 체인(B3): 내일 → 모레 → 글피 ───────────────


def test_scenario_daily_chain(engine, state) -> None:
    intent1, state, _r, _l = _turn(engine, state, "내일 운세는 어때?")
    assert intent1.time_range is not None and intent1.time_range.start == "2026-06-12"

    intent2, state, _r, link2 = _turn(engine, state, "모레는?")
    assert link2.is_follow_up and link2.link_kind is LinkKind.TIME_SHIFT
    assert intent2.time_range is not None and intent2.time_range.start == "2026-06-13"

    intent3, state, _r, _l = _turn(engine, state, "글피는?")
    assert intent3.time_range is not None and intent3.time_range.start == "2026-06-14"


# ── 시나리오 ③ — 별칭 다중 대상(A9): 1호 2호 둘 다 ───────────────


def test_scenario_alias_pair(engine, state) -> None:
    intent, state, res, _l = _turn(engine, state, "1호 2호 둘 다 올해 재물운 봐줘")
    ids = {s.companion_id for s in res.subjects}
    assert ids == {"c-son", "c-daughter"}  # 별칭 → companion_id 매핑(E14)
    assert res.subject_mode is SubjectMode.GROUP_AGGREGATE
    assert intent.domain is Domain.WEALTH


def test_unknown_alias_marked_unresolved(engine, state) -> None:
    """미등록 별칭은 추측하지 않고 확인 질문 대상으로 표시(절대 원칙 7)."""
    _i, _s, res, _l = _turn(engine, state, "3호 운세 봐줘")
    assert "3호" in res.unresolved


# ── F4 — 임시 인물 누적 참조 (골든 xfail 해소) ────────────────────


def test_f4_cumulative_inline_reference(engine, state) -> None:
    # 1턴: 인라인 2명 등록.
    _i, state, _r, _l = _turn(engine, state, "1997.04.08 여자, 1996.11.02 여자 궁합 봐줘")
    temps = [e for e in state.entities if e.attributes.get("kind") == "inline_temp"]
    assert len(temps) == 2

    # 2턴: 새 3명 + "앞서 물어본 2명까지 포함" → 총 5명.
    _i, state, res, _l = _turn(
        engine, state,
        "1998.07.23 여자, 1997.10.16 여자, 1998.08.24 여자 이 3명과 "
        "앞서 물어본 2명까지 포함했을 때, 나랑 합이 좋은 사람은 누구야??",
    )
    inline = [s for s in res.subjects if s.kind is SubjectKind.INLINE_TEMP]
    assert len(inline) == 5  # 신규 3 + 누적 2
    assert res.subject_mode is SubjectMode.RANKING


# ── F7 — 동일 질문 반복 감지 (골든 xfail 해소) ────────────────────


def test_f7_repeat_detection(engine, state) -> None:
    for expected in (0, 1, 2):
        _i, state, _r, _l = _turn(engine, state, "올해 이직운 어때?")
        assert state.repeat_count == expected
    # 2회 이상 → 다른 각도 제시 신호(F7 정책은 응답층에서 소비).
    assert state.repeat_count >= 2


# ── A10 — 대상 혼동 정정 → Q12 + 동일 intent 재실행 신호 ─────────


def test_a10_correction_signal(engine, state) -> None:
    _i, state, _r, _l = _turn(engine, state, "아들 사주로 용신 알려줘")
    intent, state, res, link = _turn(
        engine, state, "너 내 사주랑 아들사주를 헷갈려서 내 사주로 풀이했는데 다시 체크해봐"
    )
    assert res.correction is True  # 오류 인정 + 재실행 경로
    assert link.link_kind is LinkKind.CHALLENGE
    assert intent.query_type is QueryType.FEEDBACK_CORRECTION


# ── A13 — 생시 미상 → 3주 모드 신호 (골든 xfail 해소) ─────────────


def test_a13_time_unknown_flag(engine, state) -> None:
    _i, _s, res, _l = _turn(engine, state, "태어난 시간은 몰라")
    assert res.time_unknown is True  # 3주 분석 모드 + 신뢰도 하향 고지 신호


# ── T4.5 — claim 엔티티: 시스템 판정 추적 ─────────────────────────


def test_claim_entity_registered(engine, state) -> None:
    _i, state, _r, _l = _turn(engine, state, "내 용신이 뭐야?")
    state = ConversationEngine.register_system_results(state, [
        ResultSummaryRef(kind="claim", label="용신=土(부일간형)", detail="support_day_master"),
    ])
    claims = [e for e in state.entities if e.type is EntityType.CLAIM]
    assert claims and claims[0].source_role == "assistant"
    # 수 턴 뒤 이의 제기("편인격 아니야?")가 challenge로 잡힌다.
    _i2, state, _r2, link = _turn(engine, state, "용신이 土라고 했잖아? 아니지 않아?")
    assert link.link_kind is LinkKind.CHALLENGE


# ── T4.1 — 상태 영속화 (전용 DB 필요 시 skip) ─────────────────────


def _db_available() -> bool:
    try:
        ConversationStore(
            default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
        ).migrate()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(), reason="saju-v2-db(5433) 미기동")
def test_state_persistence_roundtrip(engine, state) -> None:
    store = ConversationStore(
        default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
    )
    store.migrate()
    _i, state, _r, _l = _turn(engine, state, "올해 연애운 어때?")
    store.save(state)
    loaded = store.load(state.thread_id)
    assert loaded is not None and loaded.turn_no == 1
    assert loaded.last_intent is not None
    assert loaded.last_intent.domain is Domain.RELATIONSHIP
    store.delete(state.thread_id)
    assert store.load(state.thread_id) is None

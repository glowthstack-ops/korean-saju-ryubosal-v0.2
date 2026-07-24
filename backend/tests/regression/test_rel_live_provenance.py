"""P1 선행 안전 보강 회귀 (RELATIONSHIP_EVENT_SYSTEM — 2026-07-24 승인 조건 2건).

① live 관계 컨텍스트 유래 후보가 흡수·대표 수렴을 거쳐도 provenance가 대표에 OR
  전파되고 노출 경로에서 차단된다(하드 게이트가 target namespace에만 의존하지 않음).
② 동일 turn의 동시/재시도 재처리에서 state·fact가 내용상 한 번만 적용된다.
"""

from __future__ import annotations

from saju_api.services.relationship_shadow import (
    build_relationship_shadow_contexts,
    strip_live_relationship_candidates,
)
from saju_engines.risk_engine import _apply_specificity_suppression
from saju_engines.user_facts import extract_user_facts, merge_user_facts
from saju_shared_types.conversation import ConversationState
from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)

_REL_ATOM = "relation:CHUNG:day_pillar:branch:ZHENGGUAN"


def _evidence(source: str = _REL_ATOM) -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"2026|{source}", code="SYN", period_key="2026",
        layer="sewoon", source=source, strength=0.5, role=EvidenceRole.TRIGGER,
        source_group="event_shape", target_domain=RiskDomain.RELATIONSHIP,
    )


def _cand(risk_id: str, *, rank: int, live: bool = False,
          target: str | None = None, family: str = "fam_rel") -> RiskCandidate:
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.RELATIONSHIP, kind=RiskKind.INCIDENT_RISK,
        risk_family=family, period_key="2026", evidence=[_evidence()],
        exposure_status=ExposureStatus.CONFIRMED,
        trigger_cause_atoms=[_REL_ATOM],
        specificity_rank=rank,
        relationship_target_id=target,
        live_relationship_context_derived=live,
    )


# ── ① provenance 전파·차단 ───────────────────────────────────────────


def test_live_absorbed_into_general_primary_propagates_flag() -> None:
    """live 후보가 일반 대표에 흡수 → 대표도 live-derived=True(그룹 OR) → 노출 차단."""
    live = _cand("REL_LIVE_SPECIFIC", rank=1, live=True, target="relstate-1")
    primary = _cand("REL_GENERAL_PRIMARY", rank=3, live=False, target=None)
    out = _apply_specificity_suppression([primary, live])
    absorbed = next(c for c in out if c.risk_id == "REL_LIVE_SPECIFIC")
    rep = next(c for c in out if c.risk_id == "REL_GENERAL_PRIMARY")
    assert absorbed.suppressed_by_specificity == "REL_GENERAL_PRIMARY"
    assert rep.live_relationship_context_derived is True  # 원래 False였어도 OR 전파
    kept, removed = strip_live_relationship_candidates(out)
    assert removed == 2 and kept == []  # 대표·흡수분 모두 노출 경로 제거


def test_general_absorbed_into_live_primary_blocked() -> None:
    """반대 방향 — live 대표는 자체 flag로 차단, target 제거돼도 유지."""
    live_primary = _cand("REL_LIVE_PRIMARY", rank=3, live=True, target="relstate-2")
    general = _cand("REL_GENERAL_SUB", rank=1, live=False, target=None)
    out = _apply_specificity_suppression([live_primary, general])
    rep = next(c for c in out if c.risk_id == "REL_LIVE_PRIMARY")
    # target_id가 이후 단계에서 제거·재구성돼도 flag가 주 판단으로 차단을 유지한다.
    stripped_target = rep.model_copy(update={"relationship_target_id": None})
    kept, removed = strip_live_relationship_candidates([stripped_target])
    assert removed == 1 and kept == []


def test_copy_does_not_lose_flag() -> None:
    """복사·재구성 시 기본값 False로 유실되지 않는다(model_copy 보존)."""
    c = _cand("REL_X", rank=2, live=True, target="relstate-3")
    assert c.model_copy().live_relationship_context_derived is True
    assert c.model_copy(update={"score": 10}).live_relationship_context_derived is True


def test_non_live_rel_candidates_still_exposable() -> None:
    """QA·비live REL 후보는 필터를 통과한다(기존 노출 동작 불변)."""
    qa = _cand("REL_QA", rank=2, live=False, target="qa-target-9")
    kept, removed = strip_live_relationship_candidates([qa])
    assert removed == 0 and kept == [qa]


# ── ② 동시/재시도 idempotency (내용 수렴) ─────────────────────────────


def _turn_payload(text: str, turn: int, state: ConversationState) -> None:
    """한 요청의 관계 처리 전체(facts 병합 + 상태 apply)를 재현한다."""
    state.user_facts = merge_user_facts(
        state, extract_user_facts(text, turn), topic_reset=False
    )
    build_relationship_shadow_contexts(
        question=text, state=state, turn=turn, profile_relationship_status=None,
    )


def test_concurrent_same_turn_converges_to_single_application() -> None:
    """동일 conversation·turn·발화를 두 독립 사본이 처리 → 최종 내용 동일·중복 0.

    (동시 요청은 각자 DB에서 상태를 로드하므로 서명 미공유 — 내용 기반 수렴으로 보장.)
    """
    text = "남자친구가 있어"
    a = ConversationState(thread_id="t")
    b = ConversationState(thread_id="t")
    _turn_payload(text, 5, a)
    _turn_payload(text, 5, b)
    # 두 사본의 최종 상태가 동일(마지막 저장이 이겨도 내용 무손실).
    assert a.relationship_states.model_dump() == b.relationship_states.model_dump()
    assert [f.quote for f in a.user_facts] == [f.quote for f in b.user_facts]
    # 같은 사본에 두 번(재시도) — fact·state 중복 0.
    _turn_payload(text, 5, a)
    assert len([f for f in a.user_facts if f.key == "relationship_status"]) == 1
    assert len(a.relationship_states.target_states) == 1


def test_persist_failure_retry_consistent() -> None:
    """apply 성공 후 영속화 실패 → 구 상태로 재시도해도 최종 상태 일관·중복 없음."""
    text = "남편과 별거 중이야"
    persisted = ConversationState(thread_id="t")   # 저장 실패로 남은 구 상태
    _turn_payload(text, 3, persisted)
    retry = ConversationState(thread_id="t")       # 재시도: 구 상태에서 재로드
    _turn_payload(text, 3, retry)
    assert retry.relationship_states.model_dump() == persisted.relationship_states.model_dump()
    assert len(retry.relationship_states.target_states) == 1

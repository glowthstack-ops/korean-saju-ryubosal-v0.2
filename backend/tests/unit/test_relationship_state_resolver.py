"""관계 상태 해소기·저장 구조 검증 — P0-B3 (RELATIONSHIP_EVENT_SYSTEM 부록 C-3).

필수 fixture(§9)·완료 게이트 항목을 고정한다: 시간성 4종, 정정·부정 supersede,
제3자 배제, 다중 target, MARRIED+SEPARATED, RECONCILING 비자동, 파생 개괄,
직렬화 round-trip·과거 payload 호환.
"""

from __future__ import annotations

from saju_engines.relationship_state_resolver import (
    apply_state_update,
    decide_state_update,
    parse_relationship_utterance,
)
from saju_engines.user_facts import extract_user_facts
from saju_shared_types.conversation import ConversationState
from saju_shared_types.relationship_event import RelationshipCondition, RelationshipStage
from saju_shared_types.relationship_state import (
    RelationshipStateStore,
    TemporalStatus,
    derive_relationship_overview,
)


def _decide(text: str, target: str | None = "t1", turn: int = 1):
    return decide_state_update(
        parse_relationship_utterance(text), target_id=target, turn=turn
    )


# ── 시간성 4종 (C-3 표) ──────────────────────────────────────────────


def test_current_dating_updates_state() -> None:
    d = _decide("남자친구가 있어")
    assert d.update and d.reason == "ok"
    assert d.new_state is not None
    assert d.new_state.stage is RelationshipStage.DATING
    assert d.new_state.temporal_status is TemporalStatus.CURRENT


def test_past_partner_does_not_update() -> None:
    d = _decide("작년에 남자친구가 있었어")
    assert not d.update and d.reason == "past"


def test_planned_marriage_does_not_promote_stage() -> None:
    """'다음 달에 결혼할 예정' → 현 stage 승격 금지, planned로만 보존."""
    d = _decide("다음 달에 결혼할 예정이야")
    assert not d.update and d.reason == "planned_only"
    assert d.planned_stage is RelationshipStage.MARRIED

    store = RelationshipStateStore()
    apply_state_update(store, d, turn=1, target_id="t1")
    st = store.target_states["t1"]
    assert st.stage is RelationshipStage.COMMITMENT  # 약속 존재 함의 — MARRIED 금지
    assert st.planned_stage is RelationshipStage.MARRIED


def test_hypothetical_breakup_keeps_current_state() -> None:
    """'남자친구와 헤어지면 어떻게 될까?' → HYPOTHETICAL, 현재 DATING 유지."""
    store = RelationshipStateStore()
    apply_state_update(store, _decide("남자친구가 있어"), turn=1, target_id="t1")
    d = _decide("남자친구와 헤어지면 어떻게 될까?")
    assert not d.update and d.reason == "hypothetical"
    assert store.target_states["t1"].stage is RelationshipStage.DATING


# ── 정정·부정 (§9) ───────────────────────────────────────────────────


def test_correction_dating_to_some_supersedes() -> None:
    """'남자친구가 있는 게 아니라 썸 타는 사람이야' → DATING 대신 CONTACT."""
    store = RelationshipStateStore()
    apply_state_update(store, _decide("남자친구가 있어"), turn=1, target_id="t1")
    d = _decide("남자친구가 있는 게 아니라 썸 타는 사람이야", turn=2)
    assert d.update and d.new_state is not None
    assert d.new_state.stage is RelationshipStage.CONTACT
    apply_state_update(store, d, turn=2, target_id="t1")
    assert store.target_states["t1"].stage is RelationshipStage.CONTACT


def test_negation_dating_to_contact_only() -> None:
    """'연애 중은 아니고 연락만 하고 있어' → CONTACT + in_contact."""
    d = _decide("연애 중은 아니고 연락만 하고 있어")
    assert d.update and d.new_state is not None
    assert d.new_state.stage is RelationshipStage.CONTACT
    assert d.new_state.contact_state == "in_contact"


def test_marital_correction_divorce_overrides_not_profile() -> None:
    """'기혼이라고 했는데 이혼했어' → 전역 override 저장(프로필 자동 수정 아님) + 충돌 표시."""
    store = RelationshipStateStore()
    d = _decide("아까 기혼이라고 했는데 이혼했어", target=None)
    assert d.marital_override == "이혼"
    conflict = apply_state_update(
        store, d, turn=3, profile_marital_status="기혼"
    )
    assert store.marital_status_override == "이혼"
    assert conflict is True  # 텔레메트리 근거


# ── 전 연인·재회 (§9) ────────────────────────────────────────────────


def test_ex_partner_contact_is_not_reconciling() -> None:
    """'전 남자친구와 연락 중이야' → CONTACT까지만, RECONCILING 자동 확정 금지."""
    d = _decide("전 남자친구와 다시 연락 중이야")
    assert d.update and d.new_state is not None
    assert d.new_state.stage is RelationshipStage.CONTACT
    assert d.new_state.target_role == "ex_partner"
    assert d.new_state.condition is not RelationshipCondition.RECONCILING


def test_explicit_reconcile_sets_reconciling() -> None:
    d = _decide("전 남자친구와 다시 만나기로 했어")
    assert d.update and d.new_state is not None
    assert d.new_state.condition is RelationshipCondition.RECONCILING


def test_breakup_sets_none_separated() -> None:
    """'어제 남자친구랑 헤어졌어' → 결과가 현재인 종료 발화(stage NONE + SEPARATED)."""
    d = _decide("어제 남자친구랑 헤어졌어")
    assert d.update and d.new_state is not None
    assert d.new_state.stage is RelationshipStage.NONE
    assert d.new_state.condition is RelationshipCondition.SEPARATED


# ── 별거·제3자·대상 미해소 (§9) ──────────────────────────────────────


def test_married_separated_representation() -> None:
    """'남편과 별거 중이야' → MARRIED + SEPARATED (stage 자동 NONE 금지)."""
    d = _decide("남편과 별거 중이야")
    assert d.update and d.new_state is not None
    assert d.new_state.stage is RelationshipStage.MARRIED
    assert d.new_state.condition is RelationshipCondition.SEPARATED


def test_third_party_never_updates_user_state() -> None:
    d = _decide("친구 남자친구 사주 좀 봐줘")
    assert not d.update and d.reason == "third_party"


def test_unresolved_target_fail_closed() -> None:
    d = _decide("남자친구가 있어", target=None)
    assert not d.update and d.reason == "target_unresolved"


def test_multiple_targets_kept_separately() -> None:
    """다중 상대 — 서로 다른 target_id로 유지(역할어 key 덮어쓰기 금지)."""
    store = RelationshipStateStore()
    apply_state_update(store, _decide("남자친구가 있어", target="cur-1"), turn=1)
    apply_state_update(
        store, _decide("전 남자친구와 다시 연락 중이야", target="ex-1"), turn=2
    )
    assert store.target_states["cur-1"].stage is RelationshipStage.DATING
    assert store.target_states["ex-1"].target_role == "ex_partner"
    assert len(store.target_states) == 2


# ── 파생 개괄 (전역 권위값 저장 금지) ─────────────────────────────────


def test_overview_derived_not_stored() -> None:
    store = RelationshipStateStore()
    apply_state_update(store, _decide("남자친구가 있어"), turn=1, target_id="t1")
    ov = derive_relationship_overview("미혼", store)
    assert ov.has_current_partner is True
    assert ov.current_partner_target_ids == ["t1"]
    assert ov.effective_marital_status == "미혼"
    # 별거 부부 — 상대 존재로 센다.
    store2 = RelationshipStateStore()
    apply_state_update(store2, _decide("남편과 별거 중이야", target="s1"), turn=1)
    assert derive_relationship_overview("기혼", store2).has_current_partner is True
    # 이별(stage NONE) — 자연 제외.
    store3 = RelationshipStateStore()
    apply_state_update(store3, _decide("어제 남자친구랑 헤어졌어", target="x1"), turn=1)
    assert derive_relationship_overview(None, store3).has_current_partner is False


def test_overview_marital_override_precedence() -> None:
    store = RelationshipStateStore()
    apply_state_update(
        store, _decide("이혼했어", target=None), turn=1, profile_marital_status="기혼"
    )
    ov = derive_relationship_overview("기혼", store)
    assert ov.effective_marital_status == "이혼" and ov.marital_from_override


# ── 직렬화·호환 (C-3 §10) ────────────────────────────────────────────


def test_conversation_state_old_payload_compat() -> None:
    """신규 필드 없는 과거 payload → 기본 store로 역직렬화."""
    st = ConversationState.model_validate({"thread_id": "t"})
    assert st.relationship_states.target_states == {}
    assert st.relationship_states.schema_version == "1"


def test_conversation_state_roundtrip_with_states() -> None:
    st = ConversationState(thread_id="t")
    apply_state_update(
        st.relationship_states, _decide("남편과 별거 중이야", target="s1"), turn=1
    )
    restored = ConversationState.model_validate_json(st.model_dump_json())
    got = restored.relationship_states.target_states["s1"]
    assert got.stage is RelationshipStage.MARRIED
    assert got.condition is RelationshipCondition.SEPARATED


# ── user_facts evidence ledger 분리 (C-3) ────────────────────────────


def test_user_facts_relationship_slot_global_scope() -> None:
    facts = extract_user_facts("어제 남자친구랑 헤어졌어", turn=3)
    rel = [f for f in facts if f.key == "relationship_status"]
    assert rel and rel[0].scope == "global"  # topic reset에 안 지워짐
    assert "헤어졌" in rel[0].quote


def test_user_facts_excludes_third_party_and_hypothetical() -> None:
    assert not [
        f for f in extract_user_facts("친구 남자친구 사주 좀 봐줘", turn=1)
        if f.key == "relationship_status"
    ]
    assert not [
        f for f in extract_user_facts("남자친구와 헤어지면 어떻게 될까?", turn=1)
        if f.key == "relationship_status"
    ]


def test_user_facts_marital_correction_slot() -> None:
    facts = extract_user_facts("아까 기혼이라고 했는데 이혼했어", turn=2)
    assert any(f.key == "marital_correction" for f in facts)

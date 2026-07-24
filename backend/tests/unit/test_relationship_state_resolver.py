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


# ── P0-B3 폐쇄 보완(2026-07-24 리뷰) — LLM 비노출·다중 상대·다중 절·planned 조건 ────


def test_state_only_facts_excluded_from_llm_block() -> None:
    """폐쇄 조건 ①② — 신규 관계 슬롯은 기존 user_facts_block(LLM)에서 제외된다."""
    from saju_engines.user_facts import user_facts_block

    facts = extract_user_facts("어제 남자친구랑 헤어졌어. 이혼했어.", turn=1)
    rel_keys = {f.key for f in facts}
    assert "relationship_status" in rel_keys and "marital_correction" in rel_keys
    block = user_facts_block(facts)
    assert block is None  # 관계 사실만 있으면 블록 자체가 없다(출력 불변)

    mixed = facts + extract_user_facts("이미 계약도 끝냈고", turn=1)
    mixed_block = user_facts_block(mixed)
    assert mixed_block is not None
    assert "헤어졌" not in mixed_block and "이혼" not in mixed_block
    assert "계약" in mixed_block  # 기존 슬롯은 그대로 노출


def test_multi_target_evidence_not_lost_in_ledger() -> None:
    """폐쇄 조건 ③ — 누적 슬롯: 전 상대 발화가 현재 상대 evidence를 지우지 않는다."""
    from saju_engines.user_facts import merge_user_facts
    from saju_shared_types.conversation import ConversationState

    st = ConversationState(thread_id="t")
    st.user_facts = merge_user_facts(
        st, extract_user_facts("남자친구가 있어", turn=1), topic_reset=False
    )
    st.user_facts = merge_user_facts(
        st, extract_user_facts("별거 중이야", turn=2), topic_reset=False
    )
    quotes = [f.quote for f in st.user_facts if f.key == "relationship_status"]
    assert any("남자친구" in q for q in quotes)  # 현재 상대 사실 보존
    assert any("별거" in q for q in quotes)


def test_multi_clause_multi_target_fail_closed() -> None:
    """폐쇄 조건 ④ — 복수 대상 서술 발화는 자동 저장 금지 + 사유 계측."""
    for text in (
        "남편과는 별거 중이고 전 남자친구와는 연락하지 않아",
        "지금 만나는 사람은 있지만 전 남자친구와도 가끔 연락해",
    ):
        d = _decide(text)
        assert not d.update and d.reason == "ambiguous_multiple_targets", text


def test_correction_single_target_not_multi() -> None:
    """정정 발화("있는 게 아니라 썸")는 같은 대상 재서술 — 다중 대상 오탐 금지."""
    d = _decide("남자친구가 있는 게 아니라 썸 타는 사람이야")
    assert d.update and d.reason == "ok"


def test_vague_planned_does_not_create_state() -> None:
    """'언젠가 결혼할 예정' — planned 신뢰도 낮음: 신규 상태(COMMITMENT 함의) 생성 금지."""
    store = RelationshipStateStore()
    d = _decide("남자친구와 언젠가 결혼할 예정이야")
    assert d.reason == "planned_only" and d.planned_may_create_state is False
    apply_state_update(store, d, turn=1, target_id="t1")
    assert "t1" not in store.target_states  # 신규 생성 없음
    # 기존 상태가 있으면 planned만 붙는다.
    apply_state_update(store, _decide("남자친구가 있어"), turn=2, target_id="t1")
    apply_state_update(store, d, turn=3, target_id="t1")
    st = store.target_states["t1"]
    assert st.stage is RelationshipStage.DATING
    assert st.planned_stage is RelationshipStage.MARRIED


def test_question_form_marriage_is_hypothetical() -> None:
    """'내년에 결혼할 수 있을까?' — 질문형 미래: 상태 변경 금지."""
    d = _decide("내년에 결혼할 수 있을까?")
    assert not d.update
    assert d.reason in ("hypothetical", "no_signal")
    assert d.planned_stage is None


def test_overview_distinguishes_partner_kinds() -> None:
    """폐쇄 보완 §5 — 별거 배우자·활동 연애 상대·연락 대상을 구분 파생한다."""
    store = RelationshipStateStore()
    apply_state_update(store, _decide("남편과 별거 중이야", target="sp"), turn=1)
    apply_state_update(
        store, _decide("전 남자친구와 다시 연락 중이야", target="ex"), turn=2
    )
    ov = derive_relationship_overview("기혼", store)
    assert ov.has_legal_spouse is True
    assert ov.has_separated_spouse is True
    assert ov.has_active_romantic_partner is False  # 별거 배우자는 활동 상대 아님
    assert ov.has_current_contact_target is True    # 전 연인 연락 중
    assert ov.active_target_count == 2


# ── P1-0: user_facts retention (관계 evidence의 전체 원장 잠식 방지) ──────────────


def test_relationship_facts_do_not_evict_other_facts() -> None:
    """관계 사실 다수 + 비관계 사실(이사·계약·일정) 공존 시 비관계 사실 보존."""
    from saju_engines.user_facts import merge_user_facts
    from saju_shared_types.conversation import ConversationState

    st = ConversationState(thread_id="t")
    base = (
        "이미 계약도 끝냈고. 잔금만 남았어. 9월 30일에 이사가 예정되어 있어."
    )
    st.user_facts = merge_user_facts(st, extract_user_facts(base, 1), topic_reset=False)
    non_rel_before = {(f.key, f.quote) for f in st.user_facts}
    assert non_rel_before  # 비관계 사실 존재 전제
    # 관계 사실을 다수 턴에 걸쳐 누적(전 연인·별거·연애·썸 …).
    rel_texts = [
        "남자친구가 있어", "남편과 별거 중이야", "썸 타는 사람이 생겼어",
        "전 남자친구와 연락 중이야", "약혼했어", "연애 중이야",
    ]
    for i, txt in enumerate(rel_texts, start=2):
        st.user_facts = merge_user_facts(
            st, extract_user_facts(txt, i), topic_reset=False
        )
    kept = {(f.key, f.quote) for f in st.user_facts}
    # 비관계 사실이 cap 때문에 사라지지 않는다.
    assert non_rel_before <= kept
    # 관계 사실은 sub-cap(4) 이내로 최근분만 유지 — 최소 evidence는 보존.
    rel_kept = [f for f in st.user_facts if f.key == "relationship_status"]
    assert 1 <= len(rel_kept) <= 4
    assert any("연애" in f.quote or "약혼" in f.quote for f in rel_kept)  # 최신 유지

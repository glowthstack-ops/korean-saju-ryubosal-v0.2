"""REL shadow 라이브 배선 검증 — P0-B4 (RELATIONSHIP_EVENT_SYSTEM 부록 C-4·C-7).

역할 매핑·생성 금지 규칙·하드 게이트·idempotency·오류 격리·계측을 고정한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_api.services.relationship_shadow import (
    REL_LIVE_CONTEXT_EXPOSE_ENABLED,
    build_relationship_shadow_contexts,
    strip_live_relationship_candidates,
)
from saju_shared_types.conversation import ConversationState


def _build(question: str, state: ConversationState | None = None, *,
           turn: int = 1, profile: str | None = None, attached: str | None = None,
           attached_rel: str | None = None):
    return build_relationship_shadow_contexts(
        question=question, state=state, turn=turn,
        profile_relationship_status=profile,
        attached_partner_subject_id=attached, attached_relation_type=attached_rel,
    )


# ── 역할 매핑·생성 규칙 (C-7 표) ─────────────────────────────────────


def test_dating_utterance_creates_current_partner_context() -> None:
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("남자친구가 있어", st)
    assert len(ctxs) == 1
    c = ctxs[0]
    assert c.target_role == "current_partner"
    assert c.target_id.startswith("relstate-")     # opaque — 역할어·원문 아님
    assert c.financial_tie is None and c.shared_responsibility is None  # 자동 추론 금지
    assert tel.context_created_count == 1 and "utterance" in tel.context_sources


def test_separated_spouse_keeps_target_with_status() -> None:
    """별거 배우자 — 대상 제거 금지, spouse+separated, contact 추론 금지."""
    st = ConversationState(thread_id="t")
    ctxs, _ = _build("남편과 별거 중이야", st)
    assert len(ctxs) == 1
    c = ctxs[0]
    assert c.target_role == "spouse"
    assert c.relationship_status == "separated"
    assert c.current_contact_state is None  # 별거라고 denied 추론 금지


def test_ex_partner_contact_not_mapped_to_current_partner() -> None:
    """전 연인 role은 위험 사전에 없음 — current_partner 대체 금지, drop 기록."""
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("전 남자친구와 다시 연락 중이야", st)
    assert ctxs == []
    assert "unsupported_role" in tel.drop_reasons


def test_generic_question_no_specific_target() -> None:
    """일반 연애운 질문 — 특정 상대 컨텍스트 생성 0건."""
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("올해 연애운 어때?", st)
    assert ctxs == []
    assert tel.context_created_count == 0


def test_third_party_no_context() -> None:
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("친구 남자친구 사주 좀 봐줘", st)
    assert ctxs == [] and "third_party" in tel.drop_reasons


def test_ambiguous_multiple_targets_no_context_and_no_state_wipe() -> None:
    """다중 대상 발화 — 생성 금지 + 기존 상태 초기화 금지(fail-closed=미write)."""
    st = ConversationState(thread_id="t")
    _build("남자친구가 있어", st, turn=1)
    before = dict(st.relationship_states.target_states)
    ctxs, tel = _build("남편과는 별거 중이고 전 남자친구와는 연락하지 않아", st, turn=2)
    assert tel.target_ambiguous and "multiple_targets" in tel.drop_reasons
    # 기존 발화 상태는 그대로(초기화·unknown 덮어쓰기 금지). 컨텍스트는 기존 상태로 생성됨.
    assert st.relationship_states.target_states == before
    assert [c.target_role for c in ctxs] == ["current_partner"]


def test_profile_slot_not_merged_with_registered() -> None:
    """프로필 기반 익명 slot — 전용 네임스페이스, 발화 상태와 별도 target."""
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("올해 운세 봐줘", st, profile="married")
    assert len(ctxs) == 1
    assert ctxs[0].target_role == "spouse"
    assert ctxs[0].target_id.startswith("profile-role:")
    assert "profile" in tel.context_sources


def test_profile_slot_suppressed_when_utterance_state_exists() -> None:
    """발화로 배우자 상태가 이미 있으면 프로필 slot 중복 생성 안 함."""
    st = ConversationState(thread_id="t")
    _build("남편과 별거 중이야", st, turn=1)
    ctxs, _ = _build("올해 운세 봐줘", st, turn=2, profile="married")
    roles = [c.target_role for c in ctxs]
    assert roles.count("spouse") == 1
    assert ctxs[0].target_id.startswith("relstate-")  # 발화 상태가 우선


def test_attached_partner_is_question_target() -> None:
    st = ConversationState(thread_id="t")
    ctxs, tel = _build("우리 궁합 어때?", st, attached="subj-9", attached_rel="romance")
    assert len(ctxs) == 1
    assert ctxs[0].target_role == "current_partner"
    assert ctxs[0].is_question_target is True
    assert ctxs[0].target_id == "attached:subj-9"


# ── 하드 게이트 (불변식 1) ───────────────────────────────────────────


def test_hard_gate_constant_off() -> None:
    assert REL_LIVE_CONTEXT_EXPOSE_ENABLED is False  # P5 승인 전 True 전환 금지


def test_strip_live_candidates_all_namespaces() -> None:
    """live 네임스페이스(relstate-/profile-role:/attached:) 후보는 노출 경로에서 제거,
    비관계·QA 유래 후보는 보존."""
    cands = [
        SimpleNamespace(risk_id="REL_PARTNER_READJUST", relationship_target_id="relstate-1"),
        SimpleNamespace(risk_id="REL_EMOTIONAL_CLASH",
                        relationship_target_id="profile-role:relstate-2"),
        SimpleNamespace(risk_id="REL_DISTANCE_PRESSURE", relationship_target_id="attached:subj-9"),
        SimpleNamespace(risk_id="MOB_TRAFFIC", relationship_target_id=None),
        SimpleNamespace(risk_id="REL_FAMILY_BURDEN", relationship_target_id="qa-target-1"),
    ]
    kept, removed = strip_live_relationship_candidates(cands)
    assert removed == 3
    assert [c.risk_id for c in kept] == ["MOB_TRAFFIC", "REL_FAMILY_BURDEN"]


# ── idempotency (불변식 2) ───────────────────────────────────────────


def test_same_turn_reprocess_no_duplicate_write() -> None:
    st = ConversationState(thread_id="t")
    _build("남자친구가 있어", st, turn=5)
    snap = st.relationship_states.model_dump()
    ctxs2, tel2 = _build("남자친구가 있어", st, turn=5)  # 동일 turn 재처리(재시도)
    assert tel2.retry_skipped is True
    assert st.relationship_states.model_dump() == snap  # 중복 write 0
    assert len(ctxs2) == 1  # 컨텍스트는 결정론 재생성(중복 아님)


def test_new_turn_same_text_applies() -> None:
    st = ConversationState(thread_id="t")
    _build("남자친구가 있어", st, turn=5)
    _, tel = _build("남자친구가 있어", st, turn=6)
    assert tel.retry_skipped is False


# ── 오류 격리·계측 (C-4) ─────────────────────────────────────────────


def test_resolver_error_isolated(monkeypatch) -> None:
    """내부 강제 예외 → 빈 컨텍스트 + resolver_error 계측, 예외 전파 없음."""
    import saju_api.services.relationship_shadow as mod

    def boom(_text):
        raise RuntimeError("forced")

    monkeypatch.setattr(mod, "parse_relationship_utterance", boom)
    ctxs, tel = _build("남자친구가 있어", ConversationState(thread_id="t"))
    assert ctxs == [] and "resolver_error" in tel.drop_reasons


def test_telemetry_has_no_raw_text() -> None:
    """계측에 발화 원문·별명 미포함(enum·count·bool·opaque 네임스페이스만)."""
    st = ConversationState(thread_id="t")
    _, tel = _build("남자친구가 있어", st)
    dumped = repr(tel.__dict__)
    assert "남자친구" not in dumped

"""REL shadow 라이브 배선 — P0-B4 (RELATIONSHIP_EVENT_SYSTEM 부록 C-4·C-7).

발화·프로필·첨부 상대를 해소해 위험 엔진 shadow 전용 `RelationshipContext`를 만든다.
실행 순서(확정): parse → 대상 resolve → temporal/제3자 판정 → decide → apply(이번 turn
반영) → **갱신된 상태로** 컨텍스트 생성 → shadow 전달.

최우선 불변식 2건(2026-07-24 승인):
1. **하드 게이트** — 본 모듈이 만든 live 컨텍스트에서 나온 REL 후보는 위험 모드
   (off/shadow/canary/expose)와 무관하게 **P5 전까지 LLM에 노출되지 않는다**.
   `REL_LIVE_CONTEXT_EXPOSE_ENABLED=False` + 후보 필터(`strip_live_relationship_candidates`)
   — live 컨텍스트의 target_id는 전용 네임스페이스 접두사를 가지므로 후보의
   `relationship_target_id`로 결정적으로 식별·차단한다.
2. **idempotency** — 동일 turn 재처리 시 state/facts/context 중복 0
   (store.last_applied_signature).

역할 매핑(C-7): MARRIED→spouse(별거는 relationship_status="separated" — contact 추론
금지) / DATING·COMMITMENT·FORMALIZATION→current_partner / CONTACT→dating_partner /
전 연인(ex_partner)은 위험 role 사전에 없음 → 컨텍스트 미생성+drop 기록(current_partner
대체 금지). generic 질문·대상 불명·제3자 → 생성 금지. financial_tie·shared_responsibility
는 항상 None(역할에서 자동 추론 금지 — UNKNOWN≠CONFIRMED).

오류 격리: 어떤 단계가 실패해도 본 응답을 막지 않는다 — 빈 목록 + resolver_error 계측.
계측은 enum·count만(PII·원문·자유 문자열 금지).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field

from saju_engines.relationship_state_resolver import (
    apply_state_update,
    decide_state_update,
    parse_relationship_utterance,
)
from saju_engines.risk_engine import RelationshipContext
from saju_shared_types.conversation import ConversationState
from saju_shared_types.relationship_event import RelationshipCondition, RelationshipStage
from saju_shared_types.relationship_state import (
    RelationshipStateStore,
    TemporalStatus,
    derive_relationship_overview,
)
from saju_shared_types.risk_engine import ExposureStatus

logger = logging.getLogger(__name__)

# ── 관계 기능 beta 노출 마스터 플래그(테스터 피드백용 — 2026-07-24 사용자 승인) ──────
# env SAJU_RELATIONSHIP_BETA_EXPOSE=true 로 켠다(기본 off). 관계 **벡터 인사이트**
# (슬라이스1 채팅·슬라이스2 리포트)만 이 플래그로 노출한다. off면 shadow 복귀 →
# 기존 출력 byte-identical. 캘리브레이션 사람 감수(P2-3) 전이라 beta·잠정 라벨로만
# 노출하며, 미평가 4축·단정·승부/당첨 단정 하드 가드는 유지한다.
RELATIONSHIP_BETA_EXPOSE = os.getenv(
    "SAJU_RELATIONSHIP_BETA_EXPOSE", "false").strip().lower() in ("1", "true", "yes")

# ── 하드 게이트(불변식 1) — 관계 위험 라이브 후보 노출 차단(P5) ──────────────────────
# 슬라이스3(관계 위험 노출)은 위험 노출 파이프라인(RISK_ENGINE_MODE=expose +
# reviewed manifest + 유효 HMAC + adapter)이 별도로 fail-closed라, beta 플래그만으로는
# 실제 노출되지 않는다. 위험 도메인 출력(사고수·갈등·흉사)은 정책 감수를 거쳐야 하므로
# beta 인사이트 플래그와 **연동하지 않는다**(잠재 누출 방지). 위험 노출은 위험 파이프라인
# 감수 완료 후 별도로 켠다. 기본 False 유지.
REL_LIVE_CONTEXT_EXPOSE_ENABLED = False

# ── dev 전용 관계 위험 beta 우회(2026-07-24 사용자 승인 — 테스터 피드백용) ────────────
# env SAJU_RELATIONSHIP_RISK_BETA_EXPOSE=true 로 켠다(기본 off). **production 위험 노출
# 파이프라인을 건드리지 않는 별도 dev 경로**다 — RISK_ENGINE_MODE·expose_pipeline.reviewed·
# HMAC·adapter 어느 것도 바꾸지 않으며 reviewed 위조도 없다. 위 P5 하드 게이트
# (REL_LIVE_CONTEXT_EXPOSE_ENABLED)와 실 후보 스트림(strip_live_relationship_candidates)은
# 그대로 유지되고, 이 플래그는 **live-derived 후보를 별도로 골라 beta 블록으로만** 보여준다
# (슬라이스1·2 벡터 블록과 동일한 sidecar 패턴). calibration 사람 감수(P2-3)·증거 계약
# (P3/P5) 미완이므로 노출은 도메인·밴드 수준으로 제한하고 단정·미평가 4축·구체 사건은 금지,
# beta·감수 대상 라벨을 강제한다. dev에서 데이터가 실제로 있으려면 RISK_ENGINE_MODE=shadow
# (계산만·주입 0)가 함께 필요하다 — expose 모드는 계속 off.
RELATIONSHIP_RISK_BETA_EXPOSE = os.getenv(
    "SAJU_RELATIONSHIP_RISK_BETA_EXPOSE", "false").strip().lower() in ("1", "true", "yes")

# live 컨텍스트 전용 target 네임스페이스 — 후보 차단 필터의 결정 기준.
_LIVE_TARGET_PREFIXES = ("relstate-", "profile-role:", "attached:")

# drop_reason enum(계측 고정 — 자유 문자열 금지)
_DROP_REASONS = frozenset({
    "target_ambiguous", "multiple_targets", "third_party", "past_only", "hypothetical",
    "planned_only", "unsupported_role", "missing_target", "state_conflict",
    "resolver_error", "no_signal", "generic_question",
})

# stage → 위험 role(사전 어휘 _RISK_RELATIONSHIP_ROLES 내 값만).
_STAGE_TO_RISK_ROLE: dict[RelationshipStage, str] = {
    RelationshipStage.MARRIED: "spouse",
    RelationshipStage.FORMALIZATION: "current_partner",
    RelationshipStage.COMMITMENT: "current_partner",
    RelationshipStage.DATING: "current_partner",
    RelationshipStage.CONTACT: "dating_partner",
}


@dataclass
class RelationshipShadowTelemetry:
    """계측 10+2종(부록 C-4) — enum·count 전용, PII 없음."""

    context_attempted: bool = False
    context_created_count: int = 0
    context_sources: list[str] = field(default_factory=list)   # utterance|profile|attached
    target_resolved: bool = False
    target_ambiguous: bool = False
    temporal_status: str = ""
    profile_fact_conflict: bool = False
    exposure_statuses: list[str] = field(default_factory=list)
    risk_candidate_count: int = 0          # take_risk_shadow 후 chat 측에서 기록
    risk_blocked_or_suppressed_count: int = 0
    context_deduplicated_count: int = 0
    drop_reasons: list[str] = field(default_factory=list)      # _DROP_REASONS 값만
    retry_skipped: bool = False            # 동일 turn 재처리 감지(고유/재시도 구분)

    def add_drop(self, reason: str) -> None:
        assert reason in _DROP_REASONS, reason
        self.drop_reasons.append(reason)

    def emit(self) -> None:
        """PII 없는 1줄 로그(shadow 관측 — 출력·토큰 무관)."""
        logger.info(
            "relationship_shadow attempted=%s created=%d sources=%s resolved=%s "
            "ambiguous=%s temporal=%s conflict=%s exposures=%s rel_candidates=%d "
            "blocked=%d dedup=%d drops=%s retry_skipped=%s",
            self.context_attempted, self.context_created_count, self.context_sources,
            self.target_resolved, self.target_ambiguous, self.temporal_status,
            self.profile_fact_conflict, self.exposure_statuses,
            self.risk_candidate_count, self.risk_blocked_or_suppressed_count,
            self.context_deduplicated_count, self.drop_reasons, self.retry_skipped,
        )


def _opaque_target_id(store: RelationshipStateStore, slot_key: str) -> str:
    """대화 로컬 opaque ID — 같은 슬롯은 안정적으로 같은 ID, 원문·역할어 비저장."""
    existing = store.target_registry.get(slot_key)
    if existing:
        return existing
    store.target_seq += 1
    tid = f"relstate-{store.target_seq}"
    store.target_registry[slot_key] = tid
    return tid


def _utterance_signature(turn: int, text: str) -> str:
    return hashlib.sha256(f"{turn}:{text.strip()}".encode()).hexdigest()[:16]


def relationship_observation_id(thread_id: str, turn: int, text: str) -> str:
    """동일 사용자 입력의 안정 ID(P1-6 §5-2) — scope-local digest, 원문 미노출.

    재시도 dedupe 기준. 사용자 간 전역 추적 불가(thread scope 포함 해시)."""
    return hashlib.sha256(
        f"{thread_id}:{turn}:{text.strip()}".encode()).hexdigest()[:16]


def relationship_vector_run_id(observation_id: str) -> str:
    """계산 런 ID = observation + 벡터 schema/calibration 버전(P1-6 §5-2).

    계수 변경 후 같은 turn 재감사는 별도 run으로 관측되고, 동일 버전 재시도는
    dedupe된다."""
    from saju_engines.relationship_effect_vector import (
        RELATIONSHIP_CALIBRATION_VERSION,
        RELATIONSHIP_VECTOR_SCHEMA_VERSION,
    )
    return hashlib.sha256(
        f"{observation_id}:{RELATIONSHIP_VECTOR_SCHEMA_VERSION}:"
        f"{RELATIONSHIP_CALIBRATION_VERSION}".encode()).hexdigest()[:16]


def build_relationship_shadow_contexts(
    *,
    question: str,
    state: ConversationState | None,
    turn: int,
    profile_relationship_status: str | None = None,   # single|dating|married|divorced
    attached_partner_subject_id: str | None = None,
    attached_relation_type: str | None = None,        # spouse|romance 등(사용자 명시 첨부)
) -> tuple[list[RelationshipContext], RelationshipShadowTelemetry]:
    """관계 발화 해소→상태 반영→shadow 컨텍스트 생성(순서 고정, 오류 격리).

    Returns:
        (shadow 전용 컨텍스트 목록, 계측). 실패 시 ([], resolver_error 계측).
    """
    t = RelationshipShadowTelemetry(context_attempted=True)
    try:
        return _build_inner(
            question=question, state=state, turn=turn,
            profile_relationship_status=profile_relationship_status,
            attached_partner_subject_id=attached_partner_subject_id,
            attached_relation_type=attached_relation_type, t=t,
        )
    except Exception:  # noqa: BLE001 — shadow 실패가 본 응답을 막으면 안 된다(C-4)
        logger.exception("relationship_shadow 실패 — 본 응답 비차단")
        t.add_drop("resolver_error")
        return [], t


def _build_inner(
    *,
    question: str,
    state: ConversationState | None,
    turn: int,
    profile_relationship_status: str | None,
    attached_partner_subject_id: str | None,
    attached_relation_type: str | None,
    t: RelationshipShadowTelemetry,
) -> tuple[list[RelationshipContext], RelationshipShadowTelemetry]:
    store = state.relationship_states if state is not None else RelationshipStateStore()

    # 1) parse — 발화의 관계 신호(rules-first).
    parsed = parse_relationship_utterance(question)
    if parsed is not None:
        t.temporal_status = parsed.temporal_status.value

    # 2) 대상 resolve(발화 기반, 보수) — 역할 힌트가 있으면 대화 로컬 opaque 슬롯.
    #    등록 동반자·프로필과의 자동 병합 금지(별도 소스로 각각 생성 — dedup은 P5).
    target_id: str | None = None
    if parsed is not None and not parsed.third_party and not parsed.multiple_targets \
            and parsed.target_role_hint is not None:
        target_id = _opaque_target_id(store, f"self-reported:{parsed.target_role_hint}")
        t.target_resolved = True

    # 3~5) temporal/제3자 판정 + decide + apply(이번 turn 반영 — idempotent).
    decision = decide_state_update(parsed, target_id=target_id, turn=turn)
    if decision.reason in ("ambiguous_multiple_targets",):
        t.target_ambiguous = True
        t.add_drop("multiple_targets")
    elif decision.reason == "third_party":
        t.add_drop("third_party")
    elif decision.reason == "hypothetical":
        t.add_drop("hypothetical")
    elif decision.reason == "past":
        t.add_drop("past_only")
    elif decision.reason == "planned_only":
        t.add_drop("planned_only")
    elif decision.reason == "target_unresolved":
        t.add_drop("missing_target")

    sig = _utterance_signature(turn, question)
    if store.last_applied_signature == sig:
        t.retry_skipped = True  # 동일 turn 재처리 — 중복 write 금지(불변식 2)
    else:
        conflict = apply_state_update(
            store, decision, turn=turn, target_id=target_id,
            profile_marital_status=None,  # 프로필 원문은 게이트 값만 보유 — 충돌은 아래 개괄로
        )
        t.profile_fact_conflict = conflict
        if decision.update or decision.planned_stage or decision.marital_override:
            store.last_applied_signature = sig

    # 6) 갱신된(이번 turn 반영 후) 상태로 컨텍스트 생성.
    contexts: list[RelationshipContext] = []
    seen_targets: set[str] = set()

    # 6a) 발화 해소 상태 — CURRENT target별.
    for tid, st in store.target_states.items():
        if st.temporal_status is not TemporalStatus.CURRENT:
            continue
        role = _STAGE_TO_RISK_ROLE.get(st.stage)
        if role is None:
            # 전 연인(stage NONE·CONTACT 아님) 등 사전 role 없음 — current_partner 대체 금지.
            if st.target_role == "ex_partner" and st.stage is RelationshipStage.NONE:
                t.add_drop("unsupported_role")
            continue
        if st.target_role == "ex_partner":
            # 전 연인 연락 재개(CONTACT) — 위험 role 사전에 과거 상대 role 없음 → drop.
            t.add_drop("unsupported_role")
            continue
        separated = st.condition is RelationshipCondition.SEPARATED
        contexts.append(RelationshipContext(
            target_role=role,
            target_id=tid,
            exposure_status=ExposureStatus.CONFIRMED,  # 사용자 명시 발화로 확인된 관계
            financial_tie=None,             # 자동 추론 금지
            shared_responsibility=None,     # 자동 추론 금지
            relationship_status="separated" if separated else None,
            current_contact_state=st.contact_state,  # 별거라도 contact 추론 금지(실측만)
            live_state_derived=True,
        ))
        seen_targets.add(tid)
        t.context_sources.append("utterance")
        t.exposure_statuses.append(ExposureStatus.CONFIRMED.value)

    # 6b) 프로필 기반 익명 slot — 발화 컨텍스트와 자동 병합 금지(별도 opaque id).
    ov = derive_relationship_overview(None, store)
    if profile_relationship_status == "married" and not ov.has_legal_spouse:
        tid = _opaque_target_id(store, "profile-role:spouse")
        contexts.append(RelationshipContext(
            target_role="spouse", target_id=f"profile-role:{tid}",
            exposure_status=ExposureStatus.CONFIRMED,  # 프로필 명시 입력
            live_state_derived=True,
        ))
        t.context_sources.append("profile")
        t.exposure_statuses.append(ExposureStatus.CONFIRMED.value)
    elif profile_relationship_status == "dating" and not ov.has_active_romantic_partner:
        tid = _opaque_target_id(store, "profile-role:current-partner")
        contexts.append(RelationshipContext(
            target_role="current_partner", target_id=f"profile-role:{tid}",
            exposure_status=ExposureStatus.CONFIRMED,
            live_state_derived=True,
        ))
        t.context_sources.append("profile")
        t.exposure_statuses.append(ExposureStatus.CONFIRMED.value)

    # 6c) 첨부 상대(사용자가 직접 선택한 궁합 칩 — 명시 지정이라 병합 아님).
    if attached_partner_subject_id and attached_relation_type in ("spouse", "romance"):
        role = "spouse" if attached_relation_type == "spouse" else "current_partner"
        contexts.append(RelationshipContext(
            target_role=role, target_id=f"attached:{attached_partner_subject_id}",
            exposure_status=ExposureStatus.CONFIRMED,
            is_question_target=True,
            live_state_derived=True,
        ))
        t.context_sources.append("attached")
        t.exposure_statuses.append(ExposureStatus.CONFIRMED.value)

    # dedup 계측(같은 target_id 중복 생성 방지 — 소스 간 병합은 하지 않되 동일 id는 1건).
    unique: dict[str | None, RelationshipContext] = {}
    for c in contexts:
        if c.target_id in unique:
            t.context_deduplicated_count += 1
            continue
        unique[c.target_id] = c
    out = list(unique.values())
    t.context_created_count = len(out)
    if not out and parsed is None and profile_relationship_status in (None, "single",
                                                                      "divorced"):
        t.add_drop("generic_question")  # 특정 상대 컨텍스트 0 — 정상(생성 금지 규칙)
    return out, t


def strip_live_relationship_candidates(candidates: list) -> tuple[list, int]:
    """하드 게이트(불변식 1) — live 관계 컨텍스트에서 나온 REL 후보를 노출 경로에서 제거.

    위험 모드(off/shadow/canary/expose)와 무관하게 적용한다. live 컨텍스트의 target_id는
    전용 네임스페이스 접두사를 가지므로 후보의 relationship_target_id로 결정적 식별.
    반환: (필터된 목록, 제거 수). `REL_LIVE_CONTEXT_EXPOSE_ENABLED=True`(P5 승인)가
    되기 전에는 항상 활성이다.
    """
    if REL_LIVE_CONTEXT_EXPOSE_ENABLED:  # pragma: no cover — P5 승인 전 도달 불가
        return candidates, 0
    kept, removed = [], 0
    for c in candidates:
        tid = getattr(c, "relationship_target_id", None) or ""
        # provenance가 주 판단(흡수·대표 수렴 후에도 OR 전파로 보존), namespace는
        # 보조 fail-safe(flag 유실·복사 재구성 대비 이중 방어).
        if getattr(c, "live_relationship_context_derived", False) or any(
            tid.startswith(p) for p in _LIVE_TARGET_PREFIXES
        ):
            removed += 1
            continue
        kept.append(c)
    return kept, removed


def select_live_relationship_risk_candidates(candidates: list) -> list:
    """dev beta 우회 전용 — strip이 제거하는 live 관계 유래 후보만 골라 반환.

    `strip_live_relationship_candidates`의 반대(제거 대상) 집합이다. production 노출
    경로가 아니라 `RELATIONSHIP_RISK_BETA_EXPOSE` beta 블록에서만 소비하며, 실 후보
    스트림·P5 하드 게이트에는 영향을 주지 않는다(읽기 전용 선택). provenance 플래그가
    주 판단, target 네임스페이스가 보조 fail-safe(strip과 동일 식별 기준).
    """
    out = []
    for c in candidates:
        tid = getattr(c, "relationship_target_id", None) or ""
        if getattr(c, "live_relationship_context_derived", False) or any(
            tid.startswith(p) for p in _LIVE_TARGET_PREFIXES
        ):
            out.append(c)
    return out

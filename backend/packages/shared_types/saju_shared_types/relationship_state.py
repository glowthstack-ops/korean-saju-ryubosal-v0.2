"""관계 상태 저장 구조 — P0-B3 (RELATIONSHIP_EVENT_SYSTEM 부록 C-3).

소유권 분리(2026-07-24 승인):
- `user_facts` = 사용자 **원문 사실·정정 이력의 evidence ledger**(quote 보존).
- `ConversationState.relationship_states`(본 모듈 `RelationshipStateStore`) = 원문·프로필을
  해소한 **현재 운영 상태의 SSOT**(target_id별).
- 전역 연애 여부(has_current_partner 등)는 **권위값으로 저장하지 않고 파생**한다
  (`derive_relationship_overview`) — 다중 상대·별거·재회를 단순 bool로 뭉개지 않기 위함.
  전역 권위값은 사용자가 명시로 정정한 혼인 상태 override뿐.

target_id 규칙(부록 C-3/C-4): 등록 동반자=subject_id, inline 상대=대화 로컬 opaque ID.
실명·별명 원문, "남자친구"류 역할어 자체를 key로 쓰지 않는다(현재/전 상대가 같은 키에
덮어써지는 것 금지 — target_role은 속성). 계정 간 추적 가능한 전역 해시 금지.

직렬화 안전(부록 C-3 §10): conversation_threads.state는 JSONB 단일 컬럼 +
pydantic 기본 extra='ignore' — 신규 필드는 default로 과거 payload 역직렬화 안전
(물리 마이그레이션 불필요, 실확인 2026-07-24). `schema_version`으로 읽기 마이그레이션
여지를 남긴다. 구버전 worker가 신규 필드를 드롭 후 재저장할 수 있음(단일 환경이라
위험 낮음 — 배포 정책 메모).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .relationship_event import RelationshipCondition, RelationshipStage


class TemporalStatus(StrEnum):
    """발화 시간성 — 현재 상태 갱신 가능 여부를 가른다(C-3)."""

    CURRENT = "current"            # 갱신 가능
    PAST = "past"                  # 현재 갱신 금지(이력)
    PLANNED = "planned"            # 계획 상태만(planned_stage) — 현 stage 승격 금지
    HYPOTHETICAL = "hypothetical"  # 갱신 금지


class RelationshipStateSource(StrEnum):
    """상태 결정 출처(우선순위 근거 기록)."""

    QUESTION_EXPLICIT = "question_explicit"    # 현재 질문의 명시 사실
    CONVERSATION_FACT = "conversation_fact"    # 최근 대화 confirmed 현재형
    PROFILE = "profile"                        # 2단계 프로필
    UNKNOWN = "unknown"


class ResolvedRelationshipState(BaseModel):
    """target 1명에 대한 해소된 현재 운영 상태."""

    target_id: str
    target_role: str | None = None      # partner / ex_partner / spouse …(속성 — key 아님)

    stage: RelationshipStage = RelationshipStage.NONE
    condition: RelationshipCondition | None = None
    contact_state: str | None = None    # in_contact / no_contact / None(미상)
    # PLANNED 발화 보존 — 현 stage를 승격시키지 않는다("결혼할 예정"≠MARRIED).
    planned_stage: RelationshipStage | None = None

    temporal_status: TemporalStatus = TemporalStatus.CURRENT
    source: RelationshipStateSource = RelationshipStateSource.UNKNOWN
    source_turn: int | None = None

    profile_conflict: bool = False      # 프로필과 어긋남(텔레메트리 근거)
    confidence: str = "medium"          # high / medium / low


class RelationshipStateStore(BaseModel):
    """대화 스레드의 관계 상태 SSOT(ConversationState에 내장)."""

    schema_version: str = "1"

    # 프로필 혼인 상태를 사용자가 명시로 정정한 경우에만 저장(프로필 자동 수정 금지 —
    # 프로필 영구 변경은 별도 정책 소관, P0-B3 범위 밖).
    marital_status_override: str | None = None
    marital_status_source: RelationshipStateSource | None = None

    target_states: dict[str, ResolvedRelationshipState] = Field(default_factory=dict)
    last_resolved_turn: int | None = None


# 파생 시 "현재 상대 있음"으로 세는 단계(NONE·AWARENESS·CONTACT 제외).
_PARTNERED_STAGES = frozenset({
    RelationshipStage.DATING, RelationshipStage.COMMITMENT,
    RelationshipStage.FORMALIZATION, RelationshipStage.MARRIED,
})


class RelationshipOverview(BaseModel):
    """읽기 시 파생되는 전역 개괄 — 저장 금지(권위값 아님).

    단일 has_partner 압축 금지(P0-B3 폐쇄 보완 §5) — 법적 배우자·활동 중인 연애 상대·
    별거 배우자·연락 중인 대상을 구분해야 B4가 위험 컨텍스트 role을 오귀속하지 않는다.
    """

    effective_marital_status: str | None = None   # override > profile
    marital_from_override: bool = False
    has_current_partner: bool = False             # 하위 호환 파생값(세분 값 우선 사용)
    has_legal_spouse: bool = False                # MARRIED target 존재
    has_active_romantic_partner: bool = False     # 별거 아닌 연애·혼인 상대
    has_separated_spouse: bool = False            # MARRIED + SEPARATED(별거)
    has_current_contact_target: bool = False      # in_contact 대상(전 연인 연락 포함)
    active_target_count: int = 0
    current_partner_target_ids: list[str] = Field(default_factory=list)


def derive_relationship_overview(
    profile_marital_status: str | None,
    store: RelationshipStateStore,
) -> RelationshipOverview:
    """전역 개괄 파생 — target별 상태·override에서 읽기 시 계산(중복 권위값 저장 금지).

    별거(MARRIED+SEPARATED)는 상대가 존재하므로 has_current_partner=True로 세되,
    has_active_romantic_partner에서는 제외한다(위험 role 구분 근거). 이별(stage=NONE)은
    자연히 제외된다.
    """
    current = {
        tid: st for tid, st in store.target_states.items()
        if st.temporal_status is TemporalStatus.CURRENT
    }
    partners = [t for t, st in current.items() if st.stage in _PARTNERED_STAGES]
    separated_spouse = any(
        st.stage is RelationshipStage.MARRIED
        and st.condition is RelationshipCondition.SEPARATED
        for st in current.values()
    )
    active_romantic = any(
        st.stage in _PARTNERED_STAGES
        and not (
            st.stage is RelationshipStage.MARRIED
            and st.condition is RelationshipCondition.SEPARATED
        )
        for st in current.values()
    )
    contact_targets = [
        t for t, st in current.items() if st.contact_state == "in_contact"
    ]
    active = sorted(set(partners) | set(contact_targets))
    return RelationshipOverview(
        effective_marital_status=store.marital_status_override or profile_marital_status,
        marital_from_override=store.marital_status_override is not None,
        has_current_partner=bool(partners),
        has_legal_spouse=any(
            st.stage is RelationshipStage.MARRIED for st in current.values()
        ),
        has_active_romantic_partner=active_romantic,
        has_separated_spouse=separated_spouse,
        has_current_contact_target=bool(contact_targets),
        active_target_count=len(active),
        current_partner_target_ids=sorted(partners),
    )

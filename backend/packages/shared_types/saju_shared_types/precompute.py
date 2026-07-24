"""사전계산(Precompute Store) schemas (v2.2 Phase 2.5, docs/09 3장).

`LuckComposite`는 (subject_id, level, period_key)당 1레코드로 저장되는 다운스트림 전체의
단일 참조원(SSOT)이다. 운의 복합 조합·작용은 여기서 가져오며, 요청 시점 즉석 재계산이나
LLM 조합 판단은 금지된다(절대 원칙 9).

natal 레코드의 ganji는 일주(日柱)를 대표값으로 둔다 — 문서에 natal 레벨 ganji 정의가
없어 채택한 해석(검수 대상). 원국 4주 전체는 interactions의 participants로 표현된다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CompositeLevel(StrEnum):
    """사전계산 레벨 (docs/09 — natal 포함 5단계)."""

    NATAL = "natal"
    DAEWOON = "daewoon"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class InteractionKind(StrEnum):
    """상호작용 종류 (docs/09 3장 InteractionHit.kind — 전체 12종)."""

    STEM_COMBINE = "stem_combine"
    STEM_CLASH = "stem_clash"
    BRANCH_SIX_COMBINE = "branch_six_combine"
    BRANCH_THREE_COMBINE = "branch_three_combine"
    BRANCH_DIRECTIONAL = "branch_directional"
    BRANCH_CLASH = "branch_clash"
    BRANCH_PUNISH = "branch_punish"
    BRANCH_BREAK = "branch_break"
    BRANCH_HARM = "branch_harm"
    WONJIN = "wonjin"
    SELF_PUNISH = "self_punish"
    STRUCTURE = "structure"


class InteractionSource(StrEnum):
    """참여 글자의 소스 (docs/09 3장 participants.source — 8종)."""

    NATAL_YEAR = "natal_year"
    NATAL_MONTH = "natal_month"
    NATAL_DAY = "natal_day"
    NATAL_HOUR = "natal_hour"
    DAEWOON = "daewoon"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class InteractionParticipant(BaseModel):
    """상호작용 참여 글자 1개 — 소스(원국 자리/운 레벨) + 글자(한자)."""

    source: InteractionSource
    ganji: str  # 참여 글자(천간 또는 지지 1자)


class InteractionHit(BaseModel):
    """상호작용 탐지 1건 (docs/09 3장 InteractionHit).

    partial은 반합(삼합/방합 2자)·부분형(삼형 2자) 여부. royal_included는 삼합 반합의
    왕지 포함 플래그(docs/09 2-2 — 왕지 포함 반합이 더 유효하다는 통설 반영용 정보).
    """

    relation_id: str  # 'rel_甲己合' — relations.json 키
    kind: InteractionKind
    participants: list[InteractionParticipant] = Field(min_length=1)
    partial: bool = False
    royal_included: bool | None = None  # 삼합/방합 반합에서만 의미
    mode_candidates: list[str] = Field(default_factory=list)
    base_weight: float = 0.0


class DomainSignal(BaseModel):
    """Topic Builder가 소비하는 최소 신호 단위 (docs/09 3장)."""

    domain: str
    event_key: str | None = None
    weight: float  # favorability 보정 완료 가중치
    source_interaction: str  # relationId 역추적용
    # B1-a(RELATIONSHIP_EVENT_SYSTEM 부록 B) — legacy 정규화 provenance.
    # 저장 키 alias(family_change→relationship_change)는 소비 의미 동일을 뜻하지
    # 않으므로 원본 키·taxonomy 세대를 보존한다(M02 호환 소비 등). canonical 저장분은 빈 값.
    source_event_key: str | None = None
    source_taxonomy_version: str = ""  # "legacy" | ""(canonical)


class CompositeGanji(BaseModel):
    """레벨 대표 간지."""

    stem: str
    branch: str


class ParentContext(BaseModel):
    """상위 레벨 간지 — LLM 입력 시 함께 전달(LLM은 간지 계산 불가, docs/09 3장)."""

    daewoon: str | None = None
    year: str | None = None
    month: str | None = None


class TenGodPair(BaseModel):
    """일간 기준 십성 (천간/지지 본기)."""

    stem: str
    branch_main: str


class LuckComposite(BaseModel):
    """(subject_id, level, period_key)당 1레코드 — 사전계산 저장 단위 (docs/09 3장)."""

    subject_id: str
    level: CompositeLevel
    period_key: str  # 'natal' | 'DW:壬辰' | '2026' | '2026-06' | '2026-06-10'
    ganji: CompositeGanji
    parent_context: ParentContext = Field(default_factory=ParentContext)
    ten_god: TenGodPair
    twelve_stage: str
    favorability: str  # 용신/희신/한신/기신/구신 (오행 기준 판정)
    interactions: list[InteractionHit] = Field(default_factory=list)
    structure_flags: list[str] = Field(default_factory=list)  # 공망활성/복음/반음/병존...
    shinsal_active: list[str] = Field(default_factory=list)
    domain_signals: list[DomainSignal] = Field(default_factory=list)
    dict_version: str
    computed_at: str  # ISO8601 — 저장 시각은 호출 측이 주입

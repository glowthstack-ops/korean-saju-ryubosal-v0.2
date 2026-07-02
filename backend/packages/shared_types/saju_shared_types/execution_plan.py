"""Execution Plan schema (v2.2 Phase 3 T3.3, docs/03 B4).

오케스트레이터가 intent를 받아 "어떤 엔진/모듈을 어떤 순서로 호출할지"를 확정한 산출물.
LLM이 "어떻게 계산할까"를 생각하지 않도록 queryType별 **고정 템플릿**으로 생성되며,
동일 질문 → 동일 ExecutionPlan(결정성)이 검수 기준이다(docs/07 Phase 3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .events import EventKey
from .intent import IntentJson

# 동반자 공동 풀이 모드(P1 계산/실행 분리 — 실행 전환은 P2). docs/03 SubjectMode를 '누구 사주를
# 넣을지' 관점으로 재정리한 shadow 축. 기존 intent.SubjectMode(실행용 enum)와 별개다.
CompanionReadMode = Literal[
    "self_only",            # 본인만
    "companion_only",       # 동반자 1명만("엄마 사주만")
    "pairwise",             # 본인 + 동반자 1명(궁합·함께)
    "compare_exclude_self",  # 동반자끼리 2명(본인 제외)
    "ranking",              # 동반자 3명 이상 다자 비교(본인 제외, P3c-2)
    "competition",          # 경쟁 비교 오버레이(relationship_context.mode 전용, P3c-1)
    "multi_with_self",      # 본인 + 동반자 2명 이상
    "unknown",
]


class EffectiveSubject(BaseModel):
    """P1 — 대상 조합 계산 결과 한 명(shadow, 실행 미전환). role/source로 P2 주입을 결정한다."""

    subject_id: str
    role: str  # 'self' | 'companion' | 'inline_temp'
    label: str
    relation_to_user: str | None = None
    matched_alias: str | None = None  # 발화에서 매칭된 별칭('와이프' 등, 있으면)
    source: str  # 'base' | 'text_alias' | 'text_inline' | 'chip'


class SubjectInjectionPolicy(BaseModel):
    """P1 — 케이스별 어느 대상 사주를 LLM 입력에 넣을지 자동 산출(실행은 P2에서 켠다).

    execution_enabled=False가 핵심 — P1은 계산·노출만 하고, P2가 대상별 ChartAnalysis를
    준비한 뒤 이 정책을 소비해 subject_blocks 주입/실행 분기를 켠다.
    """

    mode: CompanionReadMode = "self_only"
    primary_subject_id: str | None = None  # 서술 기준(보통 본인, companion_only면 그 동반자)
    target_subject_ids: list[str] = Field(default_factory=list)  # 실제 명식 주입 대상
    companion_subject_ids: list[str] = Field(default_factory=list)
    requires_companion_chart: bool = False
    requires_relationship_context: bool = False
    execution_enabled: bool = False  # P1 shadow — P2에서 True 전환
    reason: str = ""


class EngineCall(BaseModel):
    """호출할 엔진/모듈 한 단계(순서 보장)."""

    engine: str  # 'event_scoring' | 'timeline' | 'topic:M07' | 'llm' 등
    params: dict = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """실행 계획 (docs/03 B4 ExecutionPlan)."""

    intent: IntentJson
    event_type: str  # 'progress' | 'instant' | 'hybrid' | 'none'
    engine_calls: list[EngineCall] = Field(default_factory=list)
    dictionary_scope: list[str] = Field(default_factory=list)  # 로드할 사전(분할 로드)
    graph_scope: list[EventKey] = Field(default_factory=list)  # Graph RAG 검색 범위
    per_subject: bool = False  # 다중 대상이면 대상별 호출 후 집계
    # Q11~Q14 비분석 라우트: 엔진 미호출 사유/정책 (docs/03 B4 하단 4종).
    policy_route: str | None = None
    # P1(계산/실행 분리) — 대상 조합 shadow 메타. per_subject 실행 분기와 독립이며 P1에서는
    # 계산·노출만 한다(subject_injection.execution_enabled=False). P2가 소비해 실행을 켠다.
    effective_subjects: list[EffectiveSubject] = Field(default_factory=list)
    companion_read_mode: CompanionReadMode = "self_only"
    subject_injection: SubjectInjectionPolicy | None = None

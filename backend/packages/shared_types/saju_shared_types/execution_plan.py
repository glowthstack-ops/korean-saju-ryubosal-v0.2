"""Execution Plan schema (v2.2 Phase 3 T3.3, docs/03 B4).

오케스트레이터가 intent를 받아 "어떤 엔진/모듈을 어떤 순서로 호출할지"를 확정한 산출물.
LLM이 "어떻게 계산할까"를 생각하지 않도록 queryType별 **고정 템플릿**으로 생성되며,
동일 질문 → 동일 ExecutionPlan(결정성)이 검수 기준이다(docs/07 Phase 3).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventKey
from .intent import IntentJson


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

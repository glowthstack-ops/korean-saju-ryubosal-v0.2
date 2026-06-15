"""풀이 상품(보고서) schemas (v2.2 Phase 9, docs/10 — 전체 규격).

보고서 = "대화형 파이프라인을 섹션 수만큼 정해진 순서로 실행해 묶은 것" — 별도 분석
로직 금지. 목차·섹션 구성은 docs/10 3·4장 규격 그대로(임의 추가·삭제·병합·순서변경
금지, 변경은 사용자 승인 필요).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .intent import SubjectRef
from .profile import PersonaConfig


class ReportPeriod(BaseModel):
    """분석 기간."""

    start: str
    end: str


class ReportSpec(BaseModel):
    """보고서 사양 (docs/10 2장)."""

    product_code: Literal["RPT_FULL", "RPT_FOCUS", "RPT_YEAR"]
    subjects: list[SubjectRef]
    topic: str | None = None  # FOCUS 전용(Domain | 'compatibility' | 'relocation')
    period: ReportPeriod
    persona: PersonaConfig = Field(default_factory=PersonaConfig)  # 생성 시점 스냅샷
    language: Literal["ko"] = "ko"


class TargetChars(BaseModel):
    """섹션 분량 목표(자)."""

    min: int
    max: int


class ModuleCall(BaseModel):
    """Topic Builder 모듈 호출 1건."""

    module_id: str  # 'M01'~'M15' / 엔진 식별자
    params: dict = Field(default_factory=dict)


class SectionPlan(BaseModel):
    """섹션 계획 (docs/10 SectionPlan)."""

    section_id: str  # 'F-07' / 'C-03'
    title: str
    module_calls: list[ModuleCall] = Field(default_factory=list)
    target_chars: TargetChars
    depends_on: list[str] = Field(default_factory=list)


class SectionContext(BaseModel):
    """섹션 LLM 입력 + 정합성 검사 기준(코드가 확정한 사실 데이터)."""

    section_id: str
    subject_label: str = "본인"
    allowed_ganji: list[str] = Field(default_factory=list)  # calendarContext 간지
    allowed_scores: list[int] = Field(default_factory=list)
    allowed_years: list[int] = Field(default_factory=list)
    yongsin_element: str | None = None  # F-04 확정 — 이후 섹션 일관 검사 기준
    evidence_paths: list[str] = Field(default_factory=list)
    multi_subject: bool = False
    body_prompt: str = ""  # 직렬화된 LLM 입력(docs/06 계약 + 분량 목표)


class SectionResult(BaseModel):
    """섹션 생성 결과."""

    section_id: str
    title: str
    text: str = ""
    attempts: int = 0
    passed: bool = False
    violations: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class ReportCost(BaseModel):
    """원가 집계 (docs/10 9장) — 호출 로그 합산."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ReportResult(BaseModel):
    """조립 결과 — 보류 시 관리자 알림 대상."""

    spec: ReportSpec
    status: Literal["completed", "on_hold"]
    sections: list[SectionResult] = Field(default_factory=list)
    failed_sections: list[str] = Field(default_factory=list)  # 2회 재생성 실패
    total_chars: int = 0
    cost: ReportCost = Field(default_factory=ReportCost)
    # 재현성 파라미터(docs/10 8장 부록): dictVersion·chartVariant·페르소나 스냅샷.
    meta: dict = Field(default_factory=dict)

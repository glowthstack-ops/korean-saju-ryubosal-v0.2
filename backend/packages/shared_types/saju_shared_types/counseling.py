"""상담 결론 의미론(counseling decision semantics) — P1 스키마 (2026-08-21 승인 설계).

목적: "좋다/나쁘다"의 단일 축이 아니라 ①무엇이 움직이는지(activation) ②어느 단계가
힘든지(stage·friction) ③그럼에도 결과는 어떤지(outcome_outlook) ④어느 단계에서 밀고
어디서 멈출지(stage_action_policy)를 분리해 전달한다.

설계 불변식(전 계층 공유 — 위반은 결함):
- INV-A: summary_stance 는 stage_action_policy 의 **파생 요약**일 뿐 SSOT 가 아니다.
- INV-B: 배경 운(luck_backdrop)은 비거부권 — 어떤 stage action 도 만들거나 뒤집지 못한다.
- INV-C: activation 과 outcome_outlook 을 단일 good/bad 축으로 재합성하지 않는다.
- INV-D: neutral(중립 실판정)/mixed(양측 실증거)/unknown(근거 없음)은 판별 술어가 다른
  3값 — 무근거를 mixed/neutral 로 자동 폴백하지 않는다.
- INV-F: HOLD 는 event-local 명명 가능 근거가 최소 1개 필요하다.
- INV-G: friction(지연·압박)은 direction/outcome 을 변경하지 않는 직교 축이다.

이 모듈은 점수·간지·기존 quality/favorability 판정을 변경하지 않는 파생 계층이다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class StageScope(StrEnum):
    """사건 진행 단계 축 — 기회 유입 → 진행 → 결정 → 실행 → 실속·유지."""

    OPPORTUNITY = "opportunity"
    PROCESS = "process"
    DECISION = "decision"
    REALIZATION = "realization"
    OUTCOME = "outcome"


class StageAction(StrEnum):
    """단계별 행동 지침 — LLM 이 아니라 arbiter(코드)가 결정한다.

    UNKNOWN = 판단 재료 없음(LLM 보충 서술 금지). WITHHELD = 도메인 정책상 미산출
    (당락 단정 금지 영역 등) — '엔진이 못 정한 것'과 '안 정하는 것'의 구분(3값 원칙).
    """

    PROCEED = "proceed"
    CONDITIONAL = "conditional"
    HOLD = "hold"
    UNKNOWN = "unknown"
    WITHHELD = "withheld"


class FrictionKind(StrEnum):
    """마찰 신호 종류 — 결과 실패가 아니라 과정·시점의 결(INV-G)."""

    DELAY = "delay"                      # 시점 이연(공망·게이트) — 좋고 나쁨과 무관
    PRESSURE = "pressure"                # 경험 부담(기신 품질) — 성사 여부 아님
    CONFLICT = "conflict"                # 마찰·갈등 경험
    CONDITION_DEFECT = "condition_defect"  # 조건·유지력 하자(검토월·결실 뉘앙스)


class FrictionMark(BaseModel):
    """마찰 1건 — stage=None 은 특정 단계에 귀속되지 않는 직교 신호(공망 지연 등)."""

    kind: FrictionKind
    stage: StageScope | None = None
    source: str = ""  # reason_code·마커 카테고리(provenance)


StageDirection = Literal["favorable", "adverse", "mixed", "neutral", "unknown"]


class StageEvidenceSource(BaseModel):
    """단계 근거 1건의 provenance (CDS-P1b, 2026-08-21 방향 재설정).

    stage는 명리 primitive가 아니라 상담 의미론의 lifecycle 축이다 — 기존 domain
    SSOT가 stage provenance를 **명시 제공**할 때만 근거가 생기며, 그렇지 않은
    도메인/단계는 UNKNOWN이 정상 상태다(coverage 100%를 위해 임의의 십성·12운성
    매핑을 만들지 않는다 — 데굴님 확정).
    """

    type: str  # 'event_stage_tags' | 'ganji_nuance' | 'review_month' | 'gate' | 'outcome_code' …
    code: str
    reviewed: bool = False  # 해당 매핑이 감수·승인된 SSOT 유래인가


class StageAssessment(BaseModel):
    """단계 1개의 평가 — 근거(evidence) 없는 단계는 만들지 않는다(fail-closed)."""

    stage: StageScope
    direction: StageDirection = "unknown"
    frictions: list[FrictionMark] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    sources: list[StageEvidenceSource] = Field(default_factory=list)


ActivationBand = Literal["high", "moderate", "low", "unknown"]
OutcomeOutlook = Literal["favorable", "workable", "mixed", "weak", "adverse", "unknown"]
SummaryStance = Literal[
    "PROCEED", "PROCEED_WITH_CONDITIONS", "HOLD", "UNAVAILABLE"
]


class CounselingSemantics(BaseModel):
    """후보 1건의 상담 결론 파생 판정 — 엔진 evidence → arbiter 판단 → LLM 표현 순서."""

    event_key: str = ""
    event_ko: str = ""
    period: str = ""
    activation_band: ActivationBand = "unknown"
    outcome_outlook: OutcomeOutlook = "unknown"
    stages: list[StageAssessment] = Field(default_factory=list)
    # StageScope.value → StageAction.value (직렬화 안정성 위해 str 키).
    stage_action_policy: dict[str, str] = Field(default_factory=dict)
    summary_stance: SummaryStance = "UNAVAILABLE"  # 파생 전용(INV-A)
    # 배경 운 주석(INV-B: 비거부권) — 서술 배경 전용, 행동 지침 근거 사용 금지.
    luck_backdrop: str = ""
    # 도메인 캡 발동 사유(WITHHELD·요약 캡) — 예: 'competition'(당락 단정 금지 영역).
    domain_cap: str = ""
    unknown_stages: list[str] = Field(default_factory=list)

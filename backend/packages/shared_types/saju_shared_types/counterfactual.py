"""반사실(counterfactual) 컨텍스트 계약 — 서술 전용 inert 레이어 (2026-07-21 데굴님 확정).

"왜 늦게/왜 안 됐지/만약 그때 했다면" 류 질문에서 "그때 실행했다면 함께 활성화됐을 부담"을
도메인 범용으로 설명하기 위한 fail-closed 계약. GPT 검토안(사용자 승인) 4대 수정 반영:
①부담 분석과 보호 서사 분리(allowed_claim_level) ②상태 기계 fail-closed(INSUFFICIENT면
일반론 보호 서사 금지) ③기간 미확정 시 과거 체리피킹 금지 ④사건 단계(stage) 구분.

불변식(narrative_only): 사건 생성·점수·길흉·confidence·시점 후보를 절대 변경하지 않는다.
resolver는 기존 계산값(structure_analysis·세운 LuckPillar·life events)만 읽는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CounterfactualStatus = Literal[
    "NOT_APPLICABLE",  # 반사실 질문 아님(또는 대상 도메인 불명·health 제외 도메인)
    "INSUFFICIENT",  # 대상·기간 미확정 — 정적 구조 설명까지만, 과거 체리피킹 금지
    "ELIGIBLE_BURDEN_ONLY",  # 당시 부담 설명 가능 — 보호 결론 불가
    "ELIGIBLE_PROTECTIVE",  # 부담 + 이후 완화·회복 확인 — 제한적 보호 해석 허용
    "BLOCKED",  # 기간·대상은 확정됐으나 근거 신호 불일치/부재 — 반사실 단정 금지
]

CounterfactualMode = Literal[
    "",  # 미감지
    "counterfactual_explicit",  # "2021년에 결혼했으면 어땠을까"
    "counterfactual_implicit",  # "왜 계약이 늦었지" — 과거 실행 가능성 내포
    "retrospective_causal",  # "왜 취업이 안 됐지" — 지나간 결과의 원인
    "current_non_occurrence",  # "왜 나는 결혼이 늦어" — 현재 상태(과거 반사실 자동 금지)
]

EventStage = Literal["initiation", "stabilization", "maintenance", "fruition", "recovery"]

ClaimLevel = Literal[
    "none",  # 서술 불가(NOT_APPLICABLE/BLOCKED)
    "structure_only",  # 정적 구조 경향까지만(시기 효과 서술 금지)
    "burden_only",  # 당시 부담 증가 '가능성'까지만
    "burden_plus_recovery",  # + 이후 완화·회복 비교(제한적 보호 해석)
]


class CounterfactualSignal(BaseModel):
    """반사실 근거 신호 1건 — 전부 기존 엔진 계산값의 재배치(신규 판정 아님)."""

    signal_id: str  # 예: NATAL_CLASH_배우자궁 / YEAR_CLASH_ACTIVATED_2025 / SUPPORT_YEAR_2024
    stage: EventStage  # 이 신호가 영향을 주는 사건 단계
    scope: Literal["natal", "period", "after"]  # 원국 구조 / 대상 기간 활성 / 기간 이후
    detail: str = ""  # 한글 서술 재료(관계명·궁위·운 품질 등)
    period: str = ""  # 연도 라벨(기간 신호일 때)
    confidence: Literal["high", "medium", "low"] = "medium"


class CounterfactualContext(BaseModel):
    """LLM 입력용 반사실 컨텍스트 — usage는 항상 narrative_only(점수·판정 개입 금지)."""

    status: CounterfactualStatus = "NOT_APPLICABLE"
    mode: CounterfactualMode = ""
    domain: str = ""  # career/relationship/relocation/wealth/education('' = 미확정)
    target: str = ""  # 이벤트 한글 라벨 또는 도메인 기본 대상
    period_from: str = ""  # 'YYYY'
    period_to: str = ""
    period_source: Literal["", "user_stated", "thread_inherited", "life_event"] = ""
    burden_signals: list[CounterfactualSignal] = Field(default_factory=list)
    support_signals: list[CounterfactualSignal] = Field(default_factory=list)
    recovery_signals: list[CounterfactualSignal] = Field(default_factory=list)
    allowed_claim_level: ClaimLevel = "none"
    usage: Literal["narrative_only"] = "narrative_only"

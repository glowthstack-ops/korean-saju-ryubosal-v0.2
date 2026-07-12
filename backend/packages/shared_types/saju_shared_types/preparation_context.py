"""재물 준비기(lead-up) 컨텍스트 타입 — 발현 후보년·선행 준비 신호 (2026-07-12 데굴님 확정).

서술 전용(narrative_only) inert 레이어의 출력 계약. 불변식: 이벤트 점수·후보 순위·
발현 시점(년월)·confidence·favorability를 변경하지 않고 사건을 생성하지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManifestationCandidate(BaseModel):
    """재성 유입 세운 = 발현 '후보'년(확정 발현년 아님 — 등급제).

    strong=천간·지지 본기 모두 재성군 / moderate=한쪽 재성+같은 해 식상 동반(식상생재 유입) /
    weak=한쪽 재성 단독. 지장간 전용 재성은 후보를 생성하지 않는다(신호 수집이 본기까지).
    """

    year: str
    ganji: str
    grade: Literal["strong", "moderate", "weak"]
    wealth_positions: list[str] = Field(default_factory=list)  # 'stem' | 'branch_main'


class PreparationYear(BaseModel):
    """발현 후보년 직전 2년 창의 준비 신호년.

    Y-1=주 준비기(weight 1.0), Y-2=약한 선행 준비기(weight 0.55). Y-3 이전·대운 단위
    확장 금지. 신호 강도: 식상+비겁 또는 두 자리 모두 준비 신호=strong / 식상 단독=
    moderate / 비겁 단독(한 자리)=weak(조건부). 인성은 준비년을 단독 생성하지 않는다.
    """

    year: str
    ganji: str
    target_year: str  # 이 준비년이 향하는 발현 후보년
    weight: float  # Y-1=1.0, Y-2=0.55
    signals: list[str] = Field(default_factory=list)  # 'output'(식상) | 'peer'(비겁)
    strength: Literal["strong", "moderate", "weak"]
    resource_support: bool = False  # 인성 동반(식상과 결합 시) — 학습→결과물 전환 보조 설명


class PreparationContext(BaseModel):
    """LLM 입력용 준비기 컨텍스트 — usage는 항상 narrative_only(점수·판정 개입 금지)."""

    is_detected: bool = False
    manifestation_candidates: list[ManifestationCandidate] = Field(default_factory=list)
    preparation_years: list[PreparationYear] = Field(default_factory=list)
    current_year_role: Literal["preparation", "manifestation", "none"] = "none"
    usage: Literal["narrative_only"] = "narrative_only"

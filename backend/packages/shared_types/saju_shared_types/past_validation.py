"""Past Validation schemas (v2.2 Phase 6, docs/02 E7 — 신뢰 엔진).

과거 사건 복원 → 사용자 확인 → 신뢰도 계산 — **미래 예측보다 먼저 노출**(docs/01
신뢰 형성 플로우). 콜드리딩 금지: 모든 후보에 evidence path 필수, 연도당 후보 2개
이하 + score 임계값 엄격(docs/07 리스크 3 — "뭐든 맞는" 결과 방지).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import EventKey


class PastCandidate(BaseModel):
    """과거 이벤트 후보 1건 — 근거 경로 필수(콜드리딩 방지)."""

    year_range: str  # '2009' 또는 '2009~2010'
    event_key: EventKey
    score: int = Field(ge=0, le=100)
    evidence_path: list[str] = Field(min_length=1)  # 근거 없는 후보 금지
    readable: list[str] = Field(default_factory=list)  # "2009 입학 ← 정관 활성 ←..."


class PastValidationResult(BaseModel):
    """E7 출력 — 후보 + (피드백 후) 보정 신뢰도."""

    candidates: list[PastCandidate] = Field(default_factory=list)
    calibrated_confidence: float | None = None  # 사용자 확인 후 채움(0~1)


class PastFeedbackItem(BaseModel):
    """사용자 확인 1건 — cases.jsonl 적재 원천(docs/05)."""

    year_range: str
    event_key: EventKey
    matched: bool
    actual_event: str | None = None  # 불일치 시 실제 사건(자유 기술)
    notes: str | None = None


class CalibrationOutcome(BaseModel):
    """T6.3 — 맞춘 비율 → 신뢰도 % → 표현 강도(미래 예측 서술에 반영)."""

    matched: int
    total: int
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    expression_level: str  # 'normal' | 'conservative' | 'very_conservative'
    note: str = ""

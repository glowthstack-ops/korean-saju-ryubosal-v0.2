"""용신 검증 루프 schemas (Phase 4c).

용신 확정은 계산만으로 하지 않는다. 대운·세운 반응과 사용자 피드백으로 calibration 하여
calibrated / probable / uncertain 중 하나로 판정한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 사건 도메인 (saju_v2_yongsin_calibration_loop_spec §5).
EVENT_DOMAINS: dict[str, list[str]] = {
    "career": ["취업", "이직", "퇴사", "승진", "프로젝트 성과"],
    "study": ["입학", "졸업", "시험", "자격증"],
    "money": ["큰 수입", "큰 지출", "투자 손익"],
    "relationship": ["연애 시작", "연애 종료", "결혼", "이별"],
    "family_health": ["본인 건강", "가족 건강", "병원", "간병"],
    "relocation": ["이사", "독립", "해외 이동"],
    "legal_public": ["계약", "소송", "공공기관", "신분 변화"],
}

# 강한(중대) 사건일수록 가중.
MAJOR_EVENTS: set[str] = {
    "결혼", "이별", "취업", "이직", "퇴사", "입학", "졸업",
    "이사", "해외 이동", "큰 수입", "큰 지출", "본인 건강", "신분 변화",
}

FEEDBACK_SCALE: dict[str, int | None] = {
    "very_positive": 2, "positive": 1, "neutral": 0,
    "negative": -1, "very_negative": -2, "unknown": None,
}

Rating = Literal["very_positive", "positive", "neutral", "negative", "very_negative", "unknown"]


class CalibrationQuestion(BaseModel):
    id: str
    question_type: str  # useful/unfavorable/contrast/event_domain/period_detail
    period_type: str  # year / year_month
    year: int
    month: int | None = None
    period_label: str
    target_models: list[str] = Field(default_factory=list)
    expected_effect_by_model: dict[str, str] = Field(default_factory=dict)
    ask_domains: list[str] = Field(default_factory=list)
    question_text: str
    options: list[str] = Field(default_factory=list)


class CalibrationQuestionSet(BaseModel):
    status: str  # required / not_available
    questions: list[CalibrationQuestion] = Field(default_factory=list)
    candidate_periods: list[dict] = Field(default_factory=list)
    note: str | None = None


class FeedbackAnswer(BaseModel):
    question_id: str
    overall_rating: Rating
    selected_events: list[str] = Field(default_factory=list)
    domain_ratings: dict[str, int | None] = Field(default_factory=dict)
    memo: str | None = None


class CalibrationResult(BaseModel):
    status: str  # calibrated / probable / uncertain
    final_yongsin: str | None = None
    final_heesin: str | None = None
    final_gisin: str | None = None
    final_gusin: str | None = None
    confidence: float = 0.0
    evidence_count: int = 0
    match_rate: float = 0.0
    model_scores: dict[str, float] = Field(default_factory=dict)
    selected_model: str | None = None
    explanation: list[str] = Field(default_factory=list)

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

# 검증 질문에 노출하는 '영향 영역' 범주 라벨(개별 사건 대신 범주 단위로 체크).
DOMAIN_LABELS: dict[str, str] = {
    "career": "직업", "money": "금전", "relationship": "연애/부부",
    "family_health": "건강", "relocation": "이동", "study": "학업",
    "legal_public": "계약/공공",
}

# 군 입대/제대 — 한국 남성 한정 노출. 나이가 거의 고정(~20세)이라 그 해를 특정해 주는
# 강한 회상 단서이자 관성(官)·신분 변화 신호. 남성 명식에만 영역 칩으로 추가한다.
MILITARY_DOMAIN: str = "군 입대/제대"

# 삶에 큰 영향을 주는 범주일수록 가중(범주 단위).
MAJOR_DOMAINS: set[str] = {"직업", "금전", "연애/부부", "건강", "이동", MILITARY_DOMAIN}

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
    period_range: str = ""  # 세운 범위(입춘 기준), 예: "입춘 기준 2001-02-04 ~ 2002-02-03"
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
    model_scores: dict[str, float] = Field(default_factory=dict)  # raw 피드백 점수
    # confidence 가중(실제 선택 기준)
    weighted_model_scores: dict[str, float] = Field(default_factory=dict)
    selected_model: str | None = None
    explanation: list[str] = Field(default_factory=list)

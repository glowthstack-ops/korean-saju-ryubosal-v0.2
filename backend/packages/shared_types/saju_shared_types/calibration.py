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


# ── 이벤트형 검증(연도별 이벤트 나열 + 이벤트별 긍/부정) ──────────────
# EventKey → 표시 카테고리 코드. 이직(이동)·직업·애정·금전·건강·학업으로 묶는다(사용자 확정).
# contract/document/lawsuit는 회상 변별력이 낮아 1차 제외. 애정 라벨은 혼인상태로 프론트가 결정.
EVENT_CATEGORY: dict[str, str] = {
    "promotion": "career",
    "business_start": "career",
    "career_change": "move",
    "resignation": "move",
    "relocation": "move",
    "travel": "move",
    "relationship_start": "affection",
    "relationship_end": "affection",
    "marriage": "affection",
    "childbirth": "affection",
    "family_change": "affection",
    "wealth_change": "money",
    "income_change": "money",
    "expense_risk": "money",
    "windfall": "money",
    "speculation_risk": "money",
    "asset_volatility": "money",
    "health_issue": "health",
    "surgery": "health",
    "education_start": "study",
    "education_complete": "study",
    "exam": "study",
}

# 카테고리 코드 → 기본 표시 라벨. affection은 프론트가 혼인상태로 치환(미입력=연애 또는 부부관계).
EVENT_CATEGORY_LABEL: dict[str, str] = {
    "career": "직업(직장·사업)",
    "move": "이동(이직·이사)",
    "affection": "연애 또는 부부관계",
    "money": "금전",
    "health": "건강",
    "study": "학업",
}

# 점수 가중이 큰(삶에 큰 영향) 카테고리 — feedback 가중 1.5.
MAJOR_CATEGORIES: set[str] = {"career", "move", "affection", "money", "health"}

# 이벤트별 응답 — 이분 + 해당없음(점수 제외).
EventRating = Literal["positive", "negative", "na"]

# 이벤트형 응답(긍/부정) → 점수. na/None은 제외.
EVENT_RATING_SCORE: dict[str, int | None] = {"positive": 1, "negative": -1, "na": None}


class CalibrationEventItem(BaseModel):
    """검증 질문에 나열되는 그 해의 이벤트 1건.

    expected_by_model: 모델 type → 그 모델 용희기구로 재계산한 기대 극성
    (positive/negative/mixed/neutral). 사용자 응답과 대조해 모델을 투표한다.
    """

    event_key: str
    category: str  # EVENT_CATEGORY 값(career/move/affection/money/health/study)
    label: str  # 사용자 표시 라벨(이벤트 한글명)
    expected_by_model: dict[str, str] = Field(default_factory=dict)


class CalibrationQuestion(BaseModel):
    id: str
    question_type: str  # useful/unfavorable/contrast/event_domain/period_detail/event_list
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
    # 이벤트형 질문에만 채워진다(연도별 검출 이벤트 + 모델별 기대 극성).
    events: list[CalibrationEventItem] = Field(default_factory=list)


class CalibrationQuestionSet(BaseModel):
    status: str  # required / not_available
    questions: list[CalibrationQuestion] = Field(default_factory=list)
    candidate_periods: list[dict] = Field(default_factory=list)
    note: str | None = None


class FeedbackAnswer(BaseModel):
    question_id: str
    # 비이벤트형(레거시) 질문의 전체 평점. 이벤트형 질문이면 'unknown'(미사용)일 수 있다.
    overall_rating: Rating = "unknown"
    selected_events: list[str] = Field(default_factory=list)
    domain_ratings: dict[str, int | None] = Field(default_factory=dict)
    # 이벤트형 응답 — event_key → 'positive'|'negative'|'na'.
    event_ratings: dict[str, EventRating] = Field(default_factory=dict)
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

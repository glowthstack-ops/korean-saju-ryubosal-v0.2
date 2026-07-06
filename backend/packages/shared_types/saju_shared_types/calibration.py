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

# ── CAL-P0(상담 사례 파생, doc/v2_2/cases/1980_1122_job_report_case.md) ──────
# trait_probe 허용 대상 축 — 성향 해석 표현의 적중도 검수용(용신·점수 채점 절대 비반영).
TRAIT_PROBE_TARGETS: tuple[str, ...] = (
    "communication_style",
    "loneliness_or_relationship_need",
    "money_management_style",
    "career_expression_style",
    "decision_style",
    "social_energy",
)
TRAIT_TARGET_KO: dict[str, str] = {
    "communication_style": "표현·전달 방식",
    "loneliness_or_relationship_need": "외로움·관계 욕구",
    "money_management_style": "돈 관리 방식",
    "career_expression_style": "일에서의 발현 방식",
    "decision_style": "의사결정 방식",
    "social_energy": "사회적 에너지",
}
# trait_probe 응답 선택지(프론트 표시) ↔ trait_response 값.
TRAIT_PROBE_OPTIONS: list[str] = [
    "대체로 그렇다", "상황에 따라 다르다", "그렇지 않다", "잘 모르겠다",
]
TRAIT_RESPONSES: tuple[str, ...] = ("agreed", "mixed", "denied", "unclear")

# ── CAL-P1(doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md, 2026-07-03 확정) ──────
# 정적 결핍 vs 운 작동 이원 probe. 둘 다 채점 절대 비반영(§5 불변식) — review 축적과
# LLM 표현 힌트 전용. A(static)의 응답 체계는 trait_probe와 동일 4지를 재사용한다.
STATIC_DEFICIENCY_RESPONSES: tuple[str, ...] = TRAIT_RESPONSES
TRANSIT_ACTIVATION_RESPONSES: tuple[str, ...] = ("strong", "partial", "none", "unknown")
# B 응답 라벨(P1-b 확정, 2026-07-03) ↔ strong/partial/none/unknown.
TRANSIT_PROBE_OPTIONS: list[str] = [
    "강하게 있었다", "일부 있었다", "거의 없었다", "잘 모르겠다",
]
# 성향 반박 결 태깅(§4) — 룰 기반 분류값. 빈 진술은 None(정보 없음 ≠ unclear=분류 실패).
TRAIT_DENIAL_KINDS: tuple[str, ...] = (
    "absolute", "situational", "temporal", "mixed", "unclear",
)


class TraitProbeCandidate(BaseModel):
    """trait_probe 질문 후보 — 엔진 신호(결정론 predicate)에서 생성한다.

    manse_service가 명식 사실(신살·십성 분포)로 후보를 만들어 주입하며, 질문 생성기는
    후보를 그대로 질문으로 옮길 뿐 명리 판단을 하지 않는다(원칙 1).
    """

    target: str  # TRAIT_PROBE_TARGETS 중 하나
    engine_basis: list[str] = Field(default_factory=list)  # 예: ["현침"], ["관성 부재"]
    question_text: str
    # CAL-P1 suppress 매칭 키(§1-C) — 같은 axis의 P1 pair가 생성되면 이 후보를 숨긴다.
    # 신살 기반(현침 등)은 None — axis suppress 대상 아님.
    axis_key: str | None = None


class DeficiencyPairCandidate(BaseModel):
    """정적 결핍 A/B pair 질문 후보 — CAL-P1-b(엔진 결정론 predicate에서 생성).

    manse_service가 오행 표면 부재·십성 그룹 표면 부재로 후보를 만들고 우선순위로
    정렬해 주입한다(논쟁 축 우선 — §2-4). 질문 생성기는 B 앵커 해 랭킹과 cap만 담당.
    """

    axis_type: str  # element | ten_god_group
    axis_id: str  # 예: wood / officer
    axis_element: str  # 한자 오행(B 앵커 해 매칭용) — 예: 木
    engine_basis: list[str] = Field(default_factory=list)
    static_question_text: str  # A 질문 전문(비시간형)
    transit_question_text: str  # B 질문 본문(앵커 연도 프리픽스는 생성기가 부착)
    # 이 pair가 생성되면 숨길 trait_probe axis_key 목록(§1-C suppress).
    suppress_axis_keys: list[str] = Field(default_factory=list)


class TraitProbeFeedback(BaseModel):
    """trait_probe 응답 축적 레코드 — 감수 전용(accumulate_only).

    성향 반박은 '엔진 오류 확정'이 아니라 표현 방식·발현 조건·환경 의존성의 재해석
    재료다. 용신·기신 역할, 이벤트 점수, favorability에 절대 반영하지 않는다(CAL-P0 금지).
    """

    type: str = "trait_probe_feedback"
    question_id: str
    target: str
    engine_basis: list[str] = Field(default_factory=list)
    user_feedback: str  # agreed / mixed / denied / unclear
    user_statement: str | None = None
    # 반박 결 태깅(CAL-P1 §4 — 룰 기반, 채점 비반영). 진술이 없으면 None.
    denial_kind: str | None = None
    scoring_effect: str = "none"
    review_status: str = "accumulate_only"


class PairExpressionHint(BaseModel):
    """A×B 응답 매트릭스 → LLM 표현 조정 힌트(P1-c §6-2) — 판정 변경이 아니라 서술 조정.

    instruction은 한국어 지시문(불변 조항 포함). narrative_mode는 매트릭스 행 식별자 —
    dual_static_deficiency_and_transit_pressure / conditional_manifestation /
    felt_lack_without_activation / external_period_pressure / deemphasize_axis /
    hedge_uncertain.
    """

    axis_type: str
    axis_id: str
    element: str | None = None  # 축 대상 오행(한자)
    basis_label: str = ""  # 예: "木 표면 부재·관성 표면 부재"
    static_response: str | None = None
    transit_response: str | None = None
    transit_year: int | None = None
    narrative_mode: str
    instruction: str


class DeficiencyPairFeedback(BaseModel):
    """정적 결핍(A) + 운 작동(B) 쌍 응답 축적 레코드 — CAL-P1 §6-1(accumulate_only).

    응답 조합은 해석 매트릭스(§6-2)로 LLM 표현 힌트·감수 자료에만 쓰이며, 용신·기신
    role, event score, favorability, selected_model에 절대 반영하지 않는다(§5 불변식).
    P1-a에서는 스키마만 — 생성·수집 배선은 P1-b.
    """

    type: str = "deficiency_pair_feedback"
    pair_id: str
    axis_type: str  # element | ten_god_group
    axis_id: str  # 예: wood / officer
    axis_element: str | None = None  # 축 대상 오행(한자)
    engine_basis: list[str] = Field(default_factory=list)
    static_response: str | None = None  # agreed / mixed / denied / unclear
    static_statement: str | None = None
    static_denial_kind: str | None = None  # §4 태깅(빈 진술 None)
    transit_year: int | None = None
    transit_response: str | None = None  # strong / partial / none / unknown
    transit_statement: str | None = None
    scoring_effect: str = "none"
    review_status: str = "accumulate_only"

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

# ── 해상도 개선(docs/14) — 정도+반반 2축 분해 ────────────────────────────
# ExperienceRating: 좋고 나쁨의 정도 + '반반(혼재)'. neutral(무던)≠mixed(혼재)를 분리한다.
ExperienceRating = Literal[
    "very_positive", "positive", "neutral", "mixed", "negative", "very_negative", "unknown"
]
# 극성 축(정도) — mixed는 0(좋고 나쁨 상쇄), unknown/na는 None(채점 제외).
EXPERIENCE_POLARITY: dict[str, float | None] = {
    "very_positive": 2.0, "positive": 1.0, "neutral": 0.0, "mixed": 0.0,
    "negative": -1.0, "very_negative": -2.0, "unknown": None,
}
# 변동성 축 — mixed만 1(충·형·합·교운·대운전환 신호). 그 외 0.
EXPERIENCE_VOLATILITY: dict[str, float] = {
    "very_positive": 0.0, "positive": 0.0, "neutral": 0.0, "mixed": 1.0,
    "negative": 0.0, "very_negative": 0.0, "unknown": 0.0,
}
# FE 영역별 상태 → 내부 값(연도 전체/사건 강도는 7상태 그대로 사용).
# CAL-QA: '특별한 일 없었음'은 무신호(no_domain_activity) — 모름(unknown)과 구분.
DOMAIN_RATING_FROM_UI: dict[str, str] = {
    "좋음": "positive", "보통": "neutral", "반반": "mixed", "힘듦": "negative", "모름": "unknown",
    "특별한 일 없었음": "no_domain_activity",
}


# ── CAL-QA(docs/14 §8, 2026-07-03 확정) — 무신호(no-signal) 응답 상태 ─────────
# '기억 안 남(unknown)'과 구분되는 실제 무신호 값. 채점·분모에서 제외하되 raw 응답
# blob에는 값 그대로 축적한다(unknown과 혼합 금지 — 데이터 계약).
NO_DOMAIN_ACTIVITY = "no_domain_activity"  # 그 기간 그 영역에 평가할 활동·사건 없음
NOT_OCCURRED = "not_occurred"  # 엔진 제시 이벤트가 실제로 발생하지 않음(발생 반증)
# 주의: not_occurred는 용신/기신 판정 근거가 아니다(결정② — 발생은 이벤트 엔진
# 개인화 축). personal_match 승격은 CAL-P2에서 판단 — 현재는 축적만.
NO_SIGNAL_RATINGS: frozenset[str] = frozenset({NO_DOMAIN_ACTIVITY, NOT_OCCURRED})


def experience_polarity(rating: str | None) -> float | None:
    """ExperienceRating(또는 레거시 'na') → 극성 점수. 모름·무신호는 None(채점·분모 제외).

    CAL-QA: no_domain_activity/not_occurred는 unknown과 같은 '제외'지만 저장 값은
    구분된다 — 채점 함수만 동일하게 None을 돌려 분모 오염을 막는다(docs/14 §8 불변식).
    """
    if rating is None or rating in ("na", "unknown") or rating in NO_SIGNAL_RATINGS:
        return None
    return EXPERIENCE_POLARITY.get(rating)


def experience_volatility(rating: str | None) -> float:
    """ExperienceRating → 변동성(mixed=1). 레거시/미상/무신호는 0."""
    return EXPERIENCE_VOLATILITY.get(rating or "", 0.0)


CALIB_DOMAINS: tuple[str, ...] = ("career", "money", "relationship", "health")
# 이벤트 카테고리(EVENT_CATEGORY 값) → 캘리브레이션 4도메인. move/study는 career로 접음(확장 후속).
CATEGORY_TO_CALIB_DOMAIN: dict[str, str] = {
    "career": "career", "move": "career", "study": "career",
    "money": "money", "affection": "relationship", "health": "health",
}


class DomainExpectation(BaseModel):
    """한 도메인에 대한 모델의 기대(도메인 이벤트들의 기대극성 집계, docs/14 결정③).

    status='no_signal'은 '모델이 그 영역을 판단할 근거 없음'으로 neutral(평온 예상)과 구분한다
    (채점 분모에서 제외). scored일 때만 expected_polarity/volatility가 유효하다.
    """

    expected_polarity: float | None = None
    expected_volatility: float | None = None
    signal_strength: float = 0.0
    status: Literal["scored", "no_signal"] = "no_signal"


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
    # useful/unfavorable/contrast/event_domain/period_detail/event_list
    # + CAL-P0: transition_probe(교운기 변화 회상 — ranking에만 관여)
    #          trait_probe(성향 동의/반박 수집 — 채점 절대 비반영)
    # + CAL-P1: static_deficiency_probe(정적 결핍 체감 — 비시간형)
    #          transit_activation_probe(운 작동 확인 — 연도 앵커형). 둘 다 채점 비반영.
    question_type: str
    period_type: str  # year / year_month / trait(비시간 성향 질문)
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
    # 모델별 도메인 기대(docs/14 P1) — model_type → domain → DomainExpectation. 질문 생성 시 산출.
    domain_expectations: dict[str, dict[str, DomainExpectation]] = Field(default_factory=dict)
    # trait_probe 전용(CAL-P0) — 성향 대상 축과 엔진 근거. 그 외 유형은 빈 값.
    trait_target: str | None = None
    engine_basis: list[str] = Field(default_factory=list)
    # CAL-P1 pair 전용 — A/B 두 질문이 pair_id·축을 공유한다(P1-a 스키마만, 생성은 P1-b).
    pair_id: str | None = None
    axis_type: str | None = None  # element | ten_god_group
    axis_id: str | None = None
    axis_element: str | None = None  # 축 대상 오행(한자) — 힌트 직렬화용(P1-c)


class CalibrationQuestionSet(BaseModel):
    status: str  # required / not_available
    questions: list[CalibrationQuestion] = Field(default_factory=list)
    candidate_periods: list[dict] = Field(default_factory=list)
    note: str | None = None


class FeedbackAnswer(BaseModel):
    question_id: str
    # 그 해 전체 체감(ExperienceRating 7상태 — 'mixed' 포함). 이벤트형 질문이면 'unknown'일 수 있다.
    overall_rating: ExperienceRating = "unknown"
    selected_events: list[str] = Field(default_factory=list)
    # 영역별 체감(docs/14 B) — domain → ExperienceRating(좋음/보통/반반/힘듦/모름 매핑). 채점 주축.
    # (레거시 dict[str,int|None]에서 승격 — 죽어있던 필드 활성.)
    domain_ratings: dict[str, str] = Field(default_factory=dict)
    # 이벤트형 응답 — event_key → ExperienceRating(레거시 'positive'|'negative'|'na' 호환)
    # + CAL-QA 'not_occurred'(그런 일 없었음 — 채점 제외, 축적만. docs/14 §8).
    event_ratings: dict[str, str] = Field(default_factory=dict)
    # 사건별 강도(선택, 1~3) — 미세 가중. 없으면 채점에서 강도 항 생략.
    event_intensity: dict[str, int] = Field(default_factory=dict)
    memo: str | None = None
    # trait_probe 응답(CAL-P0) — agreed/mixed/denied/unclear. 채점 비반영, 축적 전용.
    trait_response: str | None = None
    trait_statement: str | None = None  # 자유 서술(예: '면접에서 말을 잘 못한다')
    # CAL-P1 static_deficiency_probe 응답(P1-c 확정 — 전용 필드. trait_response 폴백 허용).
    static_response: str | None = None
    # CAL-P1 transit_activation_probe 응답 — strong/partial/none/unknown. 채점 비반영.
    transit_response: str | None = None
    transit_statement: str | None = None


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
    # CAL-P0 — trait_probe 축적(감수 전용)과 LLM 표현 조정 힌트. 용신·점수 판정에 비반영.
    trait_probe_feedback: list[TraitProbeFeedback] = Field(default_factory=list)
    trait_llm_hints: list[str] = Field(default_factory=list)
    # CAL-P1 — 이원 probe 쌍 축적(P1-b) + A×B 매트릭스 표현 힌트(P1-c). 판정 비반영.
    deficiency_pair_feedback: list[DeficiencyPairFeedback] = Field(default_factory=list)
    pair_expression_hints: list[PairExpressionHint] = Field(default_factory=list)

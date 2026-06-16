"""21키 이벤트 taxonomy 부속 테이블 (Phase 7 하드 스위치 타깃 계층).

EventKeyV2(21종)의 한글 라벨·시간성격·검증 카테고리·리포트 도메인·구키 매핑·금기룰·질의
키워드·택일 대상과, 새 출력 차원(quality/confidence_level/temporal_mode/궁성)의 한글 라벨을
한곳에 모은다. 다운스트림(planner·calibration·report·chat·query_parser·graph·context_reducer)이
구 EventKey(25종) 대신 본 테이블을 참조하도록 7c에서 전환한다.

EventKeyV2는 StrEnum이라 dict 키로 두어도 평문 문자열로 조회된다(event_key 직렬화 호환).
"""

from __future__ import annotations

from .event_engine import (
    ConfidenceLevel,
    EventKeyV2,
    EventQuality,
    Pillar4,
    TemporalMode,
)

# ── 한글 라벨 (사용자 노출 — 내부 키 노출 금지) ──────────────────
EVENT_KO: dict[EventKeyV2, str] = {
    EventKeyV2.CAREER_CHANGE: "이직·직업 변화",
    EventKeyV2.JOB_GAIN: "취업·합격",
    EventKeyV2.PROMOTION: "승진·인정",
    EventKeyV2.BUSINESS_START: "사업 시작·개업",
    EventKeyV2.BUSINESS_EXPANSION: "사업 확장",
    EventKeyV2.WEALTH_CHANGE: "재물 변화",
    EventKeyV2.WINDFALL: "횡재",  # '표현 제한'은 prohibit_windfall 금기룰이 강제(라벨 비주입)
    EventKeyV2.CONTRACT_DOCUMENT: "계약·문서",
    EventKeyV2.EDUCATION_ADMISSION: "합격·진학·자격",
    EventKeyV2.EDUCATION_COMPLETION: "수료·졸업",
    EventKeyV2.RELATIONSHIP_CHANGE: "관계 변화",
    EventKeyV2.NEW_RELATIONSHIP: "새 인연",
    EventKeyV2.MARRIAGE_SIGNAL: "결혼 신호",
    EventKeyV2.CHILDBIRTH: "출산·자녀",
    EventKeyV2.RELOCATION: "이사·이동",
    EventKeyV2.LEGAL_CONFLICT: "법적 갈등",
    EventKeyV2.HEALTH_ATTENTION: "건강 주의",
    EventKeyV2.SOCIAL_CONFLICT: "사회적 갈등",
    EventKeyV2.PREPARATION_DELAY: "준비·지연",
    EventKeyV2.CREATIVE_OUTPUT: "결과물·창작",
    EventKeyV2.PUBLIC_EXPOSURE: "공개 노출·평가",
}

# ── 시간 성격 (progress/instant/hybrid — 택일·타임라인 분기) ──────
EVENT_TYPE: dict[EventKeyV2, str] = {
    EventKeyV2.CAREER_CHANGE: "progress",
    EventKeyV2.JOB_GAIN: "progress",
    EventKeyV2.PROMOTION: "progress",
    EventKeyV2.BUSINESS_START: "progress",
    EventKeyV2.BUSINESS_EXPANSION: "progress",
    EventKeyV2.WEALTH_CHANGE: "progress",
    EventKeyV2.WINDFALL: "instant",
    EventKeyV2.CONTRACT_DOCUMENT: "instant",
    EventKeyV2.EDUCATION_ADMISSION: "progress",
    EventKeyV2.EDUCATION_COMPLETION: "progress",
    EventKeyV2.RELATIONSHIP_CHANGE: "progress",
    EventKeyV2.NEW_RELATIONSHIP: "progress",
    EventKeyV2.MARRIAGE_SIGNAL: "progress",
    EventKeyV2.CHILDBIRTH: "progress",
    EventKeyV2.RELOCATION: "hybrid",
    EventKeyV2.LEGAL_CONFLICT: "progress",
    EventKeyV2.HEALTH_ATTENTION: "progress",
    EventKeyV2.SOCIAL_CONFLICT: "instant",
    EventKeyV2.PREPARATION_DELAY: "progress",
    EventKeyV2.CREATIVE_OUTPUT: "progress",
    EventKeyV2.PUBLIC_EXPOSURE: "instant",
}

# ── 검증(calibration) 카테고리 — career/move/affection/money/health/study ──
EVENT_CATEGORY: dict[EventKeyV2, str] = {
    EventKeyV2.JOB_GAIN: "career",
    EventKeyV2.PROMOTION: "career",
    EventKeyV2.BUSINESS_START: "career",
    EventKeyV2.BUSINESS_EXPANSION: "career",
    EventKeyV2.CREATIVE_OUTPUT: "career",
    EventKeyV2.PUBLIC_EXPOSURE: "career",
    EventKeyV2.CAREER_CHANGE: "move",
    EventKeyV2.RELOCATION: "move",
    EventKeyV2.RELATIONSHIP_CHANGE: "affection",
    EventKeyV2.NEW_RELATIONSHIP: "affection",
    EventKeyV2.MARRIAGE_SIGNAL: "affection",
    EventKeyV2.CHILDBIRTH: "affection",
    EventKeyV2.WEALTH_CHANGE: "money",
    EventKeyV2.WINDFALL: "money",
    EventKeyV2.HEALTH_ATTENTION: "health",
    EventKeyV2.EDUCATION_ADMISSION: "study",
    EventKeyV2.EDUCATION_COMPLETION: "study",
}

# ── 리포트·planner 도메인 — career/relationship/relocation/wealth/education/health ──
EVENT_DOMAIN: dict[EventKeyV2, str] = {
    EventKeyV2.CAREER_CHANGE: "career",
    EventKeyV2.JOB_GAIN: "career",
    EventKeyV2.PROMOTION: "career",
    EventKeyV2.BUSINESS_START: "career",
    EventKeyV2.BUSINESS_EXPANSION: "career",
    EventKeyV2.CREATIVE_OUTPUT: "career",
    EventKeyV2.PUBLIC_EXPOSURE: "career",
    EventKeyV2.CONTRACT_DOCUMENT: "career",
    EventKeyV2.SOCIAL_CONFLICT: "career",
    EventKeyV2.LEGAL_CONFLICT: "career",
    EventKeyV2.PREPARATION_DELAY: "career",
    EventKeyV2.RELATIONSHIP_CHANGE: "relationship",
    EventKeyV2.NEW_RELATIONSHIP: "relationship",
    EventKeyV2.MARRIAGE_SIGNAL: "relationship",
    EventKeyV2.CHILDBIRTH: "relationship",
    EventKeyV2.RELOCATION: "relocation",
    EventKeyV2.WEALTH_CHANGE: "wealth",
    EventKeyV2.WINDFALL: "wealth",
    EventKeyV2.EDUCATION_ADMISSION: "education",
    EventKeyV2.EDUCATION_COMPLETION: "education",
    EventKeyV2.HEALTH_ATTENTION: "health",
}

# ── 구 EventKey(25종) → 신 EventKeyV2(21종) 매핑 (2026-06-13 사용자 확정) ──
# 저장된 검증/대화 데이터의 구키를 신키로 옮길 때 사용한다(손실성 매핑은 quality로 의미 보존).
LEGACY_EVENT_KEY_MAP: dict[str, EventKeyV2] = {
    "career_change": EventKeyV2.CAREER_CHANGE,
    "promotion": EventKeyV2.PROMOTION,
    "resignation": EventKeyV2.CAREER_CHANGE,  # 퇴사 = 직업 변화[압박]
    "business_start": EventKeyV2.BUSINESS_START,
    "relationship_start": EventKeyV2.NEW_RELATIONSHIP,
    "relationship_end": EventKeyV2.RELATIONSHIP_CHANGE,
    "marriage": EventKeyV2.MARRIAGE_SIGNAL,
    "childbirth": EventKeyV2.CHILDBIRTH,
    "relocation": EventKeyV2.RELOCATION,
    "contract": EventKeyV2.CONTRACT_DOCUMENT,
    "document": EventKeyV2.CONTRACT_DOCUMENT,
    "wealth_change": EventKeyV2.WEALTH_CHANGE,
    "income_change": EventKeyV2.WEALTH_CHANGE,
    "expense_risk": EventKeyV2.WEALTH_CHANGE,  # 손실[loss]
    "windfall": EventKeyV2.WINDFALL,
    "speculation_risk": EventKeyV2.WEALTH_CHANGE,  # 투기[loss]
    "asset_volatility": EventKeyV2.WEALTH_CHANGE,  # 변동[loss]
    "education_start": EventKeyV2.EDUCATION_ADMISSION,
    "education_complete": EventKeyV2.EDUCATION_COMPLETION,
    "exam": EventKeyV2.EDUCATION_ADMISSION,
    "health_issue": EventKeyV2.HEALTH_ATTENTION,
    "surgery": EventKeyV2.HEALTH_ATTENTION,
    "family_change": EventKeyV2.RELATIONSHIP_CHANGE,
    "lawsuit": EventKeyV2.LEGAL_CONFLICT,
    "travel": EventKeyV2.RELOCATION,
}

# ── 금기 표현 규칙 (절대 원칙 3·8) — public_exposure 경쟁 보호 신규 추가 ──
PROHIBITIONS: list[tuple[str, str, list[str]]] = [
    ("prohibit_windfall", "당첨·횡재 단정 금지, 로또 번호 생성 거부, 투기 과몰입 경고",
     [EventKeyV2.WINDFALL.value]),
    ("prohibit_finance", "투자 손익 보장 없음 고지(투자 조언 아님)",
     [EventKeyV2.WEALTH_CHANGE.value]),
    ("prohibit_medical", "의료 조언 아님 고지, 수술·질병 시기 단정 금지",
     [EventKeyV2.HEALTH_ATTENTION.value]),
    ("prohibit_exam", "합격·당락 단정 금지(상대 우열 + 준비도·근거까지만)",
     [EventKeyV2.EDUCATION_ADMISSION.value]),
    ("prohibit_competition", "경쟁(오디션·대회·선거) 승부 단정 금지(상대 우열 + 근거까지만)",
     [EventKeyV2.PUBLIC_EXPOSURE.value]),
    ("prohibit_legal", "법률 조언 아님 고지, 승소·판결 단정 금지",
     [EventKeyV2.LEGAL_CONFLICT.value]),
]

# ── 질의 키워드 (실로그 — 진급·평가·오디션·대회·고시·자격증 포함) ──
EVENT_WORDS: dict[EventKeyV2, list[str]] = {
    EventKeyV2.CAREER_CHANGE: ["이직", "퇴사"],
    EventKeyV2.JOB_GAIN: ["취업", "취직", "입사", "채용", "재취업", "구직", "복직", "일자리"],
    EventKeyV2.PROMOTION: ["승진", "진급", "평가", "고과", "인사"],
    EventKeyV2.BUSINESS_START: ["창업", "개업", "사업 시작"],
    EventKeyV2.BUSINESS_EXPANSION: ["사업 확장", "분점", "확장"],
    EventKeyV2.WEALTH_CHANGE: ["재물", "수입", "지출", "투자"],
    EventKeyV2.WINDFALL: ["로또", "복권", "횡재"],
    EventKeyV2.CONTRACT_DOCUMENT: ["계약", "문서"],
    EventKeyV2.EDUCATION_ADMISSION: ["국가고시", "자격증", "시험", "합격", "입시", "입학", "진학"],
    EventKeyV2.EDUCATION_COMPLETION: ["졸업", "수료"],
    EventKeyV2.RELATIONSHIP_CHANGE: ["이별", "헤어", "권태"],
    EventKeyV2.NEW_RELATIONSHIP: ["연애", "소개팅", "인연"],
    EventKeyV2.MARRIAGE_SIGNAL: ["결혼", "재혼"],
    EventKeyV2.CHILDBIRTH: ["출산", "임신", "자녀가 있을지"],
    EventKeyV2.RELOCATION: ["이사", "이동수", "여행", "해외 이동"],
    EventKeyV2.LEGAL_CONFLICT: ["소송", "고소", "법적"],
    EventKeyV2.HEALTH_ATTENTION: ["건강", "수술", "병원"],
    EventKeyV2.SOCIAL_CONFLICT: ["갈등", "다툼", "구설"],
    EventKeyV2.CREATIVE_OUTPUT: ["작품", "프로젝트", "성과물"],
    EventKeyV2.PUBLIC_EXPOSURE: ["오디션", "대회", "경연", "선거", "공개 발표"],
}

# ── 택일(date selection) 대상 — 즉효/실행일 성격 이벤트 ──
DATE_PURPOSES: set[EventKeyV2] = {
    EventKeyV2.RELOCATION,
    EventKeyV2.CONTRACT_DOCUMENT,
    EventKeyV2.MARRIAGE_SIGNAL,
    EventKeyV2.BUSINESS_START,
    EventKeyV2.WINDFALL,
    EventKeyV2.HEALTH_ATTENTION,
}

# ── 새 출력 차원 한글 라벨 (LLM 입력 톤 힌트) ──────────────────────
QUALITY_KO: dict[EventQuality, str] = {
    EventQuality.OPPORTUNITY: "기회",
    EventQuality.PRESSURE: "압박·부담",
    EventQuality.LOSS: "손실·지출",
    EventQuality.DELAY: "지연·보류",
    EventQuality.CONFLICT: "갈등",
    EventQuality.ACHIEVEMENT: "성취·인정",
    EventQuality.RESOLUTION: "해소·정리",
    EventQuality.MIXED: "혼재·변동",
}
CONFIDENCE_KO: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.THEME_ONLY: "주제·분위기",
    ConfidenceLevel.WEAK_EVENT_CANDIDATE: "약한 사건 후보",
    ConfidenceLevel.EVENT_CANDIDATE: "사건 후보",
    ConfidenceLevel.STRONG_EVENT_CANDIDATE: "강한 사건 후보",
    ConfidenceLevel.HIGH_PROBABILITY_EVENT: "높은 확률",
}
TEMPORAL_KO: dict[TemporalMode, str] = {
    TemporalMode.LONG_TERM: "장기",
    TemporalMode.MEDIUM_TERM: "중기",
    TemporalMode.IMMEDIATE: "즉시",
}
PALACE_KO: dict[Pillar4, str] = {
    Pillar4.YEAR: "년주(가족·배경)",
    Pillar4.MONTH: "월주(직업·사회)",
    Pillar4.DAY: "일주(배우자·거처)",
    Pillar4.HOUR: "시주(자녀·결과)",
}


def event_ko_v2(key: EventKeyV2 | str) -> str:
    """EventKeyV2(또는 문자열) → 한글 라벨(미정의 시 키 그대로)."""
    try:
        k = key if isinstance(key, EventKeyV2) else EventKeyV2(key)
    except ValueError:
        return str(key)
    return EVENT_KO.get(k, str(key))

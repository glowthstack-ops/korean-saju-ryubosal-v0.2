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
    EventTiming,
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

# ── 채널 중립 의미 facet (2026-07-30 데굴님 확정 — 가′) ──────────────
#
# 리포트 섹션이 사건을 라우팅할 때 쓰는 **의미 속성**이다. `event_key` 를 보고 섹션
# 계층이 단계를 재추론하면 drift 가 생기므로, 여기서만 정의하고 대화·리포트·후보
# 감사가 공유한다. 출력 채널에 종속되지 않는다.
#
# 불변식:
#   - 점수·favorable/adverse·confidence·성사 판정에 관여하지 않는다(라우팅 메타데이터).
#   - 모르는 축은 `UNKNOWN` 으로 두고 fail-closed 한다 — 넓은 사건군에 임의 편입 금지.
#   - fail-closed 는 **축 단위**다. `WEALTH_CHANGE` 는 family 는 알지만 subtype 은
#     모르므로 family 만 쓰고 subtype 은 UNKNOWN 이다.
#   - `stage_tags` 는 기존 SSOT(관계 로드맵·커리어 트랙)가 부여한 값만 쓴다. 이름만
#     보고 추론하지 않는다 — 현재 리포에 확정 매핑이 없으므로 전부 비어 있다.
FACET_UNKNOWN = "UNKNOWN"

#: 무엇에 관한 사건인가.
EVENT_FAMILY: dict[EventKeyV2, str] = {
    EventKeyV2.WEALTH_CHANGE: "wealth_change",
    EventKeyV2.WINDFALL: "windfall",
    EventKeyV2.CAREER_CHANGE: "career_transition",
    EventKeyV2.JOB_GAIN: "employment",
    EventKeyV2.PROMOTION: "advancement",
    EventKeyV2.BUSINESS_START: "entrepreneurship",
    EventKeyV2.BUSINESS_EXPANSION: "entrepreneurship",
    EventKeyV2.CONTRACT_DOCUMENT: "contract_document",
    EventKeyV2.PREPARATION_DELAY: "delay",
    EventKeyV2.LEGAL_CONFLICT: "legal_dispute",
    EventKeyV2.SOCIAL_CONFLICT: "social_conflict",
    EventKeyV2.CREATIVE_OUTPUT: "creative_output",
    EventKeyV2.PUBLIC_EXPOSURE: "visibility",
    EventKeyV2.NEW_RELATIONSHIP: "new_relationship",
    EventKeyV2.RELATIONSHIP_CHANGE: "relationship_change",
    EventKeyV2.MARRIAGE_SIGNAL: "marriage_signal",
    EventKeyV2.RELOCATION: "relocation",
}

#: 과정에서 어떤 역할인가. 확정되지 않은 키는 `UNKNOWN`.
EVENT_PROCESS_ROLE: dict[EventKeyV2, str] = {
    EventKeyV2.WEALTH_CHANGE: FACET_UNKNOWN,   # 수입·지출·정산·자산이동 미분화
    EventKeyV2.WINDFALL: "unexpected_gain",
    EventKeyV2.CAREER_CHANGE: "transition",
    EventKeyV2.JOB_GAIN: "entry",
    EventKeyV2.PROMOTION: "advancement",
    EventKeyV2.BUSINESS_START: "initiation",
    EventKeyV2.BUSINESS_EXPANSION: "expansion",
    EventKeyV2.CONTRACT_DOCUMENT: "agreement",
    EventKeyV2.PREPARATION_DELAY: "delay",
    EventKeyV2.LEGAL_CONFLICT: "conflict",
    EventKeyV2.SOCIAL_CONFLICT: "conflict",
    EventKeyV2.CREATIVE_OUTPUT: "production",
    EventKeyV2.PUBLIC_EXPOSURE: "exposure",
    EventKeyV2.NEW_RELATIONSHIP: "initiation",
    EventKeyV2.RELATIONSHIP_CHANGE: "transition",
    EventKeyV2.MARRIAGE_SIGNAL: FACET_UNKNOWN,  # 공식화 단계 확정 매핑 부재
    EventKeyV2.RELOCATION: "movement",
}

#: 로드맵 단계. 기존 SSOT 가 부여한 값만 담는다 — 현재 확정 매핑이 없어 비어 있다.
#: 비워 두는 것이 계약이다. 세 관계 키를 6단계에 강제 배분하지 않는다.
EVENT_STAGE_TAGS: dict[EventKeyV2, tuple[str, ...]] = {}


#: 문자열 키 조회용 미러(EventKeyV2 는 StrEnum 이지만 타입 검사를 위해 분리).
_FAMILY_BY_STR: dict[str, str] = {str(k): v for k, v in EVENT_FAMILY.items()}
_ROLE_BY_STR: dict[str, str] = {str(k): v for k, v in EVENT_PROCESS_ROLE.items()}
_STAGE_BY_STR: dict[str, tuple[str, ...]] = {
    str(k): v for k, v in EVENT_STAGE_TAGS.items()
}


def event_facets(event_key: str) -> dict[str, object]:
    """사건 1건의 채널 중립 facet. 모르는 축은 `UNKNOWN`/빈 튜플로 낸다.

    Args:
        event_key: canonical event key 문자열.

    Returns:
        `event_family` · `process_role` · `stage_tags` · `subtype`.
        미등록 키는 family 까지 UNKNOWN 이므로 세부 라우팅에서 제외된다.
    """
    return {
        "event_family": _FAMILY_BY_STR.get(event_key, FACET_UNKNOWN),
        "process_role": _ROLE_BY_STR.get(event_key, FACET_UNKNOWN),
        "stage_tags": _STAGE_BY_STR.get(event_key, ()),
        # 세부 유형은 이번 배포에서 만들지 않는다(사전 분화는 별건).
        "subtype": FACET_UNKNOWN,
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
    EventKeyV2.RELATIONSHIP_CHANGE: ["이별", "헤어", "권태", "이혼", "별거", "파혼"],
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

# ── 새 출력 차원 한글 라벨 (사용자 노출 — 사건 '방향'을 또렷이) ──────────────────
# 사건명은 중립으로 두고 이 라벨로 길흉 방향을 명시한다("좋은지 나쁜지" 모호함 해소).
QUALITY_KO: dict[EventQuality, str] = {
    EventQuality.OPPORTUNITY: "기회·유입",
    EventQuality.ACHIEVEMENT: "성취·결실",
    EventQuality.RESOLUTION: "해소·정리",
    EventQuality.PRESSURE: "압박·부담",
    EventQuality.LOSS: "손실·지출",
    EventQuality.CONFLICT: "갈등·마찰",
    EventQuality.MIXED: "혼합(좋은 면·주의할 면 공존)",
    EventQuality.DELAY: "지연·보류",  # deprecated(미생산) — 하위호환 표기만
}
# 시간 작동 방식 — 방향(quality)과 독립. delay는 방향 라벨 뒤에 덧붙인다("기회·유입 · 지연").
TIMING_KO: dict[EventTiming, str] = {
    EventTiming.ACTIVE: "",
    EventTiming.DELAY: "지연·보류",
}


def direction_label(quality: str | None, timing: str = "active") -> str:
    """사건 방향(길흉) + 타이밍 → 사용자 표시 라벨. 예: '기회·유입 · 지연', '손실·지출'.

    방향(quality)도 타이밍(delay)도 없으면 빈 문자열(중립). polarity 4값("조건부") 축소를
    대체해 "좋은지 나쁜지"를 또렷이 전달한다. 입력은 enum value 문자열(legacy 후보 호환).
    """
    q = ""
    if quality:
        try:
            q = QUALITY_KO.get(EventQuality(quality), "")
        except ValueError:
            q = ""
    t = ""
    if timing:
        try:
            t = TIMING_KO.get(EventTiming(timing), "")
        except ValueError:
            t = ""
    if q and t:
        return f"{q} · {t}"
    return q or t
# ── 의미 별칭(중장기 마이그레이션 준비, 2026-07-22 데굴님 확정) ─────────────────
# canonical 키는 당분간 유지(저장 데이터·fixture·통계·캐시 호환). 표시 계층은 이미
# 방향 인지 라벨(_DIRECTION_DISPLAY)로 중립화됨. 후속 마이그레이션 시 taxonomy version
# 필드 + 구→신 alias + 읽기 호환 + 통계 통합 + fixture 재생성 + (외부 API 시) deprecation
# 기간이 필요하며, 장기적으로는 부모(SUDDEN_FINANCIAL_CHANGE)-자식(UNEXPECTED_INFLOW/
# OUTFLOW/SETTLEMENT_DELAY/VOLATILE) 구조를 검토한다. 과거의 진짜 긍정 횡재 데이터 의미가
# 바뀌지 않도록 rename이 아니라 alias로 간다.
EVENT_SEMANTIC_ALIAS: dict[EventKeyV2, str] = {
    EventKeyV2.WINDFALL: "sudden_financial_change",
}


# ── 결과 방향 파생축(P1 lite, 2026-07-22 데굴님 확정) ─────────────────────────
# quality 하나에 뭉쳐 있던 '결과 방향'과 '경험 품질'을 표시·서술용으로 분리한다(점수·판정
# 불변). pressure는 결과가 아니라 경험 품질(부담)이므로 결과 방향은 '활성화만'으로 본다 —
# '합격+부담'을 실패로 격하하지 않는다(§3 승인). timing=delay는 결과 방향에 우선한다.
def result_direction(quality: str | None, timing: str = "active") -> str:
    """후보의 결과 방향 파생 — 'positive'|'negative'|'delay'|'activation'|'unknown'."""
    if timing == "delay":
        return "delay"
    if quality in ("opportunity", "achievement", "resolution"):
        return "positive"
    if quality in ("loss", "conflict"):
        return "negative"
    if quality == "pressure":
        return "activation"  # 주제 활성화 + 경험 부담(방향 라벨이 압박·부담을 병기)
    return "unknown"  # mixed/None — 중립 국면


# 방향 인지 표시 라벨(2026-07-22 데굴님 감수 문안) — 방향 함의가 있는 이벤트명이 반대
# 방향 quality와 결합해 모순 표기('횡재+손실')가 되는 것을 차단한다. 'neutral'은
# activation/unknown 공용(국면·변동형 중립 라벨). 미등재 키는 EVENT_KO 그대로.
_DIRECTION_DISPLAY: dict[EventKeyV2, dict[str, str]] = {
    EventKeyV2.WINDFALL: {
        "positive": "뜻밖의 수입·수익 기회",
        "negative": "예상 밖 지출·손실 위험",
        "delay": "수령·정산 지연 가능성",
        "neutral": "돌발 금전 변동",
    },
    EventKeyV2.JOB_GAIN: {
        "positive": "취업 성사 가능성",
        "negative": "구직·채용 난항",
        "delay": "채용 결정 지연",
        "neutral": "구직·채용 국면",
    },
    EventKeyV2.EDUCATION_ADMISSION: {
        "positive": "합격·진학 가능성",
        "negative": "시험·선발 난항",
        "delay": "발표·진행 지연",
        "neutral": "시험·학업 관련 변동",
    },
    EventKeyV2.PROMOTION: {
        "positive": "승진·평가 기회",
        "negative": "평가 압박·승진 난항",
        "delay": "승진·보상 결정 지연",
        "neutral": "승진·평가 국면",
    },
    EventKeyV2.NEW_RELATIONSHIP: {
        "positive": "새로운 인연 가능성",
        "negative": "관계 불안정",
        "delay": "관계 진전 지연",
        "neutral": "인연 접점",
    },
    EventKeyV2.MARRIAGE_SIGNAL: {
        "positive": "혼인 구체화",
        "negative": "혼인 논의 부담",
        "delay": "혼인 결정 지연",
        "neutral": "혼인 논의 국면",
    },
}


def event_display_ko(
    event_key: str, quality: str | None = None, timing: str = "active"
) -> str:
    """사용자 표시용 사건 라벨 — 방향 함의 이벤트는 결과 방향에 맞춰 치환(판정·점수 불변).

    '횡재'는 결과가 긍정으로 확정된 경우에만 쓴다(데굴님 확정). activation(주제 활성화만)과
    unknown(혼합·미확정)은 중립 국면 라벨을 공유하며, 경험 품질(압박·부담 등)은 방향 라벨
    열이 병기한다. 미등재 키는 EVENT_KO 폴백.
    """
    try:
        key = EventKeyV2(event_key)
    except ValueError:
        return event_key
    table = _DIRECTION_DISPLAY.get(key)
    if table is None:
        return EVENT_KO.get(key, event_key)
    d = result_direction(quality, timing)
    if d in ("activation", "unknown"):
        return table["neutral"]
    return table[d]


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

"""신살 보정 레이어 config — 위치·도메인·운층·생애단계·재활성화·강도밴드 상수.

doc/v2_2/SINSAL_MODIFIER_SPEC.md 의 초기 기본값(initial_default)을 한곳에 집약한다.
**확정값이 아니라 튜닝 대상**(용신 operational_role_config 선례) — shadow 로그·사례 검증으로 조정.

Phase A 원칙: 이 수치는 LLM payload 에 직접 노출하지 않는다(§9). 내부 weight → 한글 강도어로만.
신살은 보조 레이어 — event_score/favorability/용신 판정을 바꾸지 않는다(§2).
"""

from __future__ import annotations

# ── §4 위치별 작동범위(scope)·기본 가중치·직접성·해석모드 ──
PILLAR_SCOPE: dict[str, list[str]] = {
    "year": ["ancestry", "early_life", "family_background", "outer_reputation", "distant_network"],
    "month": ["career", "organization", "parents", "social_role", "workplace", "public_activity"],
    "day": ["self", "body", "spouse", "relationship", "daily_reality", "core_decision"],
    "hour": ["children", "subordinates", "future", "late_life", "output", "long_term_project"],
}
PILLAR_DEFAULT_WEIGHT: dict[str, float] = {"year": 0.60, "month": 0.90, "day": 1.00, "hour": 0.75}
PILLAR_EVENT_DIRECTNESS: dict[str, float] = {"year": 0.45, "month": 0.85, "day": 1.00, "hour": 0.70}
PILLAR_INTERP_MODE: dict[str, str] = {
    "year": "background", "month": "social_reality", "day": "core_life", "hour": "future_result",
}
# §7 GENERAL 흡수용 궁성/서브도메인 태그(Domain enum 불변).
PILLAR_PALACE_TAGS: dict[str, list[str]] = {
    "year": ["year_pillar", "ancestry", "reputation"],
    "month": ["month_pillar", "career", "organization"],
    "day": ["day_pillar", "self", "spouse"],
    "hour": ["hour_pillar", "children", "late_life", "project_output"],
}

# §4 천간/지지/지장간 layer + 지지 위치 가중(파생 산출 보조 — Phase A 내부값).
POSITION_LAYER_WEIGHT: dict[str, float] = {"stem": 0.45, "branch": 1.00, "hidden_stem": 0.35}
BRANCH_SPECIAL_WEIGHT: dict[str, float] = {
    "month_branch": 1.15, "day_branch": 1.20, "year_branch": 0.75, "hour_branch": 0.85,
}

# ── §7 도메인별 위치 가중(domain_override) — 실제 Domain enum 값 키 ──
# children/late_life/project 는 enum 미존재 → GENERAL + palace_tags(§7).
DOMAIN_OVERRIDE: dict[str, dict[str, float]] = {
    "career": {"year": 0.55, "month": 1.00, "day": 0.80, "hour": 0.65},
    "relationship": {"year": 0.40, "month": 0.70, "day": 1.00, "hour": 0.60},
    "health": {"year": 0.45, "month": 0.75, "day": 1.00, "hour": 0.70},
    "wealth": {"year": 0.50, "month": 0.90, "day": 0.85, "hour": 0.75},
    "relocation": {"year": 0.55, "month": 0.90, "day": 0.95, "hour": 0.75},
    "education": {"year": 0.45, "month": 0.90, "day": 0.85, "hour": 0.80},
    # general 은 DOMAIN_OVERRIDE 미수록 → PILLAR_DEFAULT_WEIGHT 사용.
}
# domain_match 판정 임계 — 그 도메인에서 위치 가중이 이 값 이상이면 궁성 정렬로 본다(§7).
DOMAIN_MATCH_THRESHOLD = 0.85

# ── §5 운층(source)별 작동 강도 ──
SOURCE_EVENT_POWER: dict[str, str] = {
    "natal": "low_to_medium",
    "daewoon": "medium",
    "yearly": "medium_to_high",
    "monthly": "high_if_supported",
    "daily": "trigger_only",
}

# ── §8 생애단계 밴드(나이 fallback) + 주별 생애단계 곡선(weight shape: 길성·흉살 공통) ──
LIFE_STAGE_AGE_BANDS: list[tuple[str, int, int]] = [
    ("childhood", 0, 15),
    ("youth", 16, 30),
    ("middle", 31, 45),
    ("late", 46, 200),
]
LIFE_STAGE_ORDER: list[str] = ["childhood", "youth", "middle", "late"]
# (pillar, stage) -> (mode, weight). mode: seed | emerging | direct | background | accumulated.
LIFE_STAGE_CURVE: dict[str, dict[str, tuple[str, float]]] = {
    "year": {
        "childhood": ("direct", 0.80), "youth": ("background", 0.55),
        "middle": ("background", 0.55), "late": ("accumulated", 0.45),
    },
    "month": {
        "childhood": ("seed", 0.50), "youth": ("direct", 0.90),
        "middle": ("direct", 0.90), "late": ("accumulated", 0.60),
    },
    "day": {
        "childhood": ("seed", 0.40), "youth": ("emerging", 0.70),
        "middle": ("direct", 1.00), "late": ("accumulated", 0.65),
    },
    "hour": {
        "childhood": ("seed", 0.35), "youth": ("seed", 0.35),
        "middle": ("emerging", 0.65), "late": ("direct", 0.85),
    },
}
# 모드별 한글 라벨(길성=자산 / 흉살=리스크 의미 분기) — effect 서술 보조.
LIFE_STAGE_MODE_KO: dict[str, dict[str, str]] = {
    "positive": {
        "seed": "잠재 자산(늦게 발현)", "emerging": "발현 시작", "direct": "직접 도움",
        "background": "배경 자산", "accumulated": "누적 자산",
    },
    "caution": {
        "seed": "잠재 성향(미발현)", "emerging": "긴장 시작", "direct": "직접 발현(주의)",
        "background": "배경 리스크", "accumulated": "체화·잔존 패턴",
    },
}

# ── §8-3 재활성화 ──
REACTIVATION_WEIGHT_BOOST = 0.25
# relations_to_chart 접두(형충회합/합) — 운이 원국 글자를 건드림 = 재활성화 트리거.
REACTIVATION_RELATION_PREFIXES: tuple[str, ...] = (
    "충", "육합", "파", "해", "무례지형", "천간합",
    "삼합완성", "반합성립", "방합완성", "자형", "삼형",
)

# ── payload pruning(가드) — 후보당 노출 상한·도메인 비정렬/년주 배경 캡 ──
SINSAL_PAYLOAD_MAX_PER_EVENT = 3
# natal 신살은 도메인 레벨(모든 후보 동일) → 토큰 절약 위해 상위 N개 후보에만 부착.
SINSAL_PAYLOAD_MAX_CANDIDATES = 2
SINSAL_PAYLOAD_MAX_DOMAIN_UNMATCHED = 1  # domain_match=False 최대 노출
SINSAL_PAYLOAD_MAX_YEAR_BACKGROUND = 1  # 년주 background 길성/흉살 최대 노출
# 위치 → 직렬화용 짧은 궁성 라벨(payload 텍스트).
PALACE_SHORT_LABEL: dict[str, str] = {
    "year": "년주", "month": "월주(사회궁)", "day": "일주", "hour": "시주",
}

# ── §9 강도 밴드(internal_weight → LLM 한글 강도어) ──
STRENGTH_BANDS: list[tuple[float, str]] = [
    (0.80, "매우 강함"),
    (0.55, "강함"),
    (0.25, "보조"),
    (0.00, "약함"),
]

# ── §6 효과 태그(한글, 숫자 없음) — 명명 신살 override, 그 외 catalog tags fallback ──
# 길성 = 완충·도움·회복 / 흉살 = 리스크·긴장·주의 / 중립 = 변동·매력 등.
EFFECT_TAGS: dict[str, list[str]] = {
    "천을귀인": ["위기 완화·도움 가능성", "귀인·해결자"],
    "천덕귀인": ["큰 흉 감소·보호"],
    "월덕귀인": ["인복·사회적 완충"],
    "태극귀인": ["통찰·복록"],
    "문창귀인": ["학습·문서·기획 강화"],
    "학당귀인": ["학습·교육 성과"],
    "관귀학관": ["시험·승진 신호"],
    "금여": ["생활 안정·배우자 복"],
    "암록": ["숨은 조력·비공식 지원"],
    "천의성": ["치유·회복 도움"],
    "역마살": ["이동·변동성 강화"],
    "도화": ["매력·인기·노출"],
    "홍염": ["매력·끼"],
    "화개살": ["고독·전문성 심화"],
    "백호": ["급성 변수·주의(충형 동반 시 강화)"],
    "양인": ["경쟁·긴장·결단"],
    "괴강": ["강단·권위·극단성"],
    "겁살": ["손실·경쟁 변수 주의"],
    "재살": ["관재·압박 주의"],
    "천살": ["통제 어려운 외부 변수"],
    "귀문관살": ["예민·집착·심리 긴장"],
    "원진": ["미묘한 불화·정서 어긋남"],
    "고신살": ["고독·지연"],
    "과숙살": ["고독·이별"],
    "망신살": ["체면·구설 주의"],
}
# 명명 없는 신살의 polarity 기본 효과 프레이밍.
POLARITY_DEFAULT_EFFECT: dict[str, str] = {
    "positive": "도움·완충",
    "caution": "리스크·긴장 주의",
    "neutral": "변동·특수성",
}

# ── Phase B-1 v2: 신살 채널 shadow sidecar (운영 불변·관측 전용) ──
# 발생 가능성(occurrence_score)은 절대 미반영(=0). 길흉·리스크·완충·질감 채널만 관측한다(§10-1b).
# 마스터 게이트 — off면 sidecar 미산출(byte-identical). 용신 operational shadow 게이트 선례.
SINSAL_NUMERIC_SHADOW_ENABLED = False
SINSAL_NUMERIC_REACT_BOOST = 1.25  # 기간 재활성화 시 기여 가중(§8-3)
# 채널 계수는 0~1 분수 스케일(§6). 길성=mitigation(완충·도움)·favorability(+),
# 흉살=risk(마찰·리스크)·favorability(−). 위치/intent 가중(DOMAIN_OVERRIDE)·재활성 boost 곱.
SINSAL_CHANNEL_AUSPICIOUS: dict[str, dict[str, float]] = {
    "천을귀인": {"mitigation": 0.15, "favorability": 0.08},
    "천덕귀인": {"mitigation": 0.18, "favorability": 0.06},
    "월덕귀인": {"mitigation": 0.12, "favorability": 0.07},
    "태극귀인": {"mitigation": 0.10, "favorability": 0.06},
    "문창귀인": {"mitigation": 0.08, "favorability": 0.05},
    "학당귀인": {"mitigation": 0.08, "favorability": 0.05},
    "금여": {"mitigation": 0.10, "favorability": 0.06},
    "암록": {"mitigation": 0.10, "favorability": 0.05},
    "천의성": {"mitigation": 0.12, "favorability": 0.05},
}
SINSAL_CHANNEL_AUSPICIOUS_DEFAULT: dict[str, float] = {"mitigation": 0.10, "favorability": 0.05}
SINSAL_CHANNEL_INAUSPICIOUS: dict[str, dict[str, float]] = {
    "백호": {"risk": 0.15, "favorability": -0.05},
    "양인": {"risk": 0.12, "favorability": -0.04},
    "괴강": {"risk": 0.12, "favorability": -0.04},
    "겁살": {"risk": 0.12, "favorability": -0.04},
    "재살": {"risk": 0.12, "favorability": -0.04},
    "귀문관살": {"risk": 0.12, "favorability": -0.04},
    "원진": {"risk": 0.10, "favorability": -0.04},
    "망신살": {"risk": 0.08, "favorability": -0.03},
}
SINSAL_CHANNEL_INAUSPICIOUS_DEFAULT: dict[str, float] = {"risk": 0.10, "favorability": -0.04}
# 중립(방향성) 신살 → 질감 태그(숫자 0). 역마·도화·화개·홍염 등.
SINSAL_CHANNEL_TEXTURE: dict[str, str] = {
    "역마살": "이동·변동성", "지살": "이동·시작",
    "도화": "노출·관계·인기", "년살": "도화·매력", "홍염": "매력·끼",
    "화개살": "고립·전문성·마무리",
}
# 채널 클램프(0~1 분수, 보조 보장 — 길성이 길흉을 뒤집지 못하게, §2-3).
SINSAL_CHANNEL_CAPS: dict[str, float] = {"favorability": 0.12, "risk": 0.20, "mitigation": 0.20}
# shadow WARN 임계 — max(|fav|, risk, mit) 이 값 이상이면 리뷰 대상.
SINSAL_CHANNEL_WARN = 0.10

# ── Phase B-2: 채널 운영 반영(리포트 경로) — 챗은 토큰 천장으로 제외(§10-2). ──
# 채널 색채 노트를 리포트 기간 클러스터에 부착. off면 미부착(롤백 1줄). occurrence/ranking 불변.
SINSAL_CHANNEL_APPLY_ENABLED = True
# 채널값 → 한글 강도어 밴드(숫자 미노출, §9). (임계, 라벨) 내림차순.
SINSAL_CHANNEL_MIT_BANDS: list[tuple[float, str]] = [(0.15, "완충 큼"), (0.07, "완충 있음")]
SINSAL_CHANNEL_RISK_BANDS: list[tuple[float, str]] = [(0.15, "리스크 큼"), (0.07, "리스크 주의")]
SINSAL_CHANNEL_FAV_POS_BANDS: list[tuple[float, str]] = [(0.06, "유리한 색채")]
SINSAL_CHANNEL_FAV_NEG_BANDS: list[tuple[float, str]] = [(0.06, "부담스러운 색채")]

# 금지 해석(전 주·전 극성, §8-3) — LLM 지시문/검증용 참조.
BLOCKED_INTERPRETATIONS: list[str] = [
    "그 시기에만 작동하고 끝난다",
    "비정점 시기에 직접 사건 단독 생성",
    "길성이 흉운을 완전히 제거",
    "흉살이 반드시 사고/실패를 만든다",
]


def strength_band(weight: float) -> str:
    """internal_weight(0~) → 한글 강도어(§9). 밴드 경계는 STRENGTH_BANDS."""
    for threshold, label in STRENGTH_BANDS:
        if weight >= threshold:
            return label
    return "약함"

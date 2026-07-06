"""관계유형 추론 + 관점 힌트 (동반자 공동 풀이 P3a — additive).

pairwise/companion_only에서 두 사람의 관계 유형을 추론해, LLM에 '어느 영역을 볼지' 관점
힌트만 제공한다. 점수화·궁합 점수·우열·승패는 만들지 않는다(관점 제어 전용). 추론 우선순위:
사용자 명시 키워드 > companion relation_to_user > intent/domain > unknown(질문이 등록관계보다 우선).
"""

from __future__ import annotations

import re

# 관계 유형. competition/ranking은 P3c 이후.
# 2026-07-03 확장(데굴님 지시 — 테마 애정·관계운 관계 명시 선택): 애정 단계 세분
# (crush 썸/fiance 결혼예정/divorcing 이혼예정/affair 외도)과 위계 사회관계(boss/subordinate).
# 키워드 추론(_KEYWORD_RULES)은 기존 그대로 — 신규 값은 사용자의 '명시 선택'(테마 상대
# 선택·등록 관계)으로만 들어온다(추론 확장은 실사용 후 후속).
RELATION_TYPES: tuple[str, ...] = (
    "spouse", "romance", "crush", "fiance", "divorcing", "affair",
    "parent_child", "family", "friend",
    "coworker", "boss", "subordinate", "business_partner", "unknown",
)

# 표시 라벨(FE 선택지·리포트 블록 공용).
RELATION_KO: dict[str, str] = {
    "spouse": "배우자(기혼)", "romance": "연인", "crush": "썸·호감 단계",
    "fiance": "결혼 예정(약혼)", "divorcing": "이혼 예정·진행 중", "affair": "외도 관계",
    "parent_child": "부모·자녀", "family": "가족·친척", "friend": "친구",
    "coworker": "직장 동료", "boss": "상사", "subordinate": "부하 직원",
    "business_partner": "사업 파트너", "unknown": "미지정",
}

# ① 사용자 명시 키워드 → 관계유형(우선순위 순 — 더 구체적인 것 먼저).
_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"동업|공동\s*창업|같이\s*사업|사업\s*파트너|동업자"), "business_partner"),
    (re.compile(
        r"직장\s*동료|회사\s*동료|동료|상사|부하\s*직원|업무\s*파트너|직장에서"
    ), "coworker"),
    (re.compile(r"부부|배우자|남편|아내|와이프|집사람|결혼\s*생활|혼인"), "spouse"),
    (re.compile(r"연애|썸|사귀|이성|남자\s*친구|여자\s*친구|애인|연인"), "romance"),
    (re.compile(
        r"부모|엄마|어머니|아빠|아버지|자식|아들|딸|모자|부자(?:\s*관계)?"
    ), "parent_child"),
    (re.compile(r"형제|자매|남매|가족|친척"), "family"),
    (re.compile(r"친구|벗|절친"), "friend"),
]

# ② companion relation_to_user → 관계유형.
_RELATION_TO_USER: dict[str, str] = {
    "spouse": "spouse", "husband": "spouse", "wife": "spouse",
    "father": "parent_child", "mother": "parent_child", "parent": "parent_child",
    "son": "parent_child", "daughter": "parent_child", "child": "parent_child",
    "sibling": "family", "brother": "family", "sister": "family",
    "friend": "friend", "coworker": "coworker", "business_partner": "business_partner",
    # 2026-07-03 확장 — 테마 관계 선택 값 그대로 저장·전달되는 경우(identity).
    "romance": "romance", "crush": "crush", "fiance": "fiance",
    "divorcing": "divorcing", "affair": "affair",
    "boss": "boss", "subordinate": "subordinate",
    "parent_child": "parent_child", "family": "family",
}

# 관계유형별 관점 힌트(LLM 관점 제어 — 점수 아님).
PERSPECTIVE_HINTS: dict[str, list[str]] = {
    "spouse": [
        "생활 리듬", "정서 안정", "재물·거주 의사결정", "갈등 조절 방식", "장기적 책임 분담",
    ],
    "romance": ["끌림과 거리감", "표현 방식", "관계 속도", "감정 기복", "연애 지속성"],
    "parent_child": ["보호와 독립", "기대치 충돌", "교육·진로 관점", "생활 리듬", "정서적 부담"],
    "family": ["가족 내 역할", "정서적 거리", "도움과 부담", "생활 습관", "갈등 완충"],
    "friend": ["편안함", "신뢰감", "거리 조절", "소통 방식", "오래 가는 관계성"],
    "coworker": ["업무 역할", "협업 방식", "책임 분배", "성과 압박", "커뮤니케이션"],
    "business_partner": ["금전 흐름", "역할 분담", "책임 소재", "리스크 감수", "의사결정 충돌"],
    "crush": ["끌림의 신호", "다가서는 속도", "표현 방식", "상대의 온도", "시작 타이밍"],
    "fiance": ["결혼 준비 흐름", "가치관·생활 조율", "양가·현실 문제", "결혼 시기", "재물 합류"],
    "divorcing": ["정리 vs 회복의 결", "감정 소모", "재산·생활 분리", "결정 시기", "회복 탄력"],
    "affair": ["감정의 실체", "신뢰·현실 리스크", "관계의 지속 가능성", "생활 파장", "선택의 갈림"],
    "boss": ["위계 속 소통", "인정과 평가", "업무 지시 결", "갈등 완충", "성장 기회"],
    "subordinate": ["위임과 신뢰", "지도 방식", "책임 분배", "동기 부여", "관계 거리"],
    "unknown": ["상호 성향", "소통 방식", "갈등 요인", "도움이 되는 지점", "조율 포인트"],
}

# 관계별 풀이 방향(리포트 궁합 RP-* 프레이밍 — 서술 방식 전용, 점수·판정 불변).
# 애정 단계별 톤 분리 + 사회 관계는 연애 전제 제거. affair는 조장·비난 없이 현실 리스크 동반.
RELATION_FRAMING: dict[str, str] = {
    "spouse": "이미 결혼한 부부다 — '새 인연·시작' 프레임이 아니라 결혼 생활의 운영"
              "(권태 회복·역할 분담·재물과 거주 결정)을 중심으로 풀 것.",
    "romance": "교제 중인 연인이다 — 관계의 진전·안정·갈등 조절을 중심으로 풀고, 결혼"
               " 이야기는 단정 없이 흐름으로만 다룰 것.",
    "crush": "아직 시작 전(썸·호감) 단계다 — 다가설 타이밍과 표현 방식, 시작 가능성의"
             " 창을 중심으로 풀되 '반드시 이어진다' 단정은 금지.",
    "fiance": "결혼을 앞둔 사이다 — 준비 과정의 마찰·가치관 조율·현실 문제(양가·재정)와"
              " 유리한 결혼 시기 창을 중심으로 풀 것.",
    "divorcing": "이혼을 고민·진행 중인 관계다 — 밝은 궁합 톤을 강요하지 말고, 정리와"
                 " 회복의 결을 분리해(신뢰·안전이 깨진 사유=회복 어려움 / 성격·상황"
                 " 사유=노력 여지) 큰 결정은 운 저점에서 서두르지 않게 안내할 것.",
    "affair": "혼외 관계다 — 도덕적 훈계도 관계 미화도 하지 말 것. 감정의 실체와 함께"
              " 신뢰·가정·현실에 미치는 리스크를 냉정하게 병기하고, 지속·정리 어느 쪽도"
              " 단정하지 말며 선택의 갈림과 그 대가를 균형 있게 짚을 것.",
    "parent_child": "부모·자녀 관계다 — 연애 궁합 프레임 금지. 보호와 독립, 기대 충돌,"
                    " 정서적 부담의 조율을 중심으로 풀 것.",
    "family": "가족·친척 관계다 — 연애 프레임 금지. 역할·거리 조절·도움과 부담의 균형"
              " 중심으로 풀 것.",
    "friend": "친구 관계다 — 연애 프레임을 끌어오지 말고 신뢰·거리 조절·오래 가는 관계"
              " 운영을 중심으로 풀 것.",
    "coworker": "직장 동료다 — 연애 궁합이 아니라 협업 방식·역할·소통의 합을 중심으로 풀 것.",
    "boss": "상대가 나의 상사다 — 위계를 전제로 인정받는 방식·보고와 소통의 결·갈등 완충을"
            " 중심으로 풀고, 대등한 관계처럼 서술하지 말 것.",
    "subordinate": "상대가 나의 부하 직원이다 — 위임과 신뢰, 지도 방식, 동기 부여를 중심으로"
                   " 풀고 연애 프레임을 쓰지 말 것.",
    "business_partner": "사업 파트너다 — 금전 흐름·책임 소재·의사결정 충돌의 조율을 중심으로"
                        " 풀고 연애 프레임을 쓰지 말 것.",
}


def relation_context_lines(relation_type: str | None) -> list[str]:
    """[상대와의 관계] 블록 — 사용자가 명시한 관계를 풀이 방향으로 번역한다(리포트 RP-* 공용).

    관계 미지정(None/unknown)은 빈 목록 — 기존 중립 궁합 톤 유지(하위호환).
    점수·간지·판정에는 개입하지 않는다(서술 방향 전용).
    """
    if not relation_type or relation_type == "unknown":
        return []
    ko = RELATION_KO.get(relation_type)
    framing = RELATION_FRAMING.get(relation_type)
    if ko is None or framing is None:
        return []
    hints = PERSPECTIVE_HINTS.get(relation_type, PERSPECTIVE_HINTS["unknown"])
    return [
        f"[상대와의 관계 — 사용자가 지정: {ko}]",
        f"풀이 방향: {framing}",
        f"주로 볼 영역: {' · '.join(hints)}",
        "관계 유형은 서술 관점일 뿐이다 — 궁합 점수·우열·결과를 단정하지 말 것.",
    ]

# 안전 가드 — competition/ranking 미구현이어도 미리 둔다(승부·우열 단정 금지, 절대원칙 8).
SAFETY_GUARDS: list[str] = [
    "관계를 점수나 우열·승패로 단정하지 말 것",
    "두 사람 명식 차이가 협력·충돌·보완으로 어떻게 나타나는지 조건·조율 포인트 중심으로 설명할 것",
    "경쟁·승패·당락을 묻더라도 확정 표현은 피하고 조건·강점·리스크·준비 포인트로 답할 것",
]

# 경쟁 비교(P3c-1) 전용 가드 — 승부·당락 확정 출력 금지(절대원칙 8). '우열' 대신 조건부 유리
# 요인·부담·보완 중심. '상대 우열'은 내부 표현일 뿐, 사용자 출력은 아래로 제한한다.
COMPETITION_SAFETY_GUARDS: list[str] = [
    "승패·우승·합격·당락을 확정하지 말 것.",
    "승률·확률·점수·순위를 만들지 말 것.",
    "'A가 반드시 이긴다', 'B는 떨어진다' 같은 표현을 금지한다.",
    "각 대상의 강점, 부담 요인, 리스크, 준비 포인트를 나누어 설명한다.",
    "비교가 필요하면 '이 조건에서는 A 쪽 신호가 강하고, B는 이런 보완이 필요하다'처럼 "
    "조건부로 말한다.",
    "최종 판단은 결과 보장이 아니라 준비 전략과 조율 포인트 중심으로 정리한다.",
]

# 경쟁/선발 키워드 — 2명 대상 + 이 신호면 competition으로 본다(승부 가드 적용).
_COMPETITION_RE = re.compile(
    r"누가\s*이[겨길]|누가\s*될까|누가\s*더\s*(?:잘|유리|나[아은])|누가\s*더\b|"
    r"승부|우승|합격|당선|선발|오디션|대회|붙(?:을까|어)|이길\s*(?:사람|확률|까)"
)


def is_competition(question: str) -> bool:
    """경쟁/선발/승부 비교 질문인가(승부 가드 적용 대상). 2명 대상 판정은 호출 측이 한다."""
    return bool(_COMPETITION_RE.search(question))


# 다자 비교(P3c-2, 3명 이상) 전용 가드 — '순위 산출'이 아니라 '항목별 조건부 상대 경향'.
RANKING_SAFETY_GUARDS: list[str] = [
    "절대 순위나 1등/2등/꼴찌를 단정하지 말 것.",
    "점수·확률·승률을 만들지 말 것.",
    "항목별 상대 경향만 설명할 것.",
    "추진력, 안정성, 관계 조율력, 재물 관리, 리스크 감수 성향처럼 영역별로 나누어 설명할 것.",
    "'누가 제일 낫다'가 아니라 '이 조건에서는 A의 신호가 강하고, B는 안정성, C는 조율력이 "
    "두드러진다'처럼 조건부로 설명할 것.",
]

# 다자 순위/비교 키워드(3명 이상 대상 + 이 신호면 ranking). '누가 제일/가장', 순위, 비교 등.
_RANKING_RE = re.compile(
    r"순위|랭킹|누가\s*(?:제일|가장|더)|제일\s*(?:잘|나은|유리)|가장\s*(?:잘|나은|유리)|"
    r"1등|비교(?:해|하)|중에?\s*누가"
)


def is_ranking_query(question: str) -> bool:
    """다자(순위/비교) 질문 신호인가. 3명 이상 대상 판정은 호출 측이 한다."""
    return bool(_RANKING_RE.search(question))


def infer_relation_type(
    question: str,
    companion_relation_to_user: str | None,
    domains: list[str] | None = None,
) -> tuple[str, str]:
    """관계유형과 근거(relation_basis)를 추론한다. 질문 키워드가 등록 관계보다 우선.

    Returns:
        (relation_type, relation_basis) — basis: explicit_keyword | relation_to_user |
        intent_domain | unknown.
    """
    for pat, rtype in _KEYWORD_RULES:
        if pat.search(question):
            return rtype, "explicit_keyword"
    if companion_relation_to_user:
        mapped = _RELATION_TO_USER.get(companion_relation_to_user)
        if mapped:
            return mapped, "relation_to_user"
    # ③ intent/domain — 보수적으로만(오분류 방지). 관계 도메인 단서가 있으면 romance로 약하게.
    for d in domains or []:
        if d == "relationship":
            return "romance", "intent_domain"
    return "unknown", "unknown"


def perspective_hints_for(relation_type: str) -> list[str]:
    """관계유형의 관점 힌트(미정의 시 unknown 힌트)."""
    return PERSPECTIVE_HINTS.get(relation_type, PERSPECTIVE_HINTS["unknown"])

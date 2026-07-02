"""관계유형 추론 + 관점 힌트 (동반자 공동 풀이 P3a — additive).

pairwise/companion_only에서 두 사람의 관계 유형을 추론해, LLM에 '어느 영역을 볼지' 관점
힌트만 제공한다. 점수화·궁합 점수·우열·승패는 만들지 않는다(관점 제어 전용). 추론 우선순위:
사용자 명시 키워드 > companion relation_to_user > intent/domain > unknown(질문이 등록관계보다 우선).
"""

from __future__ import annotations

import re

# 관계 유형(초기 enum). competition/ranking은 P3c 이후.
RELATION_TYPES: tuple[str, ...] = (
    "spouse", "romance", "parent_child", "family",
    "friend", "coworker", "business_partner", "unknown",
)

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
    "unknown": ["상호 성향", "소통 방식", "갈등 요인", "도움이 되는 지점", "조율 포인트"],
}

# 안전 가드 — competition/ranking 미구현이어도 미리 둔다(승부·우열 단정 금지, 절대원칙 8).
SAFETY_GUARDS: list[str] = [
    "관계를 점수나 우열·승패로 단정하지 말 것",
    "두 사람 명식 차이가 협력·충돌·보완으로 어떻게 나타나는지 조건·조율 포인트 중심으로 설명할 것",
    "경쟁·승패·당락을 묻더라도 확정 표현은 피하고 조건·강점·리스크·준비 포인트로 답할 것",
]


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

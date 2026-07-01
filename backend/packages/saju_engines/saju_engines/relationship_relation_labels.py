"""관계질 라벨 사전 — 합·충·형·파·해·원진·공망의 중립 해석 문구 (P4, 2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §2. **해석 문구 표준화 레이어**이며 점수 엔진이 아니다.
점수·confidence·후보 생성·favorability를 변경하지 않고(inert / explanation-only), 합충형파해원진
공망을 좋다/나쁘다로 단정하지 않으며 관계 맥락에 맞는 중립 표현만 제공한다. 궁합(compatibility)·
배우자궁(marriage_resource)·궁위 관계망(structural_context)이 공용한다.
"""

from __future__ import annotations

from typing import TypedDict


class RelationLabel(TypedDict):
    """관계질 라벨 1건 — 표시명·톤·중립 요약·주의·허용/금지 표현."""

    display: str
    tone: str
    summary: str
    caution: str
    safe_phrases: list[str]
    avoid_phrases: list[str]


# 합·충·형·파·해·원진·공망 관계질 라벨(중립·비단정). 직접 작문 금지 — 이 사전만 참조한다.
RELATIONSHIP_RELATION_LABELS: dict[str, RelationLabel] = {
    "hap": {
        "display": "합",
        "tone": "connection",
        "summary": "연결·협력·끌림이 생기기 쉬운 관계",
        "caution": "합거·합반이면 묶임, 지연, 선택 곤란으로 체감될 수 있음",
        "safe_phrases": ["연결감", "협력", "끌림", "관계가 묶임"],
        "avoid_phrases": ["무조건 좋음", "천생연분 확정"],
    },
    "chung": {
        "display": "충",
        "tone": "movement_conflict",
        "summary": "변동·충돌·분리·이동이 생기기 쉬운 관계",
        "caution": "갈등만이 아니라 독립·거리 조정·환경 변화로도 나타날 수 있음",
        "safe_phrases": ["변동", "거리 조정", "충돌", "독립"],
        "avoid_phrases": ["무조건 이별", "파국"],
    },
    "hyeong": {
        "display": "형",
        "tone": "pressure_adjustment",
        "summary": "조정·압박·교정·소모가 생기기 쉬운 관계",
        "caution": "관계를 다듬는 과정이지만 피로감이 커질 수 있음",
        "safe_phrases": ["조정", "압박", "교정", "소모"],
        "avoid_phrases": ["처벌", "저주"],
    },
    "pa": {
        "display": "파",
        "tone": "crack_instability",
        "summary": "균열·불안정·약속의 흔들림이 생기기 쉬운 관계",
        "caution": "작은 오해나 조건 변화가 관계 안정성을 흔들 수 있음",
        "safe_phrases": ["균열", "불안정", "흔들림"],
        "avoid_phrases": ["반드시 깨짐"],
    },
    "hae": {
        "display": "해",
        "tone": "subtle_friction",
        "summary": "은근한 방해·오해·서운함·누수가 생기기 쉬운 관계",
        "caution": "겉으로 큰 충돌이 없어도 속으로 쌓이는 불편함이 있을 수 있음",
        "safe_phrases": ["오해", "서운함", "은근한 마찰", "누수"],
        "avoid_phrases": ["배신 확정"],
    },
    "wonjin": {
        "display": "원진",
        "tone": "emotional_entanglement",
        "summary": "끌림과 불편함, 서운함과 감정 응어리가 함께 생기기 쉬운 감정 소모형 관계",
        "caution": "좋고 나쁨의 단순 판단보다 감정 관리가 중요한 관계로 해석",
        "safe_phrases": ["감정 응어리", "애증", "반복되는 서운함", "감정 소모"],
        "avoid_phrases": ["악연", "속궁합", "절대 못 헤어짐", "징글징글"],
    },
    "gongmang": {
        "display": "공망",
        "tone": "emptiness_distance",
        "summary": "실체감 부족·거리감·기대와 현실의 간극이 생기기 쉬운 관계",
        "caution": "관계가 없다는 뜻이 아니라 체감상 허전함이 남을 수 있음",
        "safe_phrases": ["거리감", "허전함", "실체감 부족", "기대와 현실의 간극"],
        "avoid_phrases": ["인연 없음", "무조건 공허함"],
    },
}

# 한글 관계명(엔진 산출) → 라벨 키. 육합=합, 귀문=원진으로 매핑한다.
_KO_TO_KEY: dict[str, str] = {
    "합": "hap", "육합": "hap", "충": "chung", "형": "hyeong", "파": "pa",
    "해": "hae", "원진": "wonjin", "귀문": "wonjin", "공망": "gongmang",
}


def get_relationship_relation_label(relation_type: str) -> RelationLabel | None:
    """라벨 키(hap/chung/…) 또는 한글명(충/원진/…)으로 관계질 라벨을 조회한다(없으면 None)."""
    key = relation_type if relation_type in RELATIONSHIP_RELATION_LABELS else _KO_TO_KEY.get(
        relation_type
    )
    return RELATIONSHIP_RELATION_LABELS.get(key) if key else None


def relation_summary_ko(relation_type: str) -> str:
    """관계질 중립 요약 문구(없으면 빈 문자열) — 라인 렌더링용 편의."""
    label = get_relationship_relation_label(relation_type)
    return label["summary"] if label else ""

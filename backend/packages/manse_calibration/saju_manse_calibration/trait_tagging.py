"""성향 반박 결(trait_denial_kind) 룰 기반 태깅 — CAL-P1 P1-a.

자유 진술(trait_statement)을 absolute / situational / temporal / mixed / unclear 로
분류한다(doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md §4). 초기엔 **룰 기반만** —
LLM·임베딩 분류 금지(과분류 위험, 실사용 진술 축적 후 보정).

불변식: 분류값은 채점 절대 비반영 — review_flags 축적과 LLM 표현 힌트 전용.
situational/temporal은 "성향이 틀렸다"가 아니라 **발현 조건 정보**다.
"""

from __future__ import annotations

# 상황 한정 표지 — 특정 장면·조건에서만 다르다는 결("글로는 괜찮은데 면접에서는…").
_SITUATIONAL_KEYS: tuple[str, ...] = (
    "면접", "회의", "사람 앞", "사람들 앞", "발표", "처음 보는", "낯선",
    "일할 때", "집에서", "에서는", "할 때만", "때만",
)
# 시기 변화 표지 — 시기에 따라 달라졌다는 결("예전에는 못했는데 요즘은…").
_TEMPORAL_KEYS: tuple[str, ...] = (
    "예전", "옛날", "요즘", "최근", "어릴 때", "어렸을 때", "지금은",
    "나이 들", "하고 나서부터", "그때는", "이제는",
)
# 강부정 표지 — 성향 자체 부정 후보("저는 외로움을 전혀 못 느껴요").
_ABSOLUTE_KEYS: tuple[str, ...] = (
    "전혀", "아예", "한 번도", "한번도", "항상 아니", "거의 못", "거의 안",
)


def classify_trait_denial_kind(statement: str | None) -> str | None:
    """자유 진술의 반박 결을 룰 기반으로 분류한다(순수 함수).

    우선순위(§4 확정): situational·temporal 표지가 **둘 다** 있으면 mixed →
    하나만 있으면 해당 결 → 둘 다 없고 강부정 표지가 있으면 absolute → 그 외 unclear.
    빈 진술은 None — 정보 없음(unclear=분류 실패와 구분).

    Args:
        statement: 사용자 자유 진술(없으면 None/공백).

    Returns:
        TRAIT_DENIAL_KINDS 중 하나 또는 None(진술 없음).
    """
    if statement is None or not statement.strip():
        return None
    situational = any(k in statement for k in _SITUATIONAL_KEYS)
    temporal = any(k in statement for k in _TEMPORAL_KEYS)
    if situational and temporal:
        return "mixed"
    if situational:
        return "situational"
    if temporal:
        return "temporal"
    if any(k in statement for k in _ABSOLUTE_KEYS):
        return "absolute"
    return "unclear"

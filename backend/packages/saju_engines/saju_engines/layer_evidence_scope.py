"""층위 근거 분류 — LLM grounding(D1-B)과 사건 범위 게이트(P2)의 단일 진실원천.

같은 판정을 두 곳에서 따로 계산하면 "LLM에는 상위 지지 있다고 알려주고 랭커는 없다고
보는" 어긋남이 생긴다. 그래서 이 순수 함수 하나만 쓴다.

**입력은 반드시 `candidate_source_layers`(후보별 기여 층위)다.** `stack_layers`(그 시점
평가 스택 구성)를 넣으면 안 된다 — `stack_for()`가 관할 상위 운을 항상 붙이므로 전 후보가
상위 지지를 가진 것처럼 보인다. 1980-11-22 차트 744후보 실측에서 stack 기준 판정은
`UPPER_SUPPORTED` 100% / `MINOR_ONLY` 0%였고, 이는 사실이 아니라 측정 대상 오류였다.

현재 엔진은 기여 시점에 층위를 기록하지 않아 `candidate_source_layers`가 항상 비어 있다.
따라서 이 함수는 지금 언제나 `UNKNOWN`을 반환한다 — 의도된 fail-safe다. 실제 기여
provenance 수집은 P2-PROV(점수 불변 shadow)에서 다룬다.
"""

from __future__ import annotations

from collections.abc import Iterable

from saju_shared_types.event_engine import (
    LUCK_LAYER_ORDER,
    MINOR_LUCK_LAYERS,
    UPPER_LUCK_LAYERS,
    LayerEvidenceScope,
)

_UPPER_VALUES = frozenset(x.value for x in UPPER_LUCK_LAYERS)
_MINOR_VALUES = frozenset(x.value for x in MINOR_LUCK_LAYERS)


def normalize_layers(layers: Iterable[object]) -> list[str]:
    """층위 입력(enum·str 혼재)을 중복 제거된 canonical 문자열 목록으로 고정한다.

    Args:
        layers: `LuckLayer` 또는 그 값 문자열의 반복자.

    Returns:
        `LUCK_LAYER_ORDER` 순으로 정렬된 문자열 목록(미지 층위는 뒤에 이름순).
    """
    values = {str(x) for x in layers}
    return sorted(values, key=lambda v: (LUCK_LAYER_ORDER.get(v, 99), v))


def classify_layer_evidence_scope(
    candidate_source_layers: Iterable[object],
) -> LayerEvidenceScope:
    """후보별 기여 층위 → 근거 범위 3분류.

    Args:
        candidate_source_layers: 이 후보에 **실제로 기여한** 층위. `stack_layers`를
            넘기면 판정이 무의미해진다(모듈 docstring 참조).

    Returns:
        비었으면 `UNKNOWN`(판정 불가 — 기존 동작 유지), 상위(대운·세운) 기여가 하나라도
        있으면 `UPPER_SUPPORTED`, 월·일운만이면 `MINOR_ONLY`, 그 외 미지 층위는 `UNKNOWN`.
    """
    values = {str(x) for x in candidate_source_layers}
    if not values:
        return LayerEvidenceScope.UNKNOWN
    if values & _UPPER_VALUES:
        return LayerEvidenceScope.UPPER_SUPPORTED
    if values <= _MINOR_VALUES:
        return LayerEvidenceScope.MINOR_ONLY
    return LayerEvidenceScope.UNKNOWN

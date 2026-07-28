"""relation_affinity 배수 shadow (**라이브 점수 불변**).

사전의 개별 `relation_affinity` 값을 덮어쓰지 않고 **contribution 계층에 전역 배수**를
건다. 그래야 "어느 사전 항목이 바뀌었나"가 아니라 "관계 기여가 커지면 무엇이
달라지나"만 분리해 볼 수 있다.

관계 기여는 세 곳에 흩어져 있다(`_group_signals` 실사):

    DAY_BRANCH_RELATION   _rel_aff(day_rel)          전량
    MONTH_CONTEXT         0.35 × _rel_aff(month_rel)
    YEAR_CONTEXT          0.30 × _rel_aff(year_rel)

바꾸지 않는 것: `ten_god_affinity` · 관계 신호 종류와 성립 판정 · 사전 부호 ·
probability clamp · headline slots · domain cap · narrative_mode · candidate-hash 계약.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saju_shared_types.constants import BRANCH_ELEMENT
from saju_shared_types.daily_fortune import DayGanjiContext
from saju_shared_types.enums import Branch, Stem

from .daily_ilju_fortune import (
    _GROUP_WEIGHTS,
    _INDEPENDENT_THRESHOLD,
    _LAMBDA,
    _OVERLAP_BONUS,
    _SIGNAL_GAIN,
    _STRONG_CONTRADICTION,
    _branch_relations,
    _clamp,
    _hidden_aff,
    _positive_soft_cap,
    _rel_aff,
    _ScoredEvent,
    _tg_aff,
)

#: 후보안 — R0가 현행이다.
RELATION_VARIANTS: dict[str, float] = {
    "R0": 1.00, "R1": 1.25, "R2": 1.50, "R3": 1.75,
}


@dataclass(frozen=True)
class ComponentTrace:
    """사건 1건의 기여 분해 — 배수 적용 전 기준선 기록용."""

    event_key: str
    ten_god_component: float
    relation_component: float
    other_components: float
    final_probability: int
    relation_affinity_all_zero: bool


def _signals(
    event: dict[str, Any], ilju_stem: Stem, ilju_branch: Branch,
    ctx: DayGanjiContext, *, relation_multiplier: float = 1.0,
    relation_only: bool = False, ten_god_only: bool = False,
) -> dict[str, float]:
    """그룹 신호 — 관계 기여에만 배수를 적용한다.

    `relation_only`·`ten_god_only`는 기여 분해용이며 배수와 함께 쓰지 않는다.
    """
    day_stem, day_branch = Stem(ctx.day_stem), Branch(ctx.day_branch)
    month_stem, month_branch = Stem(ctx.month_stem), Branch(ctx.month_branch)
    year_stem, year_branch = Stem(ctx.year_stem), Branch(ctx.year_branch)
    helpers = (month_branch, year_branch)

    day_rel = _branch_relations(day_branch, ilju_branch, helpers)
    month_rel = _branch_relations(month_branch, ilju_branch, (day_branch, year_branch))
    year_rel = _branch_relations(year_branch, ilju_branch, (day_branch, month_branch))

    def rel(hits) -> float:
        if ten_god_only:
            return 0.0
        # 배수 후 clamp — 기존 값 범위를 벗어난 값을 만들지 않는다.
        return _clamp(_rel_aff(event, hits) * relation_multiplier)

    def tg(target: Stem) -> float:
        return 0.0 if relation_only else _tg_aff(event, ilju_stem, target)

    def hidden(branch: Branch) -> float:
        return 0.0 if (relation_only or ten_god_only) else _hidden_aff(
            event, ilju_stem, branch
        )

    elem = 0.0 if (relation_only or ten_god_only) else event["element_affinity"].get(
        BRANCH_ELEMENT[year_branch].value, 0.0
    )
    return {
        "DAY_STEM": tg(day_stem),
        "DAY_BRANCH_RELATION": rel(day_rel),
        "DAY_HIDDEN_STEMS": hidden(day_branch),
        "MONTH_CONTEXT": _clamp(
            0.4 * tg(month_stem) + 0.35 * rel(month_rel) + 0.25 * hidden(month_branch)
        ),
        "YEAR_CONTEXT": _clamp(
            0.5 * tg(year_stem) + 0.3 * rel(year_rel) + 0.2 * elem
        ),
    }


def _finalize(event: dict[str, Any], signals: dict[str, float], key: str) -> _ScoredEvent:
    """`_score_event`와 동일한 산식 — clamp·게이트를 그대로 따른다."""
    evidence = float(event["base_weight"])
    contradiction = 0.0
    supporting = 0
    for group, s in signals.items():
        w = _GROUP_WEIGHTS[group] * _SIGNAL_GAIN
        if s > 0:
            evidence += w * s
            if s >= _INDEPENDENT_THRESHOLD:
                supporting += 1
        elif s < 0:
            contradiction += w * (-s)
    net = max(0.0, evidence - _LAMBDA * contradiction)
    if supporting >= 2:
        net += _OVERLAP_BONUS
    activation = float(event["expr_confidence"]) * _positive_soft_cap(net)
    p = max(5, min(95, round(5 + 90 * activation)))
    if p >= 85 and supporting < 2:
        p = 84
    if p <= 10 and contradiction < _STRONG_CONTRADICTION:
        p = 11
    return _ScoredEvent(
        event_key=key, domain=event["domain"], valence=event["valence"],
        slots=tuple(event["slots"]),
        headline_slots=tuple(event.get("headline_slots") or event["slots"]),
        synonym_group=event.get("synonym_group"), activation=activation,
        probability=p, supporting_groups=supporting, contradiction=contradiction,
    )


def score_event_with_relation(
    key: str, event: dict[str, Any], ilju_stem: Stem, ilju_branch: Branch,
    ctx: DayGanjiContext, *, multiplier: float = 1.0,
) -> _ScoredEvent:
    """관계 기여에 배수를 적용해 사건을 채점한다(shadow).

    Args:
        multiplier: 관계 기여 배수. 1.0이면 라이브와 동일해야 한다.

    Returns:
        채점 결과.
    """
    return _finalize(
        event, _signals(event, ilju_stem, ilju_branch, ctx,
                        relation_multiplier=multiplier), key
    )


def component_trace(
    key: str, event: dict[str, Any], ilju_stem: Stem, ilju_branch: Branch,
    ctx: DayGanjiContext,
) -> ComponentTrace:
    """R0 기준선 — 십성·관계·그 외 기여를 분리 기록한다.

    각 축만 남긴 신호로 재채점해 얻는 근사값이다(그룹 내 clamp가 걸리면 합이 전체와
    정확히 일치하지 않는다 — 크기 비교용이다).
    """
    full = _finalize(event, _signals(event, ilju_stem, ilju_branch, ctx), key)
    tg = _finalize(
        event, _signals(event, ilju_stem, ilju_branch, ctx, ten_god_only=True), key
    )
    rel = _finalize(
        event, _signals(event, ilju_stem, ilju_branch, ctx, relation_only=True), key
    )
    return ComponentTrace(
        event_key=key,
        ten_god_component=tg.probability - 5,
        relation_component=rel.probability - 5,
        other_components=max(0, full.probability - tg.probability - rel.probability + 5),
        final_probability=full.probability,
        relation_affinity_all_zero=not any(event.get("relation_affinity", {}).values()),
    )


__all__ = [
    "RELATION_VARIANTS",
    "ComponentTrace",
    "component_trace",
    "score_event_with_relation",
]

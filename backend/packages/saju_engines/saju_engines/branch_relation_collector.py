"""지지 파괴 관계 수집기 — 위치 기반 SSOT (P1-b0, 2026-08-01).

`ganji_calendar.relation_hits` 를 실현도 파이프라인이 직접 소비하지 않는다. 실측(0B 후속)
결과 그 함수는 **운↔원국 전용**이다.

    relation_hits(GanjiLevel.DAEWOON, "己", "酉", relations_to_chart=["충:酉-卯"], ...)
    → branch_clash  luck=daewoon:酉  natal=[(year, 卯)]

운 간지 문자열을 입력으로 받는 구조라 **원국 내부 충**(예: 일지↔시지)과 **운↔운 충**
(대운↔세운)을 낼 수 없다. 표시·캘린더 목적의 의미론이라 상태 전이 의미론과 다르고, 그쪽이
바뀌면 실현도가 암묵적으로 흔들린다.

그래서 위치 기반 수집기를 따로 둔다. `relation_hits` 는 겹치는 범위의 **parity 대조**로만
쓴다(둘의 차이는 자동으로 버그가 아니다 — 아래 판정 어휘 참조).

**탐지와 효과를 분리한다.** 충·형·파·해를 모두 수집하되, "형·파·해가 있으면 기존 합화가
풀린다" 는 일반화는 하지 않는다. 변환 해제 의미론은 우선 **충 중심**으로 제한하고, 나머지는
구조 정보만 남긴다(`breaks_transformation` 필드).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from saju_shared_types.constants import (
    BRANCH_BREAKS,
    BRANCH_CLASHES,
    BRANCH_HARMS,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
)
from saju_shared_types.enums import Branch

from .luck_relation_graph import RelationNode


class RelationScope(StrEnum):
    """관계가 어느 층 사이에서 성립했는가."""

    NATAL_INTERNAL = "natal_internal"
    TRANSIT_TO_NATAL = "transit_to_natal"
    TRANSIT_TO_TRANSIT = "transit_to_transit"
    WITHIN_TRANSIT_LAYER = "within_transit_layer"


class BranchRelationKind(StrEnum):
    """파괴 계열 관계 종류."""

    CLASH = "clash"
    PUNISHMENT = "punishment"
    BREAK = "break"
    HARM = "harm"


#: 현재 **변환 해제 후보**로 인정하는 종류. 형·파·해는 수집하되 해제 효과를 부여하지 않는다
#: — 영상 사례가 직접 확인하려는 것은 巳亥冲·卯酉冲 이고, 나머지는 근거가 없다.
TRANSFORMATION_BREAKING_KINDS = frozenset({BranchRelationKind.CLASH})


@dataclass(frozen=True)
class BranchRelationInstance:
    """파괴 관계 1건 — **자리**로 식별한다."""

    relation_id: str
    relation_family: str
    kind: BranchRelationKind
    scope: RelationScope
    member_node_ids: tuple[str, ...]
    characters: tuple[str, ...]
    #: 변환 해제 후보인가. 탐지 여부와 별개다 — 형·파·해는 True 가 아니다.
    breaks_transformation: bool


def _scope(a: RelationNode, b: RelationNode) -> RelationScope:
    natal_a, natal_b = a.layer == "natal", b.layer == "natal"
    if natal_a and natal_b:
        return RelationScope.NATAL_INTERNAL
    if natal_a != natal_b:
        return RelationScope.TRANSIT_TO_NATAL
    if a.layer == b.layer:
        return RelationScope.WITHIN_TRANSIT_LAYER
    return RelationScope.TRANSIT_TO_TRANSIT


def _pair_kind(a: str, b: str) -> BranchRelationKind | None:
    """두 지지의 파괴 관계 종류. 없으면 None."""
    try:
        pair = frozenset({Branch(a), Branch(b)})
    except ValueError:
        return None
    if pair in BRANCH_CLASHES:
        return BranchRelationKind.CLASH
    if pair in PUNISHMENT_MUTUAL:
        return BranchRelationKind.PUNISHMENT
    if pair in BRANCH_BREAKS:
        return BranchRelationKind.BREAK
    if pair in BRANCH_HARMS:
        return BranchRelationKind.HARM
    return None


def _self_punishment(ch: str) -> bool:
    try:
        return Branch(ch) in SELF_PUNISHMENT
    except ValueError:
        return False


def collect_branch_relation_instances(
    *,
    nodes: Sequence[RelationNode],
    scopes: frozenset[RelationScope] | None = None,
    relation_kinds: frozenset[BranchRelationKind] | None = None,
) -> tuple[BranchRelationInstance, ...]:
    """자리 기반으로 파괴 관계를 전수 수집한다. **결정적이며 입력 순서에 의존하지 않는다.**

    같은 글자가 여러 자리에 있으면 **자리마다 별개 인스턴스**가 된다. 원국에 戌 이 둘일 때
    글자만 보면 하나로 뭉개진다(P1-a 에서 실측으로 확인).

    Args:
        nodes: 지지 자리 전체(component == 'branch' 만 본다).
        scopes: 수집할 범위. None 이면 전체.
        relation_kinds: 수집할 종류. None 이면 전체.

    Returns:
        관계 인스턴스. 변환 해제 여부는 `breaks_transformation` 으로만 표시하고
        실제 해제 판정은 하지 않는다(P1-c).
    """
    want_scope = scopes if scopes is not None else frozenset(RelationScope)
    want_kind = relation_kinds if relation_kinds is not None else frozenset(
        BranchRelationKind
    )
    branches = sorted(
        (n for n in nodes if n.component == "branch"), key=lambda n: n.node_id
    )
    out: list[BranchRelationInstance] = []

    for a, b in itertools.combinations(branches, 2):
        kind = _pair_kind(a.character, b.character)
        if kind is None or kind not in want_kind:
            continue
        scope = _scope(a, b)
        if scope not in want_scope:
            continue
        members = tuple(sorted((a.node_id, b.node_id)))
        chars = tuple(sorted((a.character, b.character)))
        family = f"{kind.value}:{''.join(chars)}"
        out.append(BranchRelationInstance(
            relation_id=f"{family}@{'+'.join(members)}",
            relation_family=family, kind=kind, scope=scope,
            member_node_ids=members, characters=chars,
            breaks_transformation=kind in TRANSFORMATION_BREAKING_KINDS,
        ))

    # 자형 — 같은 글자가 두 자리에 있을 때. 쌍 순회로는 잡히지만 종류가 다르다.
    if BranchRelationKind.PUNISHMENT in want_kind:
        for a, b in itertools.combinations(branches, 2):
            if a.character != b.character or not _self_punishment(a.character):
                continue
            scope = _scope(a, b)
            if scope not in want_scope:
                continue
            members = tuple(sorted((a.node_id, b.node_id)))
            family = f"punishment_self:{a.character}"
            out.append(BranchRelationInstance(
                relation_id=f"{family}@{'+'.join(members)}",
                relation_family=family, kind=BranchRelationKind.PUNISHMENT,
                scope=scope, member_node_ids=members,
                characters=(a.character, b.character), breaks_transformation=False,
            ))

    # 삼형 — 세 글자가 모두 있을 때만. 부분(2글자)은 위 쌍 순회가 이미 잡는다.
    if BranchRelationKind.PUNISHMENT in want_kind:
        for triple in PUNISHMENT_TRIPLES:
            want = {b.value if hasattr(b, "value") else str(b) for b in triple}
            picks = [n for n in branches if n.character in want]
            if {n.character for n in picks} != want:
                continue
            for combo in itertools.combinations(picks, 3):
                if {n.character for n in combo} != want:
                    continue
                scope_set = {_scope(x, y) for x, y in itertools.combinations(combo, 2)}
                scope = (
                    RelationScope.NATAL_INTERNAL
                    if scope_set == {RelationScope.NATAL_INTERNAL}
                    else RelationScope.TRANSIT_TO_NATAL
                )
                if scope not in want_scope:
                    continue
                members = tuple(sorted(n.node_id for n in combo))
                family = f"punishment_triple:{''.join(sorted(want))}"
                out.append(BranchRelationInstance(
                    relation_id=f"{family}@{'+'.join(members)}",
                    relation_family=family, kind=BranchRelationKind.PUNISHMENT,
                    scope=scope, member_node_ids=members,
                    characters=tuple(sorted(n.character for n in combo)),
                    breaks_transformation=False,
                ))

    return tuple(sorted(out, key=lambda r: r.relation_id))

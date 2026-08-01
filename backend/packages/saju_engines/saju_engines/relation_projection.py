"""층별·범위별 resolver projection (P1-b2, 2026-08-01).

P1-b1.5 실측에서 나온 문제: `resolve_branch_hap` 은 대운·세운·월운을 모두 `'luck'` 한 자리로
표기한다. 대운 지지와 세운 지지가 같은 해(12년에 한 번)에는 어느 층의 글자가 관계에
참여했는지 결과만 봐서는 알 수 없다.

**그 기간을 제외하지 않는다.** 정상적인 시기를 shadow 단계에서 빼두면 나중에 production
의미론으로 승격할 때 데이터 공백이 그대로 남는다. 대신 호출을 층·범위별로 쪼갠다.

    natal.internal      원국 ↔ 원국          NATAL_INTERNAL
    daewoon.to_natal    대운 ↔ 원국          TRANSIT_TO_NATAL
    sewoon.to_natal     세운 ↔ 원국          TRANSIT_TO_NATAL
    sewoon.to_daewoon   세운 ↔ 대운          TRANSIT_TO_TRANSIT

resolver 가 층을 몰라도 **호출 범위 자체가 후보를 제한**하므로 어댑터가 모호하지 않게 이을 수
있다. `sewoon.to_natal` 에는 대운 노드가 아예 없어서 `('luck','未')` 가 세운 未 하나로
확정된다.

다만 쌍 단위 범위만으로는 층을 가로지르는 삼합을 놓친다(원국 申 + 대운 子 + 세운 辰). 그래서
**위치가 고정된 합 후보**를 관계표에서 먼저 열거한다 — 모든 글자를 한 배열에 다시 넣는 방식은
쓰지 않는다. 그러면 처음의 모호함이 되돌아온다.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from saju_shared_types.constants import (
    DIRECTIONAL_COMBINATIONS,
    SIX_COMBINATIONS,
    THREE_HARMONY,
)

from .branch_relation_collector import RelationScope
from .luck_relation_graph import RelationNode

#: 층 이름. `LuckLayer` 에는 원국이 없어 여기서도 문자열로 다룬다
#: (`relation_state_snapshot.LAYER_ORDER` 와 같은 어휘).
NATAL = "natal"

#: resolver 의 `positions` 어휘 — 원국은 궁위, 운은 전부 'luck' 한 가지다.
LUCK_POSITION = "luck"


@dataclass(frozen=True)
class ResolverProjection:
    """resolver 를 부를 범위 하나.

    `node_ids` 가 어댑터의 매핑 후보를 **가둔다.** 이 울타리가 없으면 글자만 같은 다른 층의
    노드가 후보로 들어온다.
    """

    projection_id: str
    current_layer: str            # natal | daewoon | sewoon | wolwoon | ilwoon
    scope: RelationScope
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class PositionBoundHarmonyCandidate:
    """자리가 고정된 합 후보.

    글자 조합이 아니라 **자리 조합**이다. 같은 글자 조합이 여러 자리 조합에 대응하면 각각을
    별개 후보로 남긴다 — 임의로 하나를 고르지 않는다.
    """

    relation_family: str
    relation_type: str            # six | three_harmony | directional
    member_node_ids: tuple[str, ...]
    target_element: str
    #: 참여한 층. 두 개 이상이면 층을 가로지르는 후보다.
    layers: tuple[str, ...]


class LuckNodeIndex:
    """노드 색인. **권위 있는 키는 층·자리를 끝까지 포함한다.**

        (layer, pillar_position, component, character)

    글자 하나나 `(자리, 글자)` 만으로 찾는 보조 색인도 두지만, 그건 **후보 검색용**이며 결과가
    하나라고 가정하지 않는다. 단일 확정은 projection 범위 안에서만 한다.
    """

    def __init__(self, nodes: Sequence[RelationNode]) -> None:
        self._by_key: dict[tuple[str, str, str, str], str] = {}
        self._candidates: dict[tuple[str, str], list[str]] = {}
        self._nodes: dict[str, RelationNode] = {}
        for node in sorted(nodes, key=lambda n: n.node_id):
            key = (node.layer, node.pillar_position, node.component, node.character)
            existing = self._by_key.get(key)
            if existing is not None and existing != node.node_id:
                raise ValueError(
                    f"권위 키가 겹친다: {key!r} → {existing!r} / {node.node_id!r}"
                )
            self._by_key[key] = node.node_id
            self._nodes[node.node_id] = node
            if node.component != "branch":
                continue
            pos = node.pillar_position if node.layer == NATAL else LUCK_POSITION
            self._candidates.setdefault((pos, node.character), []).append(node.node_id)

    def node(self, node_id: str) -> RelationNode:
        return self._nodes[node_id]

    def candidates(self, position: str, character: str) -> tuple[str, ...]:
        """(자리, 글자) 후보 전체. **하나라고 가정하지 않는다.**"""
        return tuple(self._candidates.get((position, character), ()))

    def candidates_in(
        self, projection: ResolverProjection, position: str, character: str
    ) -> tuple[str, ...]:
        """projection 울타리 안의 후보만."""
        allowed = set(projection.node_ids)
        return tuple(n for n in self.candidates(position, character) if n in allowed)


def _branch_nodes(nodes: Sequence[RelationNode]) -> list[RelationNode]:
    return sorted((n for n in nodes if n.component == "branch"), key=lambda n: n.node_id)


def build_layer_projections(
    *,
    natal_nodes: Sequence[RelationNode],
    daewoon_nodes: Sequence[RelationNode] = (),
    sewoon_nodes: Sequence[RelationNode] = (),
) -> tuple[ResolverProjection, ...]:
    """원국→대운→세운 조립에 필요한 projection 목록.

    운 노드가 없는 층의 projection 은 만들지 않는다 — 빈 범위로 resolver 를 부르면 원국
    내부 관계가 그 층 결과로 잘못 기록된다.

    Args:
        natal_nodes: 원국 자리.
        daewoon_nodes: 대운 자리(보통 1개).
        sewoon_nodes: 세운 자리(보통 1개).

    Returns:
        projection 목록. 순서는 층 순서를 따른다.
    """
    natal_ids = tuple(n.node_id for n in _branch_nodes(natal_nodes))
    dw_ids = tuple(n.node_id for n in _branch_nodes(daewoon_nodes))
    sw_ids = tuple(n.node_id for n in _branch_nodes(sewoon_nodes))

    out = [ResolverProjection(
        "natal.internal", NATAL, RelationScope.NATAL_INTERNAL, natal_ids,
    )]
    if dw_ids:
        out.append(ResolverProjection(
            "daewoon.to_natal", "daewoon", RelationScope.TRANSIT_TO_NATAL,
            tuple(sorted((*natal_ids, *dw_ids))),
        ))
    if sw_ids:
        out.append(ResolverProjection(
            "sewoon.to_natal", "sewoon", RelationScope.TRANSIT_TO_NATAL,
            tuple(sorted((*natal_ids, *sw_ids))),
        ))
        if dw_ids:
            out.append(ResolverProjection(
                "sewoon.to_daewoon", "sewoon", RelationScope.TRANSIT_TO_TRANSIT,
                tuple(sorted((*dw_ids, *sw_ids))),
            ))
    return tuple(out)


def _families() -> list[tuple[str, str, tuple[str, ...], str]]:
    """(가족키, 종류, 글자들, 합화 오행). 관계표 SSOT 를 그대로 읽는다."""
    out: list[tuple[str, str, tuple[str, ...], str]] = []
    for members, element in SIX_COMBINATIONS.items():
        chars = tuple(sorted(b.value for b in members))
        out.append((f"six:{''.join(chars)}", "six", chars, element.value))
    for members, element, _royal in THREE_HARMONY:
        chars = tuple(sorted(b.value for b in members))
        out.append((
            f"three_harmony:{''.join(chars)}", "three_harmony", chars, element.value,
        ))
    for members, element in DIRECTIONAL_COMBINATIONS:
        chars = tuple(sorted(b.value for b in members))
        out.append((f"directional:{''.join(chars)}", "directional", chars, element.value))
    return sorted(out)


def enumerate_cross_layer_harmony_candidates(
    nodes: Sequence[RelationNode],
) -> tuple[PositionBoundHarmonyCandidate, ...]:
    """층을 가로지르는 합 후보를 **자리 단위로** 전수 열거한다.

    쌍 단위 projection 만으로는 원국 申 + 대운 子 + 세운 辰 같은 삼합을 놓친다. 그렇다고 모든
    글자를 한 배열에 넣고 resolver 를 부르면 층 구분이 다시 사라진다. 그래서 관계표를 기준으로
    **자리 조합을 먼저 만든다.**

    같은 글자가 여러 자리에 있으면 자리 조합마다 별개 후보가 된다(일지 戌·시지 戌). 후보를
    임의로 하나로 줄이지 않는다.

    Args:
        nodes: 원국·대운·세운 자리 전체.

    Returns:
        층을 **둘 이상** 가로지르는 후보만. 한 층 안에서 닫히는 관계는 해당 층의 projection 이
        이미 다룬다.
    """
    by_char: dict[str, list[RelationNode]] = {}
    for node in _branch_nodes(nodes):
        by_char.setdefault(node.character, []).append(node)

    out: list[PositionBoundHarmonyCandidate] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for family, rel_type, chars, element in _families():
        if any(ch not in by_char for ch in chars):
            continue
        for combo in itertools.product(*(by_char[ch] for ch in chars)):
            member_ids = tuple(sorted(n.node_id for n in combo))
            if len(set(member_ids)) != len(chars):
                continue                       # 같은 자리를 두 번 쓰는 조합
            layers = tuple(sorted({n.layer for n in combo}))
            if len(layers) < 2:
                continue                       # 층 내부는 해당 projection 담당
            key = (family, member_ids)
            if key in seen:
                continue
            seen.add(key)
            out.append(PositionBoundHarmonyCandidate(
                relation_family=family, relation_type=rel_type,
                member_node_ids=member_ids, target_element=element, layers=layers,
            ))
    return tuple(sorted(out, key=lambda c: (c.relation_family, c.member_node_ids)))

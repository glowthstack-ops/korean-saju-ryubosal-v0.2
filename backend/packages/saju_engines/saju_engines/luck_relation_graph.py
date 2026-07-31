"""운 관계 의존성 그래프 — shadow 계산물 (P1-a, 2026-08-01).

기존 `resolve_stem_hap`·`resolve_branch_hap` 은 관계를 **각각 독립적으로** 돌려준다. 그런데
하나의 지지가 여러 관계에 동시에 참여한다. 기준선 측정(0B)에서 사례 A 는 이렇게 나왔다.

    six   卯戌  tier=conditional mode=bind     →火     (일지 戌)
    six   卯戌  tier=conditional mode=bind     →火     (시지 戌)
    half  卯未  tier=none        mode=partial  →木
    (卯酉冲은 목록에 없고, 卯未 와의 인과 연결도 없다)

같은 `卯` 가 木 방향과 火 방향에 동시에 얽혀 있고 `酉` 와 충하는데, 출력만 보면 서로 무관한
세 줄이다. 배열 순서대로 첫 관계만 적용하는 방식으로는 이 구조를 다룰 수 없다.

이 모듈은 **관계들 사이의 의존을 명시적 그래프로 드러내는 것까지만** 한다.

    한다        노드·엣지 정규화 · 공유 노드 · 경쟁 방향 · 잠재 차단/교란 링크
    하지 않는다  어느 합이 이겼는지 · 실제 차단 여부 확정 · 상태 전이 · 환원 ·
                점수 · tier/mode 의미 변경

그래서 링크 이름이 `BLOCKED_BY` 가 아니라 `POTENTIALLY_BLOCKED_BY` 다. 실제 차단 판정은
상태 전이 규칙(P1-b)이 들어온 뒤에야 확정할 수 있다.

**순수 함수다.** 요청 로컬·전역·take-and-reset 저장소를 두지 않는다. 이 그래프는 생성 시점과
소비 시점이 붙어 있는 중간 계산물이라(대운 배경 맵과 다르다) 숨은 저장소를 만들면 호출 순서
의존·reset 누락·병렬 평가 혼선만 남는다. 소비자는 반환값을 명시적으로 받는다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

# ── 링크 종류 ────────────────────────────────────────────────────────────
#
# 전부 **관찰**이지 판정이 아니다. P1-b 가 이 위에서 전이를 결정한다.
LINK_SHARES_NODE = "SHARES_NODE"
LINK_COMPETES_FOR_DIRECTION = "COMPETES_FOR_DIRECTION"
LINK_POTENTIALLY_BLOCKED_BY = "POTENTIALLY_BLOCKED_BY"
LINK_POTENTIALLY_DISRUPTED_BY = "POTENTIALLY_DISRUPTED_BY"
#: 같은 관계 가족이지만 자리가 다른 별개 인스턴스(예: 卯↔일지戌, 卯↔시지戌).
#: `DUPLICATE_*` 로 부르지 않는다 — 중복 제거 대상으로 오해된다.
LINK_SAME_FAMILY_DISTINCT_PLACEMENT = "SAME_FAMILY_DISTINCT_PLACEMENT"

#: 기존 결합을 깨뜨릴 수 있는 관계 종류. 여기 속하면 차단/교란 링크의 **원인 쪽**이 된다.
DISRUPTIVE_TYPES = frozenset({"clash", "punishment", "break", "harm"})


@dataclass(frozen=True)
class RelationNode:
    """관계에 참여하는 글자 한 자리.

    `node_id` 는 글자가 아니라 **자리**로 만든다. 원국에 戌 이 둘일 때 글자를 키로 쓰면
    일지와 시지를 구별할 수 없다.
    """

    node_id: str          # 예: 'natal.day.branch:戌'
    layer: str            # natal | daewoon | sewoon | wolwoon | ilwoon
    pillar_position: str  # year | month | day | hour | (운은 '')
    component: str        # stem | branch
    character: str
    original_element: str


@dataclass(frozen=True)
class RelationEdge:
    """관계 1건. 기존 resolver 결과를 **그대로** 옮긴다(해석하지 않는다)."""

    relation_id: str
    relation_family: str          # 예: 'six:卯戌' — 자리를 뺀 가족 키
    relation_type: str            # six | half | three_harmony | directional | clash …
    member_node_ids: tuple[str, ...]
    existing_tier: str | None
    existing_mode: str | None
    target_element: str | None
    source_resolver: str
    #: tier/mode 가 서로 다른 방향을 가리키는 경우를 **기존 필드를 고치지 않고** 병기한다
    #: (0B: 卯未亥 가 tier=none·mode=transform). 의미 변경은 별도 조사 후에 한다.
    normalized_observation: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationDependency:
    """관계 사이의 의존 1건."""

    dependency_id: str
    relation_ids: tuple[str, ...]
    link_type: str
    shared_node_ids: tuple[str, ...]
    target_elements: tuple[str, ...]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationDependencyGraph:
    """shadow 산출물. 생산 응답 DTO 에 붙이지 않는다 — 아직 소비자가 없다."""

    nodes: tuple[RelationNode, ...]
    edges: tuple[RelationEdge, ...]
    relation_dependencies: tuple[RelationDependency, ...]

    def metrics(self) -> dict[str, int]:
        """비용·구조 관측치. 간지 원문을 운영 로그에 남기지 않기 위한 요약이다."""
        by_link: dict[str, int] = {}
        for dep in self.relation_dependencies:
            by_link[dep.link_type] = by_link.get(dep.link_type, 0) + 1
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "dependency_count": len(self.relation_dependencies),
            "shared_node_group_count": by_link.get(LINK_SHARES_NODE, 0),
            "competing_direction_count": by_link.get(LINK_COMPETES_FOR_DIRECTION, 0),
            "potential_block_count": by_link.get(LINK_POTENTIALLY_BLOCKED_BY, 0),
            "potential_disrupt_count": by_link.get(LINK_POTENTIALLY_DISRUPTED_BY, 0),
            "distinct_placement_family_count": by_link.get(
                LINK_SAME_FAMILY_DISTINCT_PLACEMENT, 0
            ),
        }


def _dep_id(link_type: str, relation_ids: Sequence[str]) -> str:
    """의존 식별자 — 관계 ID 를 정렬해 만든다.

    대칭 관계(경쟁)에서 두 방향으로 두 번 만들지 않기 위해 정규 정렬한다. 비대칭 관계
    (차단)는 호출부가 순서를 고정해 넘긴다.
    """
    return f"{link_type}|" + "|".join(relation_ids)


def _normalized_observation(tier: str | None, mode: str | None) -> dict[str, object]:
    """tier/mode 의 의미 충돌을 관찰값으로만 병기한다(기존 필드 불변)."""
    intent = mode in ("transform", "partial")
    completed = tier == "confirmed"
    return {
        "transformation_intent": "present" if intent else "absent",
        "transformation_completion": "confirmed" if completed else "unconfirmed",
        # tier 는 '완성 아님' 인데 mode 는 '변환' 인 상태.
        "semantic_conflict": bool(mode == "transform" and tier != "confirmed"),
    }


def edge_from_resolution(
    *, relation_id: str, relation_family: str, relation_type: str,
    member_node_ids: Sequence[str], tier: str | None, mode: str | None,
    target_element: str | None, source_resolver: str,
) -> RelationEdge:
    """기존 resolver 결과 1건 → 엣지. `normalized_observation` 을 여기서 채운다.

    호출부가 매번 관찰값을 손으로 만들면 표기가 갈린다 — 한 곳에서만 만든다.
    """
    return RelationEdge(
        relation_id=relation_id, relation_family=relation_family,
        relation_type=relation_type, member_node_ids=tuple(member_node_ids),
        existing_tier=tier, existing_mode=mode, target_element=target_element,
        source_resolver=source_resolver,
        normalized_observation=_normalized_observation(tier, mode),
    )


def build_relation_dependency_graph(
    *,
    nodes: Sequence[RelationNode],
    resolved_relations: Sequence[RelationEdge],
    disruptive_relations: Sequence[RelationEdge] = (),
) -> RelationDependencyGraph:
    """관계 목록 → 의존 그래프. **결정적이며 입력 순서에 의존하지 않는다.**

    Args:
        nodes: 참여 가능한 자리 전체.
        resolved_relations: 합 계열 관계(기존 resolver 결과를 옮긴 것).
        disruptive_relations: 충·형·파·해 등 기존 결합을 깨뜨릴 수 있는 관계.

    Returns:
        노드·엣지·의존 링크. 승자·차단 여부는 판정하지 않는다.
    """
    edges = tuple(sorted(
        (*resolved_relations, *disruptive_relations), key=lambda e: e.relation_id
    ))
    deps: list[RelationDependency] = []
    seen: set[str] = set()

    def add(link_type: str, rel_ids: Sequence[str], shared: Collection[str],
            targets: Sequence[str], evidence: Sequence[str] = ()) -> None:
        dep_id = _dep_id(link_type, rel_ids)
        if dep_id in seen:
            return
        seen.add(dep_id)
        deps.append(RelationDependency(
            dependency_id=dep_id, relation_ids=tuple(rel_ids), link_type=link_type,
            shared_node_ids=tuple(sorted(shared)),
            target_elements=tuple(targets), evidence=tuple(evidence),
        ))

    resolved = sorted(resolved_relations, key=lambda e: e.relation_id)
    disruptive = sorted(disruptive_relations, key=lambda e: e.relation_id)

    for i, a in enumerate(resolved):
        for b in resolved[i + 1:]:
            shared = set(a.member_node_ids) & set(b.member_node_ids)
            if not shared:
                continue
            pair = tuple(sorted((a.relation_id, b.relation_id)))
            if a.relation_family == b.relation_family:
                # 같은 가족·다른 자리 — 보존 대상이지 중복이 아니다.
                add(LINK_SAME_FAMILY_DISTINCT_PLACEMENT, pair, shared,
                    tuple(sorted({t for t in (a.target_element, b.target_element) if t})))
                continue
            targets = {t for t in (a.target_element, b.target_element) if t}
            if len(targets) > 1:
                # 같은 글자를 두고 서로 다른 오행 방향으로 끌어간다.
                add(LINK_COMPETES_FOR_DIRECTION, pair, shared, tuple(sorted(targets)))
            else:
                add(LINK_SHARES_NODE, pair, shared, tuple(sorted(targets)))

    # 결합 ← 파괴 관계. 방향을 고정한다: source 가 방해받는 쪽이다.
    for res in resolved:
        for dis in disruptive:
            shared = set(res.member_node_ids) & set(dis.member_node_ids)
            if not shared:
                continue
            link = (
                LINK_POTENTIALLY_BLOCKED_BY
                if res.existing_tier != "confirmed"
                else LINK_POTENTIALLY_DISRUPTED_BY
            )
            add(link, (res.relation_id, dis.relation_id), shared,
                tuple(t for t in (res.target_element,) if t),
                evidence=(f"shared:{','.join(sorted(shared))}",))

    return RelationDependencyGraph(
        nodes=tuple(sorted(nodes, key=lambda n: n.node_id)),
        edges=edges,
        relation_dependencies=tuple(sorted(deps, key=lambda d: d.dependency_id)),
    )

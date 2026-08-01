"""원국→대운→세운 상태 체인 조립 (P1-b2, 2026-08-01).

P1-b1.5 결론 두 가지를 여기서 계약으로 굳힌다.

    parent_snapshot_id 만으로는 부모 내용을 찾을 수 없다(내부 저장소가 없다).
    → 최종 snapshot 하나가 아니라 frame(graph+snapshot) 체인을 반환한다.

    P1-c 는 dependency 만 믿으면 안 된다.
    → 우선 경로(governing_relation_id ↔ POTENTIALLY_DISRUPTED_BY)와
      백업 경로(node_id ∩ clash.member_node_ids)에 필요한 자료를 **모두** 남긴다.

resolver 호출은 층·범위별로 쪼갠다(`relation_projection`). 대운 지지와 세운 지지가 같은
해에도 기간을 제외하지 않는다 — 조립은 성공해야 하고 두 未 는 별개 노드로 남아야 한다.

**판정하지 않는 것**: 어느 합이 이겼는지, 충이 실제로 합화를 풀었는지, 환원 성립 여부.
그건 P1-c 다. 이 모듈은 재료를 자리 정보와 함께 모아 넘기는 데서 멈춘다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from saju_shared_types.constants import BRANCH_ELEMENT
from saju_shared_types.enums import Branch

from .branch_relation_collector import RelationScope, collect_branch_relation_instances
from .luck_relation_graph import (
    BranchHapLike,
    RelationDependencyGraph,
    RelationEdge,
    RelationNode,
    build_relation_dependency_graph,
    edge_from_resolution,
    edges_from_branch_relations,
)
from .relation_projection import (
    LUCK_POSITION,
    NATAL,
    LuckNodeIndex,
    PositionBoundHarmonyCandidate,
    ResolverProjection,
    build_layer_projections,
    enumerate_cross_layer_harmony_candidates,
)
from .relation_shadow_config import should_build_relation_state_chain
from .relation_state_snapshot import (
    RelationStateSnapshot,
    build_relation_state_snapshot,
)

_logger = logging.getLogger(__name__)


class ShadowFailureKind(StrEnum):
    """shadow 실패 분류. 운영 로그에는 이 코드와 수량만 남긴다(간지·생년월일 금지)."""

    NODE_INDEX_COLLISION = "node_index_collision"
    AMBIGUOUS_POSITION_BINDING = "ambiguous_position_binding"
    UNSUPPORTED_CROSS_LAYER_RELATION = "unsupported_cross_layer_relation"
    SNAPSHOT_BUILD_FAILURE = "snapshot_build_failure"
    FINGERPRINT_FAILURE = "fingerprint_failure"
    UNEXPECTED_ERROR = "unexpected_error"


class RelationStateAssemblyError(Exception):
    """조립 실패. 호출부는 이걸 잡아 기록하고 요청은 정상 완료시킨다."""

    def __init__(self, kind: ShadowFailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class RelationFrameBuildMetrics:
    """frame 하나의 비용·구조 관측치. **간지 원문을 담지 않는다.**"""

    layer: str
    projection_count: int = 0
    resolver_call_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    dependency_count: int = 0
    ambiguous_position_binding_count: int = 0
    cross_layer_harmony_candidate_count: int = 0
    duplicate_edge_merge_count: int = 0


@dataclass(frozen=True)
class RelationStateFrame:
    """한 층의 그래프와 상태를 함께 보존한다.

    P1-c 는 이전 snapshot 과 현재 graph 를 **둘 다** 필요로 한다. snapshot 배열만 넘기면
    현재 층의 충 엣지를 볼 수 없다.
    """

    layer: str
    period_key: str
    graph: RelationDependencyGraph
    snapshot: RelationStateSnapshot
    metrics: RelationFrameBuildMetrics
    #: (relation_id, projection_id 들) — 같은 관계가 여러 범위에서 발견된 내력.
    #: 기존 `RelationEdge` DTO 를 건드리지 않으려고 정규화 단계에만 둔다.
    edge_provenance: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class RelationStateChain:
    """원국→대운→세운 frame 체인."""

    frames: tuple[RelationStateFrame, ...]
    build_duration_ms: float = 0.0
    failure_kind: ShadowFailureKind | None = None

    @property
    def terminal_frame(self) -> RelationStateFrame:
        return self.frames[-1]

    def aggregate_metrics(self) -> dict[str, int]:
        """저카디널리티 집계. 층 라벨은 frame 쪽 metrics 에 있다."""
        keys = (
            "projection_count", "resolver_call_count", "node_count", "edge_count",
            "dependency_count", "ambiguous_position_binding_count",
            "cross_layer_harmony_candidate_count", "duplicate_edge_merge_count",
        )
        out = {k: 0 for k in keys}
        for frame in self.frames:
            for k in keys:
                out[k] += int(getattr(frame.metrics, k))
        out["snapshot_count"] = len(self.frames)
        return out


class BranchHapResolver(Protocol):
    """resolver 호출 어댑터의 최소 계약.

    `resolve_branch_hap` 을 직접 import 하면 saju_engines → manse_analysis 방향 의존이
    생긴다. 호출부가 주입한다.
    """

    def __call__(
        self, luck_branches: Sequence[str] | None = ...
    ) -> Sequence[BranchHapLike]: ...


def _positions_in_scope(scope: RelationScope, positions: Sequence[str]) -> bool:
    """이 projection 이 받아야 할 결과인가 — 범위 밖 결과를 조용히 흡수하지 않는다."""
    has_luck = LUCK_POSITION in positions
    if scope is RelationScope.NATAL_INTERNAL:
        return not has_luck
    if scope is RelationScope.TRANSIT_TO_TRANSIT:
        return all(p == LUCK_POSITION for p in positions)
    return has_luck and not all(p == LUCK_POSITION for p in positions)


@dataclass
class _AdaptResult:
    edges: list[RelationEdge] = field(default_factory=list)
    ambiguous: int = 0


def adapt_resolver_results_to_relation_edges(
    *,
    projection: ResolverProjection,
    resolver_results: Sequence[BranchHapLike],
    node_index: LuckNodeIndex,
) -> tuple[tuple[RelationEdge, ...], int]:
    """projection 범위 안에서만 resolver 결과를 엣지로 옮긴다.

    어댑터가 글자만 보고 노드를 찾게 두지 않는다. 후보는 `projection.node_ids` 안으로
    제한되며, 그 울타리가 층 구분 없는 `'luck'` 어휘를 대신 가른다.

    Args:
        projection: 호출 범위.
        resolver_results: 해당 범위로 부른 `resolve_branch_hap` 결과.
        node_index: 권위 색인.

    Returns:
        (엣지, 모호 바인딩 건수). 모호한 건은 버리지 않고 `position_binding=unconfirmed`
        로 표시해 남긴다 — 확정 변환에는 반영되지 않는다.
    """
    out = _AdaptResult()
    for res in resolver_results:
        positions = tuple(res.positions)
        members = tuple(res.members)
        if not positions or not _positions_in_scope(projection.scope, positions):
            continue
        member_ids: set[str] = set()
        ambiguous = False
        for pos in positions:
            for ch in members:
                hits = node_index.candidates_in(projection, pos, ch)
                if len(hits) > 1:
                    ambiguous = True
                member_ids.update(hits)
        if not member_ids:
            continue
        if ambiguous:
            out.ambiguous += 1
        family = f"{res.kind}:{''.join(members)}"
        edge = edge_from_resolution(
            relation_id=f"{family}@{'+'.join(sorted(member_ids))}",
            relation_family=family,
            relation_type=str(res.kind),
            member_node_ids=tuple(sorted(member_ids)),
            tier=res.transform_tier,
            mode=res.hap_mode,
            target_element=res.transform_element,
            source_resolver="branch_hap",
        )
        if ambiguous:
            edge.normalized_observation["position_binding"] = "unconfirmed"
        out.edges.append(edge)
    return tuple(out.edges), out.ambiguous


def edges_from_harmony_candidates(
    candidates: Sequence[PositionBoundHarmonyCandidate],
    tier_by_family: dict[str, tuple[str | None, str | None]],
) -> tuple[RelationEdge, ...]:
    """자리 고정 합 후보 → 엣지. tier/mode 는 resolver 판정을 그대로 빌려온다.

    후보가 자리를 정하고 resolver 가 성립 여부를 정한다. 어느 쪽도 상대의 판단을 대신하지
    않는다. resolver 가 그 가족을 보고하지 않았으면 tier/mode 는 None 이며, 확정 변환으로
    올라가지 않는다.
    """
    out: list[RelationEdge] = []
    for cand in candidates:
        # 후보의 가족키는 관계표 정렬 순이라 resolver 순서와 다를 수 있다.
        key = normalized_family_key(
            cand.relation_type, cand.relation_family.split(":", 1)[1]
        )
        tier, mode = tier_by_family.get(key, (None, None))
        out.append(edge_from_resolution(
            relation_id=(
                f"{cand.relation_family}@{'+'.join(cand.member_node_ids)}"
            ),
            relation_family=cand.relation_family,
            relation_type=cand.relation_type,
            member_node_ids=cand.member_node_ids,
            tier=tier, mode=mode,
            target_element=cand.target_element if tier == "confirmed" else None,
            source_resolver="cross_layer_harmony",
        ))
    return tuple(sorted(out, key=lambda e: e.relation_id))


def merge_edges(
    labelled: Sequence[tuple[str, RelationEdge]],
) -> tuple[tuple[RelationEdge, ...], tuple[tuple[str, tuple[str, ...]], ...], int]:
    """자리별 relation_id 기준 병합.

    문자 관계로 합치지 않는다 — 卯↔일지戌 과 卯↔시지戌 은 서로 다른 인스턴스이고, 합치면
    궁위 근거가 사라진다. 같은 relation_id 가 여러 범위에서 나오면 하나로 묶고 출처만
    누적한다.

    Returns:
        (엣지, (relation_id, projection_id 들), 병합 횟수).
    """
    first: dict[str, RelationEdge] = {}
    sources: dict[str, list[str]] = {}
    merged = 0
    for projection_id, edge in labelled:
        if edge.relation_id in first:
            merged += 1
        else:
            first[edge.relation_id] = edge
        srcs = sources.setdefault(edge.relation_id, [])
        if projection_id not in srcs:
            srcs.append(projection_id)
    edges = tuple(sorted(first.values(), key=lambda e: e.relation_id))
    provenance = tuple(
        (rid, tuple(sorted(srcs))) for rid, srcs in sorted(sources.items())
    )
    return edges, provenance, merged


def normalized_family_key(relation_type: str, characters: Sequence[str]) -> str:
    """글자 순서에 의존하지 않는 가족키.

    자리 열거기는 관계표(정렬된 frozenset)에서, resolver 는 자기 순서로 글자를 낸다.
    `申子辰` 과 `子申辰` 은 같은 삼합인데 문자열로는 다르다 — 실측에서 이 불일치로 tier 가
    유실돼 확정 삼합이 UNCONFIRMED 로 떨어졌다. 대조는 정렬된 키로만 한다.
    """
    return f"{relation_type}:{''.join(sorted(characters))}"


def _tier_by_family(results: Sequence[BranchHapLike]) -> dict[str, tuple[str | None, str | None]]:
    """정규 가족키 → (tier, mode). 자리는 여기서 정하지 않는다."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for res in results:
        members = tuple(res.members)
        if not members:
            continue
        key = normalized_family_key(str(res.kind), members)
        out[key] = (
            res.transform_tier,
            res.hap_mode,
        )
    return out


def assemble_relation_state_chain(
    *,
    natal_nodes: Sequence[RelationNode],
    daewoon_nodes: Sequence[RelationNode] = (),
    sewoon_nodes: Sequence[RelationNode] = (),
    resolve_branch_hap: BranchHapResolver,
    period_keys: dict[str, str],
) -> RelationStateChain:
    """원국→대운→세운 체인 조립. **판정하지 않는다.**

    Args:
        natal_nodes: 원국 자리.
        daewoon_nodes: 대운 자리.
        sewoon_nodes: 세운 자리.
        resolve_branch_hap: `luck_branches` 만 받아 결과를 돌려주는 호출자 주입 함수.
        period_keys: 층 → 기간키(예: {'natal': 'natal', 'daewoon': '2003', ...}).

    Returns:
        frame 체인. 각 frame 이 graph 와 snapshot 을 함께 들고 있다.

    Raises:
        RelationStateAssemblyError: 조립 실패. 호출부가 잡아 기록하고 요청은 계속한다.
    """
    started = time.perf_counter()
    try:
        all_nodes = [*natal_nodes, *daewoon_nodes, *sewoon_nodes]
        try:
            index = LuckNodeIndex(all_nodes)
        except ValueError as exc:
            raise RelationStateAssemblyError(
                ShadowFailureKind.NODE_INDEX_COLLISION, str(exc)
            ) from exc

        projections = build_layer_projections(
            natal_nodes=natal_nodes, daewoon_nodes=daewoon_nodes,
            sewoon_nodes=sewoon_nodes,
        )
        by_layer: dict[str, list[ResolverProjection]] = {}
        for proj in projections:
            by_layer.setdefault(proj.current_layer, []).append(proj)
        seen_layers: list[str] = []

        luck_by_layer = {
            "daewoon": [n.character for n in daewoon_nodes if n.component == "branch"],
            "sewoon": [n.character for n in sewoon_nodes if n.component == "branch"],
        }
        cross = enumerate_cross_layer_harmony_candidates(all_nodes)

        frames: list[RelationStateFrame] = []
        parent: RelationStateSnapshot | None = None
        visible: list[RelationNode] = []
        for layer in (NATAL, "daewoon", "sewoon"):
            layer_nodes = {
                NATAL: list(natal_nodes), "daewoon": list(daewoon_nodes),
                "sewoon": list(sewoon_nodes),
            }[layer]
            if layer != NATAL and not layer_nodes:
                continue
            visible = [*visible, *layer_nodes]
            seen_layers.append(layer)
            # 그 층까지 **보이는 모든 범위**를 돌린다. 자기 층 범위만 돌리면 세운 frame 이
            # 대운↔원국 관계를 통째로 잃는다(실측: 확정 삼합이 사라져 P1-c 우선 경로가
            # 끊겼다). 대운에서 성립한 합은 세운에서도 여전히 작동 중이다.
            projs = [p for lyr in seen_layers for p in by_layer.get(lyr, [])]
            labelled: list[tuple[str, RelationEdge]] = []
            ambiguous = calls = 0

            for proj in projs:
                luck = [
                    ch for lyr, chars in luck_by_layer.items()
                    for ch in chars
                    if any(n.startswith(f"{lyr}.") for n in proj.node_ids)
                ]
                results = resolve_branch_hap(luck_branches=luck or None)
                calls += 1
                edges, amb = adapt_resolver_results_to_relation_edges(
                    projection=proj, resolver_results=results, node_index=index,
                )
                ambiguous += amb
                labelled.extend((proj.projection_id, e) for e in edges)

            # 층을 가로지르는 합 — 자리는 열거기가, 성립은 resolver 가 정한다.
            layer_cross = [
                c for c in cross
                if set(c.layers) <= {n.layer for n in visible} and layer in c.layers
            ]
            if layer_cross:
                cumulative = resolve_branch_hap(luck_branches=[
                    ch for chars in luck_by_layer.values() for ch in chars
                ] or None)
                calls += 1
                labelled.extend(
                    (f"{layer}.cumulative_audit", e)
                    for e in edges_from_harmony_candidates(
                        layer_cross, _tier_by_family(cumulative)
                    )
                )

            merged_edges, provenance, merged_count = merge_edges(labelled)
            disruptive = edges_from_branch_relations(
                collect_branch_relation_instances(nodes=visible)
            )
            resolved_ids = {e.relation_id for e in merged_edges}
            graph = build_relation_dependency_graph(
                nodes=visible, resolved_relations=merged_edges,
                disruptive_relations=tuple(
                    e for e in disruptive if e.relation_id not in resolved_ids
                ),
            )
            try:
                snapshot = build_relation_state_snapshot(
                    graph=graph, layer=layer,
                    period_key=period_keys.get(layer, layer),
                    previous_snapshot=parent,
                )
            except ValueError as exc:
                raise RelationStateAssemblyError(
                    ShadowFailureKind.SNAPSHOT_BUILD_FAILURE, str(exc)
                ) from exc
            parent = snapshot
            frames.append(RelationStateFrame(
                layer=layer, period_key=snapshot.period_key, graph=graph,
                snapshot=snapshot, edge_provenance=provenance,
                metrics=RelationFrameBuildMetrics(
                    layer=layer, projection_count=len(projs),
                    resolver_call_count=calls, node_count=len(graph.nodes),
                    edge_count=len(graph.edges),
                    dependency_count=len(graph.relation_dependencies),
                    ambiguous_position_binding_count=ambiguous,
                    cross_layer_harmony_candidate_count=len(layer_cross),
                    duplicate_edge_merge_count=merged_count,
                ),
            ))
        return RelationStateChain(
            frames=tuple(frames),
            build_duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    except RelationStateAssemblyError:
        raise
    except Exception as exc:  # noqa: BLE001 - shadow 는 요청을 실패시키지 않는다
        raise RelationStateAssemblyError(
            ShadowFailureKind.UNEXPECTED_ERROR, repr(exc)
        ) from exc


def relation_nodes_from_branches(
    *, layer: str, branches: Sequence[tuple[str, str]]
) -> tuple[RelationNode, ...]:
    """(궁위, 지지) → 노드. 운 층은 궁위를 빈 문자열로 둔다.

    Args:
        layer: natal | daewoon | sewoon | wolwoon | ilwoon.
        branches: (궁위, 지지 한자). 운은 궁위를 `''` 로 넘긴다.

    Returns:
        노드. 알 수 없는 지지는 조용히 버리지 않고 예외로 알린다.
    """
    out: list[RelationNode] = []
    for position, character in branches:
        try:
            element = BRANCH_ELEMENT[Branch(character)].value
        except (ValueError, KeyError) as exc:
            raise RelationStateAssemblyError(
                ShadowFailureKind.UNEXPECTED_ERROR, f"알 수 없는 지지: {character!r}"
            ) from exc
        node_id = (
            f"{layer}.{position}.branch:{character}" if position
            else f"{layer}.branch:{character}"
        )
        out.append(RelationNode(
            node_id=node_id, layer=layer, pillar_position=position,
            component="branch", character=character, original_element=element,
        ))
    return tuple(out)


def relation_state_chain_shadow(
    *,
    natal_branches: Sequence[tuple[str, str]],
    daewoon_branch: str | None,
    sewoon_branch: str | None,
    resolve_branch_hap: BranchHapResolver,
    period_keys: dict[str, str],
) -> RelationStateChain | None:
    """마스터 게이트 wrapper — 상태 플래그가 꺼져 있으면 **아무것도 만들지 않고** None.

    플래그 확인이 가장 먼저다. 노드 생성·projection·collector·그래프·snapshot 어느 것도
    OFF 경로에서 실행되지 않는다.

    실패는 요청을 실패시키지 않는다. shadow 산출물이 없어도 생산 응답은 그대로 나가야 하므로
    분류된 오류만 남기고 None 을 돌려준다. 다만 **예외를 삼키지는 않는다** — 오류 코드와
    수량은 기록한다(간지·생년월일·사용자 ID 는 남기지 않는다).
    """
    if not should_build_relation_state_chain():
        return None
    try:
        chain = assemble_relation_state_chain(
            natal_nodes=relation_nodes_from_branches(
                layer=NATAL, branches=natal_branches,
            ),
            daewoon_nodes=relation_nodes_from_branches(
                layer="daewoon", branches=[("", daewoon_branch)],
            ) if daewoon_branch else (),
            sewoon_nodes=relation_nodes_from_branches(
                layer="sewoon", branches=[("", sewoon_branch)],
            ) if sewoon_branch else (),
            resolve_branch_hap=resolve_branch_hap,
            period_keys=period_keys,
        )
    except RelationStateAssemblyError as exc:
        _logger.info(
            "운 관계 상태 shadow 조립 실패 — error_kind=%s status=failure", exc.kind.value
        )
        return None
    _logger.debug(
        "운 관계 상태 shadow — status=success frames=%d duration_ms=%.1f",
        len(chain.frames), chain.build_duration_ms,
    )
    return chain

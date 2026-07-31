"""관계 상태 원장 — 불변 snapshot (P1-b1, 2026-08-01).

기준선 측정(0B)에서 확인한 것: 기존 resolver 는 **이전 변환 상태를 입력받지 않고 매번
재계산한다.** 그래서 대운에서 형성된 변환을 세운의 충이 해제하는 경로가 입력 자체에 없고,
`TRANSFORMATION_REVERSED` 를 기존 `blocked/partial/none` 조합으로 간접 표현할 수도 없다.

이 모듈은 **판정 엔진이 아니라 원장**이다. 이전 층에서 무엇이 어떻게 해석됐는지를 다음 층이
받을 수 있게 보존하는 것까지만 한다.

    한다        원래 오행 보존 · 확정 변환만 반영 · 불확정을 불확정으로 보존 ·
                부모 snapshot 연결 · 관계/근거 ID 보존
    하지 않는다  충이 들어왔으므로 변환을 해제했다는 판정 · 원래 오행으로 환원 ·
                경쟁 승자 결정 · effective_quality · 용희기구한 재평가 · 점수 변경

환원은 P1-c 다.

**가장 중요한 규칙은 불확정을 실수로 확정하지 않는 것이다.** 후속 계층이
`resolved_element` 를 보고 용희기구한을 매핑하므로, 근거 없이 확정하면 그 오류가 그대로
실현도 판정까지 전파된다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .luck_relation_graph import (
    LINK_COMPETES_FOR_DIRECTION,
    RelationDependencyGraph,
    RelationEdge,
    fingerprint_relation_dependency_graph,
)

#: snapshot 식별자 payload 버전.
SNAPSHOT_SCHEMA = "luck_relation_state_snapshot.v1"

#: 층위 순서 — 원국이 가장 위다. `LuckLayer` 에는 원국이 없어 여기서 문자열로 다룬다.
#: 계층 자동 조립은 P1-b2 범위이고, 여기서는 부모 방향 검증에만 쓴다.
LAYER_ORDER: tuple[str, ...] = ("natal", "daewoon", "sewoon", "wolwoon", "ilwoon")


class ResolutionStatus(StrEnum):
    """글자 하나의 오행 정체성 상태."""

    ORIGINAL = "original"                # 관계에 얽히지 않음
    BOUND = "bound"                      # 묶였으나 변하지 않음
    TRANSFORMED = "transformed"          # 확정 변환
    UNCONFIRMED = "unconfirmed"          # 후보는 있으나 확정 근거 없음


@dataclass(frozen=True)
class ElementResolutionState:
    """글자 한 자리의 상태. `resolved_element` 는 **확정일 때만** 채운다."""

    node_id: str
    original_element: str
    resolved_element: str | None
    resolution_status: ResolutionStatus
    governing_relation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationStateSnapshot:
    """한 층·한 기간의 불변 상태 원장."""

    snapshot_id: str
    graph_fingerprint: str
    parent_snapshot_id: str | None
    layer: str
    period_key: str
    element_states: tuple[ElementResolutionState, ...]
    active_relation_ids: tuple[str, ...]
    unresolved_relation_ids: tuple[str, ...]


def _is_confirmed_transform(edge: RelationEdge) -> bool:
    """확정 변환인가 — 세 조건을 **모두** 만족해야 한다."""
    return (
        edge.existing_tier == "confirmed"
        and edge.existing_mode == "transform"
        and bool(edge.target_element)
    )


def _competing_nodes(graph: RelationDependencyGraph) -> set[str]:
    """경쟁 링크에 얽힌 노드 — 여기 속하면 확정하지 않는다.

    P1-b1 은 승자를 정하지 않는다. 같은 노드에 서로 다른 target 이 걸려 있으면 단일 최종
    상태를 확정할 근거가 없다는 뜻이므로 UNCONFIRMED 로 낮춘다. resolver 판정을 뒤집는 것이
    아니라 **원장이 확정할 수 없음을 기록**하는 것이다.
    """
    out: set[str] = set()
    for dep in graph.relation_dependencies:
        if dep.link_type == LINK_COMPETES_FOR_DIRECTION:
            out.update(dep.shared_node_ids)
    return out


def _snapshot_id(
    *, layer: str, period_key: str, parent_id: str | None, graph_fp: str,
    states: Sequence[ElementResolutionState],
    active: Sequence[str], unresolved: Sequence[str],
) -> str:
    """snapshot 식별자 — `graph_fingerprint` 와 **분리**한다.

    같은 그래프라도 층·기간·부모·상태가 다르면 다른 snapshot 이다. 그래프 지문을 그대로
    식별자로 쓰면 그 차이가 사라진다.
    """
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "layer": layer,
        "period_key": period_key,
        "parent_snapshot_id": parent_id,
        "graph_fingerprint": graph_fp,
        "element_states": [
            {
                "node_id": s.node_id, "original_element": s.original_element,
                "resolved_element": s.resolved_element,
                "resolution_status": s.resolution_status.value,
                "governing_relation_ids": list(s.governing_relation_ids),
            }
            for s in states
        ],
        "active_relation_ids": list(active),
        "unresolved_relation_ids": list(unresolved),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_relation_state_snapshot(
    *,
    graph: RelationDependencyGraph,
    layer: str,
    period_key: str,
    previous_snapshot: RelationStateSnapshot | None = None,
) -> RelationStateSnapshot:
    """그래프 → 불변 상태 원장. **환원을 판정하지 않는다.**

    Args:
        graph: P1-a 의존 그래프.
        layer: 'natal' | 'daewoon' | 'sewoon' | 'wolwoon' | 'ilwoon'.
        period_key: 기간 식별자(예: '2003', '2003-07').
        previous_snapshot: 부모 층 snapshot. **명시적으로 전달**한다 — 숨은 저장소를
            조회하지 않는다.

    Returns:
        불변 snapshot. 부모 객체는 변경하지 않고 ID 만 기록한다.

    Raises:
        ValueError: 알 수 없는 층, 자기 자신을 부모로 지정, 부모가 하위 층인 경우.
    """
    if layer not in LAYER_ORDER:
        raise ValueError(f"알 수 없는 층: {layer!r}")
    parent_id: str | None = None
    if previous_snapshot is not None:
        if previous_snapshot.layer not in LAYER_ORDER:
            raise ValueError(f"부모의 층이 알 수 없다: {previous_snapshot.layer!r}")
        if LAYER_ORDER.index(previous_snapshot.layer) >= LAYER_ORDER.index(layer):
            # 상위→하위 방향만 허용한다. 자기 자신을 부모로 두는 경우도 여기서 걸린다.
            raise ValueError(
                f"부모 층이 현재 층보다 하위이거나 같다: "
                f"{previous_snapshot.layer!r} → {layer!r}"
            )
        parent_id = previous_snapshot.snapshot_id

    competing = _competing_nodes(graph)
    by_node: dict[str, list[RelationEdge]] = {}
    for edge in graph.edges:
        for nid in edge.member_node_ids:
            by_node.setdefault(nid, []).append(edge)

    states: list[ElementResolutionState] = []
    unresolved: set[str] = set()
    for node in sorted(graph.nodes, key=lambda n: n.node_id):
        edges = by_node.get(node.node_id, [])
        rel_ids = tuple(sorted(e.relation_id for e in edges))
        if not edges:
            states.append(ElementResolutionState(
                node.node_id, node.original_element, node.original_element,
                ResolutionStatus.ORIGINAL, (),
            ))
            continue

        confirmed = [e for e in edges if _is_confirmed_transform(e)]
        targets = {e.target_element for e in confirmed if e.target_element}
        if node.node_id in competing or len(targets) > 1:
            # 경쟁 중이거나 확정 target 이 여럿 — 단일 상태를 정할 근거가 없다.
            status, resolved = ResolutionStatus.UNCONFIRMED, None
            unresolved.update(rel_ids)
        elif len(targets) == 1:
            status, resolved = ResolutionStatus.TRANSFORMED, next(iter(targets))
        elif any(e.existing_mode == "bind" for e in edges):
            # 묶였으나 변하지 않음 — 원래 오행을 유지한다.
            status, resolved = ResolutionStatus.BOUND, node.original_element
        else:
            # partial · conditional · tier=none+mode=transform 등.
            status, resolved = ResolutionStatus.UNCONFIRMED, None
            unresolved.update(rel_ids)
        states.append(ElementResolutionState(
            node.node_id, node.original_element, resolved, status, rel_ids,
        ))

    graph_fp = fingerprint_relation_dependency_graph(graph)
    active = tuple(sorted(e.relation_id for e in graph.edges))
    unresolved_ids = tuple(sorted(unresolved))
    return RelationStateSnapshot(
        snapshot_id=_snapshot_id(
            layer=layer, period_key=period_key, parent_id=parent_id,
            graph_fp=graph_fp, states=states, active=active,
            unresolved=unresolved_ids,
        ),
        graph_fingerprint=graph_fp, parent_snapshot_id=parent_id,
        layer=layer, period_key=period_key,
        element_states=tuple(states), active_relation_ids=active,
        unresolved_relation_ids=unresolved_ids,
    )

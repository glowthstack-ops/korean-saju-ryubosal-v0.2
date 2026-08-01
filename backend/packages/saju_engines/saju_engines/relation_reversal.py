"""합화 환원 후보 탐지 (P1-c0, 2026-08-01).

**변환 미완성과 변환 후 환원은 같은 상태가 아니다.** 卯酉冲이 있어 亥卯未가 애초에 木으로
완성되지 못한 것과, 이미 木으로 작동하던 亥가 巳亥冲으로 다시 水로 돌아오는 것은 다른
사건이고 다른 서술을 낳는다.

그래서 환원은 **이전 층에서 확정된 변환**에만 성립한다. 충이 들어왔다고 항상 환원시키지
않으며(가 안 채택), 충의 통근·강약으로 환원 여부를 정하지도 않는다(나 안 채택). 통근·생조·
계절성은 작동 **강도**를 재는 요소라 구조적 해제 판정과 분리한다 — 그건 P2 다.

    R1  이전 상태가 TRANSFORMED
    R2  변환 결과가 원래 오행과 다름
    R3  변환 근거 관계가 남아 있음
    R4  현재 층에 충이 존재
    R5  그 충이 **같은 node_id** 를 직접 가격 (글자만 같은 것으로는 부족)
    R6  충에 현재 층에서 새로 유입된 노드가 포함
    R7  그 충이 이전 층에는 없었음
    R8  변환 근거 관계가 이전 snapshot 에서 active 였음
    R9  상충하는 변환 근거가 없어 대상을 하나로 확정 가능

**P1-c0 는 판정하지 않는다.** 후보와 기각 사유만 낸다. snapshot 을 바꾸지 않고
`TRANSFORMATION_REVERSED` 를 생성하지도 않는다 — 상태 적용은 P1-c1 이다. 탐지의 오류와
확정의 오류를 따로 검사하려고 나눈다.

형·파·해는 첫 버전의 환원 원인이 아니다(구조 근거만 보존). 합화 해제 효과는 별도 감수 후
확장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .branch_relation_collector import BranchRelationKind
from .luck_relation_graph import (
    LINK_POTENTIALLY_DISRUPTED_BY,
    RelationDependencyGraph,
    RelationEdge,
)
from .relation_state_snapshot import (
    ElementResolutionState,
    RelationStateSnapshot,
    ResolutionStatus,
)

#: 환원 원인으로 인정하는 관계. 형·파·해는 여기 없다.
REVERSAL_CAUSE_KINDS: frozenset[str] = frozenset({BranchRelationKind.CLASH.value})


class EvidencePath(StrEnum):
    """근거를 무엇으로 이었는가."""

    DEPENDENCY_LINK = "dependency_link"
    NODE_INTERSECTION_FALLBACK = "node_intersection_fallback"


class ReversalReason(StrEnum):
    """후보·기각 사유. 운영 로그에는 이 코드와 수량만 남긴다."""

    REVERSAL_BY_DEPENDENCY_LINK = "REVERSAL_BY_DEPENDENCY_LINK"
    REVERSAL_BY_NODE_INTERSECTION_FALLBACK = "REVERSAL_BY_NODE_INTERSECTION_FALLBACK"
    REVERSAL_EVIDENCE_CONFLICT = "REVERSAL_EVIDENCE_CONFLICT"
    NO_DIRECT_TRANSFORMED_NODE_HIT = "NO_DIRECT_TRANSFORMED_NODE_HIT"
    PREEXISTING_CONFLICT_WITH_CONFIRMED_TRANSFORM = (
        "PREEXISTING_CONFLICT_WITH_CONFIRMED_TRANSFORM"
    )
    TRANSFORMATION_PREVENTED = "TRANSFORMATION_PREVENTED"
    REVERSAL_UNCONFIRMED = "REVERSAL_UNCONFIRMED"
    NO_GOVERNING_RELATION = "NO_GOVERNING_RELATION"
    GOVERNING_RELATION_NOT_ACTIVE = "GOVERNING_RELATION_NOT_ACTIVE"
    NO_ELEMENT_CHANGE = "NO_ELEMENT_CHANGE"


@dataclass(frozen=True)
class ReversalCandidate:
    """환원 후보 1건. **확정이 아니다** — P1-c1 이 감수된 후보만 적용한다."""

    candidate_id: str
    node_id: str
    #: 이 후보가 어느 상태에서 나왔는가 — 적용 시점에 다시 대조한다. 후보는 다른 snapshot 에
    #: 잘못 적용될 수 있고, 그 오류가 조용히 통과하면 상태 원장이 오염된다.
    previous_snapshot_id: str
    current_snapshot_id: str
    current_graph_fingerprint: str
    original_element: str
    from_element: str
    to_element: str
    governing_relation_ids: tuple[str, ...]
    cause_relation_id: str
    disrupted_relation_ids: tuple[str, ...]
    evidence_path: EvidencePath
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReversalRejection:
    """기각 1건. 사유를 남기지 않으면 '탐지되지 않음' 과 '기각됨' 을 구별할 수 없다."""

    node_id: str
    reason_codes: tuple[str, ...]
    related_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReversalDetection:
    """한 층 전이의 탐지 결과."""

    previous_snapshot_id: str
    current_snapshot_id: str
    candidates: tuple[ReversalCandidate, ...]
    rejections: tuple[ReversalRejection, ...]

    def metrics(self) -> dict[str, int]:
        """저카디널리티 집계 — 간지·자리 문자열을 담지 않는다."""
        by_reason: dict[str, int] = {}
        for rej in self.rejections:
            for code in rej.reason_codes:
                by_reason[code] = by_reason.get(code, 0) + 1
        return {
            "reversal_candidate_count": len(self.candidates),
            "reversal_rejection_count": len(self.rejections),
            **{f"reason:{k}": v for k, v in sorted(by_reason.items())},
        }


def _clash_edges(graph: RelationDependencyGraph) -> tuple[RelationEdge, ...]:
    return tuple(e for e in graph.edges if e.relation_type in REVERSAL_CAUSE_KINDS)


def _disrupted_links(graph: RelationDependencyGraph) -> list[tuple[str, str]]:
    """(방해받는 관계, 방해하는 관계). 링크 방향은 P1-a 가 고정한 불변이다."""
    return [
        (d.relation_ids[0], d.relation_ids[1])
        for d in graph.relation_dependencies
        if d.link_type == LINK_POTENTIALLY_DISRUPTED_BY and len(d.relation_ids) == 2
    ]


def _has_unconfirmed_transform_candidate(
    graph: RelationDependencyGraph, node_id: str,
) -> bool:
    """이 자리에 **완성되지 않은 변환 후보**가 있는가.

    상태만 보면 안 된다. 관계 불확실성을 정체성에서 분리한 뒤로 미완성 후보를 가진 노드도
    ORIGINAL 이기 때문이다.
    """
    return any(
        node_id in e.member_node_ids
        and e.relation_type not in REVERSAL_CAUSE_KINDS
        and e.existing_mode in ("transform", "partial")
        and e.existing_tier != "confirmed"
        for e in graph.edges
    )


def _governing_targets(
    graph: RelationDependencyGraph, relation_ids: tuple[str, ...]
) -> set[str]:
    """근거 관계들이 가리키는 변환 오행 집합."""
    wanted = set(relation_ids)
    return {
        e.target_element for e in graph.edges
        if e.relation_id in wanted and e.target_element
    }


def _prevented(
    state: ElementResolutionState, hits: tuple[str, ...]
) -> ReversalRejection:
    """변환이 애초에 완성되지 않은 상태에 충이 온 경우 — 환원이 아니라 방해다."""
    return ReversalRejection(
        node_id=state.node_id,
        reason_codes=(ReversalReason.TRANSFORMATION_PREVENTED.value,),
        related_relation_ids=hits,
    )


def detect_reversal_candidates(
    *,
    previous_snapshot: RelationStateSnapshot,
    previous_graph: RelationDependencyGraph,
    current_snapshot: RelationStateSnapshot,
    current_graph: RelationDependencyGraph,
) -> ReversalDetection:
    """환원 후보와 기각 사유를 낸다. **상태를 바꾸지 않는다.**

    frame 이 아니라 snapshot·graph 를 직접 받는다 — frame 을 받으면 조립기와 순환 import 가
    생긴다. `previous_graph` 가 따로 필요한 이유는 R7(이전 층에 없던 충)·R9(상충 근거)가
    이전 층의 **엣지**를 봐야 하기 때문이다. snapshot 만으로는 관계 종류와 target 을 알 수 없다.

    Args:
        previous_snapshot: 이전 층 최종 snapshot.
        previous_graph: 이전 층 graph.
        current_snapshot: 현재 층 snapshot. 부모가 `previous_snapshot` 이어야 한다.
        current_graph: 현재 층 graph.

    Returns:
        후보·기각 목록. 결정적이며 입력 순서에 의존하지 않는다.

    Raises:
        ValueError: 두 frame 이 부모–자식 관계가 아닌 경우. 엉뚱한 층을 비교하면 '새로 들어온
            충' 판정이 통째로 무의미해진다.
    """
    if current_snapshot.parent_snapshot_id != previous_snapshot.snapshot_id:
        raise ValueError(
            "부모–자식 snapshot 이 아니다: "
            f"{previous_snapshot.layer!r} → {current_snapshot.layer!r}"
        )

    previous_clash_ids = {e.relation_id for e in _clash_edges(previous_graph)}
    previous_node_ids = {n.node_id for n in previous_graph.nodes}
    current_clashes = _clash_edges(current_graph)
    disrupted = _disrupted_links(current_graph)
    active_before = set(previous_snapshot.active_relation_ids)

    candidates: list[ReversalCandidate] = []
    rejections: list[ReversalRejection] = []

    for state in sorted(
        previous_snapshot.element_states, key=lambda s: s.node_id
    ):
        # R5·R6·R7 — 같은 자리를 직접 치는, 새 노드가 낀, 이전에 없던 충.
        hits: list[str] = []
        preexisting: list[str] = []
        for clash in current_clashes:
            if state.node_id not in clash.member_node_ids:
                continue
            if clash.relation_id in previous_clash_ids:
                preexisting.append(clash.relation_id)
                continue
            if not any(n not in previous_node_ids for n in clash.member_node_ids):
                continue
            hits.append(clash.relation_id)
        hits_t = tuple(sorted(hits))

        if state.resolution_status is not ResolutionStatus.TRANSFORMED:
            # R1 불충족 — 미완성 변환에 충이 온 것은 '방해' 이지 '환원' 이 아니다.
            # 상태는 ORIGINAL 일 수 있다(관계 불확실성이 정체성을 빼앗지 않으므로).
            # 그래서 상태가 아니라 **미완성 변환 후보의 존재**로 판정한다.
            if hits_t and _has_unconfirmed_transform_candidate(
                previous_graph, state.node_id
            ):
                rejections.append(_prevented(state, hits_t))
            continue

        if preexisting:
            # 이미 충이 있었는데 TRANSFORMED 였다면 환원 사건이 아니라 이전 확정 규칙의 모순일
            # 수 있다. 자동 환원하지 않고 진단만 남긴다.
            rejections.append(ReversalRejection(
                state.node_id,
                (ReversalReason.PREEXISTING_CONFLICT_WITH_CONFIRMED_TRANSFORM.value,),
                tuple(sorted(preexisting)),
            ))
            continue
        if state.resolved_element == state.original_element:
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.NO_ELEMENT_CHANGE.value,)))
            continue
        if not state.governing_relation_ids:
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.NO_GOVERNING_RELATION.value,)))
            continue
        if not set(state.governing_relation_ids) & active_before:
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.GOVERNING_RELATION_NOT_ACTIVE.value,),
                state.governing_relation_ids))
            continue
        if len(_governing_targets(previous_graph, state.governing_relation_ids)) > 1:
            # R9 — 서로 다른 target 이 이 노드를 지배하면 무엇이 환원되는지 정할 수 없다.
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.REVERSAL_UNCONFIRMED.value,),
                state.governing_relation_ids))
            continue

        governing = set(state.governing_relation_ids)
        dep_clashes = {
            affecting for subject, affecting in disrupted if subject in governing
        }
        both = sorted(dep_clashes & set(hits_t))

        if dep_clashes and hits_t and not both:
            # 우선 경로와 백업 경로가 서로 다른 관계를 가리킨다 — 자동 환원 금지.
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.REVERSAL_EVIDENCE_CONFLICT.value,),
                tuple(sorted(dep_clashes | set(hits_t)))))
            continue
        if not hits_t:
            rejections.append(ReversalRejection(
                state.node_id, (ReversalReason.NO_DIRECT_TRANSFORMED_NODE_HIT.value,),
                tuple(sorted(dep_clashes))))
            continue

        use_dependency = bool(both)
        for cause in (both or list(hits_t)):
            path = (
                EvidencePath.DEPENDENCY_LINK if use_dependency
                else EvidencePath.NODE_INTERSECTION_FALLBACK
            )
            reason = (
                ReversalReason.REVERSAL_BY_DEPENDENCY_LINK if use_dependency
                else ReversalReason.REVERSAL_BY_NODE_INTERSECTION_FALLBACK
            )
            candidates.append(ReversalCandidate(
                candidate_id=f"reversal:{state.node_id}|{cause}",
                node_id=state.node_id,
                previous_snapshot_id=previous_snapshot.snapshot_id,
                current_snapshot_id=current_snapshot.snapshot_id,
                current_graph_fingerprint=current_snapshot.graph_fingerprint,
                original_element=state.original_element,
                # 환원은 원래 오행으로 돌아가는 것이다. 새 오행을 계산하지 않는다.
                from_element=state.resolved_element or state.original_element,
                to_element=state.original_element,
                governing_relation_ids=state.governing_relation_ids,
                cause_relation_id=cause,
                disrupted_relation_ids=state.governing_relation_ids,
                evidence_path=path, reason_codes=(reason.value,),
            ))

    return ReversalDetection(
        previous_snapshot_id=previous_snapshot.snapshot_id,
        current_snapshot_id=current_snapshot.snapshot_id,
        candidates=tuple(sorted(candidates, key=lambda c: c.candidate_id)),
        rejections=tuple(sorted(rejections, key=lambda r: (r.node_id, r.reason_codes))),
    )

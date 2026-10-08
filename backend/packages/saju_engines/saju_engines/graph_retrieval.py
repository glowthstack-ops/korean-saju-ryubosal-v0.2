"""인메모리 Graph Retrieval (v2.2 Phase 2 T2.2, docs/04).

전체 검색 금지 — intent의 graphScope(EventKey 목록)에서 **역방향**으로 `triggers`
엣지를 따라 관련 신호 노드만 탐색한다(기본 5-hop 제한). 출력은 EvidenceBundle:
근거 경로(신호→이벤트 정규화) + 보조/충돌 근거 + 금기 표현 규칙 + 해석 힌트.
"""

from __future__ import annotations

from collections import defaultdict

from saju_engines.graph_builder import _norm_event
from saju_shared_types.events import EventKey
from saju_shared_types.graph import EventGraph, EvidenceBundle, EvidencePath, GraphEdge

_DEFAULT_MAX_HOPS = 5
# 역방향 탐색에서 신호 쪽으로 거슬러 올라갈 엣지 종류.
_UPSTREAM_EDGE_TYPES = {
    "triggers", "supports", "combines_with", "conflicts_with", "punishes", "activates",
}


class GraphIndex:
    """인접 리스트 기반 그래프 인덱스 — 수천 노드 수준 인메모리 탐색용."""

    def __init__(self, graph: EventGraph) -> None:
        """노드 맵과 in/out 인접 리스트를 구성한다."""
        self.graph = graph
        self.nodes = {n.id: n for n in graph.nodes}
        self.in_edges: dict[str, list[GraphEdge]] = defaultdict(list)
        self.out_edges: dict[str, list[GraphEdge]] = defaultdict(list)
        for e in graph.edges:
            self.in_edges[e.to].append(e)
            self.out_edges[e.from_].append(e)

    def label(self, node_id: str) -> str:
        """노드 라벨(없으면 id 그대로)."""
        node = self.nodes.get(node_id)
        return node.label if node else node_id

    # ── Retrieval ────────────────────────────────────────────────

    def retrieve(
        self, graph_scope: list[EventKey], max_hops: int = _DEFAULT_MAX_HOPS
    ) -> list[EvidenceBundle]:
        """graphScope의 각 이벤트에 대해 근거 묶음을 추출한다.

        Args:
            graph_scope: intent가 허용한 EventKey 목록(이 외 노드는 탐색하지 않음).
            max_hops: 이벤트로부터의 역방향 최대 깊이.

        Returns:
            이벤트별 EvidenceBundle 목록(graph_scope 순서 유지).
        """
        return [self._bundle_for(key, max_hops) for key in graph_scope]

    def _bundle_for(self, key: EventKey, max_hops: int) -> EvidenceBundle:
        event_id = f"event_{key}"
        paths = self._signal_paths(event_id, max_hops)

        prohibitions = [
            self.label(e.from_)
            for e in self.in_edges.get(event_id, [])
            if e.type == "prohibits_style"
        ]
        path_nodes = {nid for p in paths for nid in p.nodes}
        supports = sorted({
            e.from_
            for nid in path_nodes
            for e in self.in_edges.get(nid, [])
            if e.type == "supports" and e.from_ not in path_nodes
        })
        contradicts = self._contradicting_rules(event_id, key, path_nodes)
        hints = [
            self.label(nid)
            for nid in sorted(path_nodes)
            if self.nodes.get(nid) and self.nodes[nid].type == "interpretation_rule"
        ]
        return EvidenceBundle(
            event_key=key,
            paths=paths,
            supports=supports,
            contradicts=contradicts,
            prohibitions=prohibitions,
            interpretation_hints=hints,
        )

    def _rule_polarity(self, rule_id: str, key: EventKey) -> str | None:
        """해석 규칙 노드가 이 이벤트에 부여한 candidate polarity(정규화 키 기준)."""
        node = self.nodes.get(rule_id)
        if node is None or node.type != "interpretation_rule":
            return None
        for cand in node.attrs.get("candidates") or []:
            if _norm_event(str(cand.get("event", ""))) == str(key):
                return str(cand.get("polarity") or "") or None
        return None

    def _polarity_weights(self, event_id: str, key: EventKey) -> dict[str, float]:
        """이벤트를 촉발하는 규칙들의 극성별 triggers 가중 합(positive / negative_or_forced)."""
        weights: dict[str, float] = {"positive": 0.0, "negative_or_forced": 0.0}
        for e in self.in_edges.get(event_id, []):
            if e.type != "triggers":
                continue
            pol = self._rule_polarity(e.from_, key)
            if pol in weights:
                weights[pol] += float(e.weight or 0.0) or 1.0
        return weights

    def _contradicting_rules(
        self, event_id: str, key: EventKey, path_nodes: set[str]
    ) -> list[str]:
        """충돌 근거(docs/04 Retrieval 3) — 지배 극성과 **반대 극성**으로 이벤트를 촉발하는 규칙.

        컴파일 그래프에는 `contradicts` 엣지가 없다(빌더가 내지 않는다 — 2026-09-10 사문
        감사에서 이 목록이 항상 비어 LLM 이 상충 신호를 모른 채 서술하던 결함). 그래서
        retrieval 시점에 `triggers` 엣지의 candidate polarity 로 파생한다: 극성별 가중
        합이 큰 쪽(동률이면 positive)을 이 이벤트의 지배 입장으로 보고, 반대 극성
        (positive ↔ negative_or_forced) 규칙을 충돌 근거로 돌려준다. conditional·neutral
        은 어느 쪽의 반대도 아니다. 경로는 모든 규칙을 지나므로 경로 포함 여부로 거르지
        않는다(초판이 그렇게 걸러 전부 비었다).
        """
        del path_nodes  # 경로 포함 여부는 판정 기준이 아니다(설명은 docstring)
        weights = self._polarity_weights(event_id, key)
        if not any(weights.values()):
            return []
        dominant = "negative_or_forced" if (
            weights["negative_or_forced"] > weights["positive"]
        ) else "positive"
        opposite = "positive" if dominant == "negative_or_forced" else "negative_or_forced"
        # interpretation_hints 와 같이 **라벨**(규칙 문장)로 돌려준다 — LLM 프롬프트에
        # 그대로 실리므로 노드 ID(rule_career_03)는 읽을 수 없다.
        return sorted({
            self.label(e.from_)
            for e in self.in_edges.get(event_id, [])
            if e.type == "triggers" and self._rule_polarity(e.from_, key) == opposite
        })

    def _signal_paths(self, event_id: str, max_hops: int) -> list[EvidencePath]:
        """이벤트에서 역방향 DFS로 신호 노드까지의 경로를 수집(신호→이벤트로 뒤집어 반환)."""
        paths: list[EvidencePath] = []

        def walk(node_id: str, trail: list[str], weight: float, depth: int) -> None:
            incoming = [
                e for e in self.in_edges.get(node_id, [])
                if e.type in _UPSTREAM_EDGE_TYPES and e.from_ not in trail
            ]
            if depth >= max_hops or not incoming:
                if len(trail) > 1:  # 이벤트 단독 경로는 제외
                    paths.append(EvidencePath(
                        nodes=list(reversed(trail)),
                        readable=[self.label(n) for n in reversed(trail)],
                        weight_sum=round(weight, 4),
                    ))
                return
            for e in incoming:
                walk(e.from_, [*trail, e.from_], weight + (e.weight or 0.0), depth + 1)

        walk(event_id, [event_id], 0.0, 0)
        # 가중 합 큰 경로 우선.
        return sorted(paths, key=lambda p: -p.weight_sum)

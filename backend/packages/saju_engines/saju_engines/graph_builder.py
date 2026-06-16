"""Event Graph Builder (v2.2 Phase 2 T2.1, docs/04).

사전(JSON) 원본 → 이벤트 후보 그래프(`EventGraph`) 컴파일. 운영 코드는 이 컴파일
스냅샷(`compiled/event_graph_vX.Y.Z.json`)만 읽는다(절대 원칙 5 — 원본 직접 로드 금지).

노드 구성: 오행/천간/지지/십성(명식) + 관계(rel_*) + 판정(용·희·기·구신) + 이벤트 +
해석 규칙(events/<domain>.json 신호 매핑) + 금기 규칙(prohibition_rule).
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.event_taxonomy_v2 import (
    EVENT_KO,
    EVENT_TYPE,
    LEGACY_EVENT_KEY_MAP,
    PROHIBITIONS,
)
from saju_shared_types.graph import EventGraph, GraphEdge, GraphNode

from .dictionaries import (
    ElementsFile,
    EventMappingFile,
    RelationsFile,
    StemsFile,
    TenGodsFile,
)

GRAPH_VERSION = "1.1.0"

# 관계 type → 참여 글자 엣지 종류 (docs/04 EdgeType).
_PARTICIPANT_EDGE: dict[str, str] = {
    "stem_combination": "combines_with",
    "stem_clash": "conflicts_with",
    "six_combination": "combines_with",
    "three_harmony": "combines_with",
    "directional": "combines_with",
    "branch_clash": "conflicts_with",
    "punishment_triple": "punishes",
    "punishment_mutual": "punishes",
    "self_punishment": "punishes",
    "branch_break": "conflicts_with",
    "harm": "conflicts_with",
    "wonjin": "conflicts_with",
}

# 천간 노드를 참여자로 갖는 관계 type(나머지는 지지 노드).
_STEM_PARTICIPANT_TYPES = {"stem_combination", "stem_clash"}

# 관계 type → 그래프 노드 type (docs/04 NodeType의 관계 노드 분류).
_RELATION_NODE_TYPE: dict[str, str] = {
    "stem_combination": "combination",
    "six_combination": "combination",
    "three_harmony": "combination",
    "directional": "combination",
    "stem_clash": "clash",
    "branch_clash": "clash",
    "punishment_triple": "punishment",
    "punishment_mutual": "punishment",
    "self_punishment": "self_punishment",
    "branch_break": "break",
    "harm": "harm",
    "wonjin": "harm",  # docs/04 NodeType에 원진 분류가 없어 해 계열로 수록(검수 대상)
    "void": "void",
    "bokeum": "fuyin",
    "byeongjon": "duplication",
    "ganyeojidong": "ganyeo_jidong",
}

# 판정 노드 4종 (docs/04 NodeType — 한신은 노드 타입에 없어 규칙 attrs로만 표현).
_FAVORABILITY_NODES = {
    "용신": ("yongsin", "용신"),
    "희신": ("huisin", "희신"),
    "기신": ("gisin", "기신"),
    "구신": ("gusin", "구신"),
}

# 원국 횡재 그릇(natalWealthCapacity) 노드 — windfall 해석 규칙이 그릇 강도에 걸린다(Phase 1).
_WEALTH_CAPACITY_NODES = {
    "strong": ("wealth_capacity_strong", "원국 횡재 그릇(강)"),
    "moderate": ("wealth_capacity_moderate", "원국 횡재 그릇(중)"),
}

# 금기 표현 규칙은 event_taxonomy_v2.PROHIBITIONS(21키, 경쟁·고시 보호 포함)를 정적 부착한다.


def _load(directory: Path, rel: str) -> dict:
    """사전 JSON 파일 로드."""
    return json.loads((directory / rel).read_text(encoding="utf-8"))


def _stem_branch_nodes(directory: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    """오행/천간/지지/십성 노드 + 생극·has_element 엣지."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    elements = ElementsFile.model_validate(_load(directory, "common/elements.json"))
    for el in elements.items:
        nodes.append(GraphNode(
            id=f"element_{el.element}", type="element", label=f"{el.element}({el.ko})",
        ))
    for el in elements.items:
        edges.append(GraphEdge(
            from_=f"element_{el.element}", to=f"element_{el.generates}", type="generates",
        ))
        edges.append(GraphEdge(
            from_=f"element_{el.element}", to=f"element_{el.controls}", type="overcomes",
        ))

    stems = StemsFile.model_validate(_load(directory, "common/stems.json"))
    for st in stems.items:
        nodes.append(GraphNode(
            id=f"stem_{st.stem}", type="stem", label=st.stem,
            attrs={
                "yinYang": st.yin_yang,
                "tenGodByDayMaster": st.ten_god_by_day_master,
                "domains": st.domains,
            },
        ))
        edges.append(GraphEdge(
            from_=f"stem_{st.stem}", to=f"element_{st.element}", type="has_element",
        ))

    for br in _branch_items(directory):
        nodes.append(GraphNode(
            id=f"branch_{br['branch']}", type="branch", label=br["branch"],
            attrs={"zodiac": br["zodiac"], "hiddenStems": br["hiddenStems"]},
        ))
        edges.append(GraphEdge(
            from_=f"branch_{br['branch']}", to=f"element_{br['element']}", type="has_element",
        ))

    ten_gods = TenGodsFile.model_validate(_load(directory, "common/ten_gods.json"))
    for tg in ten_gods.items:
        nodes.append(GraphNode(
            id=f"tengod_{tg.ten_god}", type="ten_god", label=tg.ten_god,
            attrs={"group": tg.group, "domains": tg.domains},
        ))
    return nodes, edges


def _branch_items(directory: Path) -> list[dict]:
    """branches.json 항목을 dict로 반환(지장간은 attrs로만 쓰여 모델 변환 불필요)."""
    from .dictionaries import BranchesFile

    parsed = BranchesFile.model_validate(_load(directory, "common/branches.json"))
    return [item.model_dump(by_alias=True) for item in parsed.items]


def _relation_nodes(directory: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    """관계(rel_*) 노드 + 참여 글자 엣지 + 관계→이벤트 triggers 엣지."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    relations = RelationsFile.model_validate(_load(directory, "relations.json"))
    for rel in relations.items:
        if not rel.enabled:
            continue  # 암합 등 기본 비활성 관계는 그래프 미수록(docs/09 2-2)
        nodes.append(GraphNode(
            id=rel.id, type=_RELATION_NODE_TYPE.get(rel.type, "combination"), label=rel.name,
            attrs={
                "relationType": rel.type,
                "participants": rel.participants,
                "resultElement": rel.result_element,
                "possibleModes": rel.possible_modes,
                "pattern": rel.pattern,
                "baseScore": rel.base_score,
                "reviewed": rel.reviewed,
            },
        ))
        edge_type = _PARTICIPANT_EDGE.get(rel.type)
        if edge_type:
            prefix = "stem" if rel.type in _STEM_PARTICIPANT_TYPES else "branch"
            for ch in dict.fromkeys(rel.participants):  # 자형(같은 글자 2회)은 1회만
                edges.append(GraphEdge(from_=f"{prefix}_{ch}", to=rel.id, type=edge_type))
        if rel.result_element:
            edges.append(GraphEdge(
                from_=rel.id, to=f"element_{rel.result_element}", type="has_element",
            ))
        for ev in rel.event_domains:
            norm = _norm_event(ev)
            if norm is None:
                continue
            edges.append(GraphEdge(
                from_=rel.id, to=f"event_{norm}", type="triggers",
                weight=rel.base_score, modes=rel.possible_modes,
            ))
    return nodes, edges


def _event_nodes(directory: Path) -> list[GraphNode]:
    """이벤트 노드 (21키 taxonomy_v2 전수, Phase 7)."""
    return [
        GraphNode(
            id=f"event_{key.value}", type="event", label=ko,
            attrs={"eventType": EVENT_TYPE.get(key, "progress")},
        )
        for key, ko in EVENT_KO.items()
    ]


_VALID_EVENTS: frozenset[str] = frozenset(str(k) for k in EVENT_KO)


def _norm_event(ev: str) -> str | None:
    """구/신 이벤트 키 → 21키. 구키는 LEGACY로 리맵, 미매핑은 None(엣지 생략)."""
    if ev in _VALID_EVENTS:
        return ev
    mapped = LEGACY_EVENT_KEY_MAP.get(ev)
    return mapped.value if mapped is not None else None


def _rule_nodes(directory: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    """해석 규칙 노드 (events/<domain>.json 신호 매핑) + supports/triggers 엣지."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    for path in sorted((directory / "events").glob("*.json")):
        if path.name == "taxonomy.json":
            continue
        mapping = EventMappingFile.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        for idx, item in enumerate(mapping.items):
            rule_id = f"rule_{mapping.domain}_{idx:02d}"
            signal = item.signal
            nodes.append(GraphNode(
                id=rule_id, type="interpretation_rule",
                label=item.note or rule_id,
                attrs={
                    "signal": signal.model_dump(by_alias=True, exclude_none=True),
                    "candidates": [c.model_dump(by_alias=True) for c in item.event_candidates],
                    "reviewed": item.reviewed,
                },
            ))
            if signal.ten_god:
                edges.append(GraphEdge(
                    from_=f"tengod_{signal.ten_god}", to=rule_id, type="supports",
                ))
            if signal.favorability in _FAVORABILITY_NODES:
                node_type, _label = _FAVORABILITY_NODES[signal.favorability]
                edges.append(GraphEdge(from_=node_type, to=rule_id, type="supports"))
            if signal.natal_wealth_capacity in _WEALTH_CAPACITY_NODES:
                cap_node, _cap_label = _WEALTH_CAPACITY_NODES[signal.natal_wealth_capacity]
                edges.append(GraphEdge(from_=cap_node, to=rule_id, type="supports"))
            for cand in item.event_candidates:
                norm = _norm_event(cand.event)
                if norm is None:
                    continue
                edges.append(GraphEdge(
                    from_=rule_id, to=f"event_{norm}", type="triggers",
                    weight=cand.score,
                ))
    return nodes, edges


def build_event_graph(directory: Path, updated_at: str | None = None) -> EventGraph:
    """사전 디렉토리에서 이벤트 그래프를 컴파일한다.

    Args:
        directory: 사전 원본 루트(`backend/dictionaries`).
        updated_at: 스냅샷 생성 시각(ISO). 빌드 스크립트가 주입(라이브러리는 시계 미사용).

    Returns:
        노드/엣지를 채운 EventGraph (semver = GRAPH_VERSION).
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    base_nodes, base_edges = _stem_branch_nodes(directory)
    nodes += base_nodes
    edges += base_edges

    for _fav, (node_type, label) in _FAVORABILITY_NODES.items():
        nodes.append(GraphNode(id=node_type, type=node_type, label=label))

    for _band, (cap_id, cap_label) in _WEALTH_CAPACITY_NODES.items():
        nodes.append(GraphNode(id=cap_id, type="wealth_capacity", label=cap_label))

    nodes += _event_nodes(directory)

    rel_nodes, rel_edges = _relation_nodes(directory)
    nodes += rel_nodes
    edges += rel_edges

    rule_nodes, rule_edges = _rule_nodes(directory)
    nodes += rule_nodes
    edges += rule_edges

    for pid, label, events in PROHIBITIONS:
        nodes.append(GraphNode(
            id=pid, type="prohibition_rule", label=label, attrs={"reviewed": False},
        ))
        for ev in events:
            norm = _norm_event(ev)
            if norm is not None:
                edges.append(GraphEdge(from_=pid, to=f"event_{norm}", type="prohibits_style"))

    return EventGraph(version=GRAPH_VERSION, updated_at=updated_at, nodes=nodes, edges=edges)


def save_event_graph(graph: EventGraph, compiled_dir: Path) -> Path:
    """그래프를 semver 파일명으로 저장하고 경로를 반환한다."""
    compiled_dir.mkdir(parents=True, exist_ok=True)
    path = compiled_dir / f"event_graph_v{graph.version}.json"
    path.write_text(
        json.dumps(graph.model_dump(by_alias=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_event_graph(path: Path) -> EventGraph:
    """컴파일 스냅샷을 로드한다(운영 경로 — 원본 사전 직접 로드 금지)."""
    return EventGraph.model_validate(json.loads(path.read_text(encoding="utf-8")))

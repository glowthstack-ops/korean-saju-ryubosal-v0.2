"""Event Graph schemas (v2.2 Phase 2, docs/04).

사전(JSON)을 컴파일한 이벤트 후보 그래프의 노드/엣지와, Graph Retrieval의 출력
(EvidenceBundle/EvidencePath)을 정의한다. 그래프는 수천 노드 수준의 인메모리
인접 리스트 탐색을 전제로 한다(그래프 DB 미도입 — docs/04 구현 방침).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .events import EventKey

# docs/04 NodeType — 명식/운/관계/판정/이벤트/규칙 노드.
NODE_TYPES = (
    "stem", "branch", "hidden_stem", "ten_god", "element", "palace", "twelve_stage",
    "daewoon", "year_luck", "month_luck", "day_luck",
    "combination", "clash", "punishment", "break", "harm", "self_punishment",
    "void", "duplication", "fuyin", "ganyeo_jidong",
    "yongsin", "huisin", "gisin", "gusin", "strength", "excess_deficiency",
    "event",
    "interpretation_rule", "prohibition_rule",
)

# docs/04 EdgeType.
EDGE_TYPES = (
    "contains", "has_ten_god", "has_element", "has_palace",
    "combines_with", "conflicts_with", "punishes", "generates", "overcomes",
    "activates", "boosts", "weakens", "cancels",
    "is_favorable_for", "is_unfavorable_for",
    "triggers", "manifests_as", "supports", "contradicts", "prohibits_style",
)


class GraphNode(BaseModel):
    """그래프 노드 (docs/04 GraphNode). id 예: 'stem_甲', 'rel_甲己合', 'event_career_change'."""

    id: str
    type: str  # NODE_TYPES 중 하나
    label: str  # 사용자 노출용 한글
    attrs: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """그래프 엣지 (docs/04 GraphEdge). JSON 키 'from'은 Python 예약어라 alias 처리."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    type: str  # EDGE_TYPES 중 하나
    weight: float | None = None  # triggers 엣지의 base 기여도(0~1)
    modes: list[str] = Field(default_factory=list)  # 합화/합반/합래/합거 등


class EventGraph(BaseModel):
    """컴파일된 이벤트 그래프 스냅샷 (compiled/event_graph_vX.Y.Z.json)."""

    version: str  # semver
    updated_at: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class EvidencePath(BaseModel):
    """근거 경로 한 줄 (docs/04 EvidencePath).

    nodes는 신호→이벤트 순서의 노드 ID, readable은 사용자/LLM용 한글 표현이다.
    """

    nodes: list[str] = Field(default_factory=list)
    readable: list[str] = Field(default_factory=list)
    weight_sum: float = 0.0


class EvidenceBundle(BaseModel):
    """이벤트 한 건의 근거 묶음 (docs/04 EvidenceBundle, Retrieval 출력)."""

    event_key: EventKey
    paths: list[EvidencePath] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)  # 보조 근거 노드 ID
    contradicts: list[str] = Field(default_factory=list)  # 충돌 근거 노드 ID
    prohibitions: list[str] = Field(default_factory=list)  # 금기 표현 규칙
    interpretation_hints: list[str] = Field(default_factory=list)

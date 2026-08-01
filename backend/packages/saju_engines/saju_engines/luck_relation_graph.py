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

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

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

class BranchHapLike(Protocol):
    """`resolve_branch_hap` 결과가 만족해야 하는 최소 계약.

    구체 타입을 import 하면 saju_engines → manse_analysis 방향 의존이 생긴다. 어댑터가
    실제로 읽는 필드만 Protocol 로 고정한다.
    """

    @property
    def kind(self) -> str: ...
    @property
    def members(self) -> tuple[str, ...]: ...
    @property
    def positions(self) -> tuple[str, ...]: ...
    @property
    def transform_element(self) -> str | None: ...
    @property
    def transform_tier(self) -> str: ...
    @property
    def hap_mode(self) -> str: ...


class BranchRelationLike(Protocol):
    """파괴 관계 인스턴스의 최소 계약."""

    @property
    def relation_id(self) -> str: ...
    @property
    def relation_family(self) -> str: ...
    @property
    def kind(self) -> object: ...
    @property
    def member_node_ids(self) -> tuple[str, ...]: ...


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


#: 지문 payload 버전. 대상 필드나 정규화 규칙을 바꾸면 v2 로 올린다 — 정의를 조용히
#: 바꾸면 과거 snapshot 과 현재 snapshot 을 비교할 수 없게 된다.
FINGERPRINT_SCHEMA = "luck_relation_graph_fingerprint.v1"


def relation_graph_fingerprint_payload(
    graph: RelationDependencyGraph,
) -> dict[str, object]:
    """지문 계산용 **정규 의미 투영본**.

    DTO 를 통째로 직렬화하지 않는다. 그러면 디버그 필드 추가·메트릭·사람이 읽는 문구 수정·
    필드 순서 변경만으로도 지문이 불필요하게 바뀐다. 반대로 ID 목록만 해시하면 같은 ID 에
    `tier=confirmed/none` 처럼 **상태를 가르는 차이**를 감지하지 못한다.

    그래서 상태 산출에 실제로 영향을 주는 필드만 담는다. `normalized_observation` 은
    tier/mode 에서 파생된 값이라 넣지 않는다(중복이며, 파생 규칙이 바뀌면 이유 없이 지문이
    흔들린다). `evidence` 는 설명 문자열이라 제외한다.

    배열은 명시적으로 정렬한다 — `sort_keys=True` 만으로는 재현되지 않는다. 다만
    `relation_ids` 는 정렬하지 않는다: `POTENTIALLY_BLOCKED_BY` 는 (방해받는 쪽, 방해하는 쪽)
    순서가 곧 의미라서 정렬하면 인과가 사라진다. 대칭인 `COMPETES_FOR_DIRECTION` 은 생성
    시점에 이미 정렬돼 들어온다.
    """
    return {
        "schema": FINGERPRINT_SCHEMA,
        "nodes": [
            {
                "node_id": n.node_id, "layer": n.layer,
                "pillar_position": n.pillar_position, "component": n.component,
                "character": n.character, "original_element": n.original_element,
            }
            for n in sorted(graph.nodes, key=lambda x: x.node_id)
        ],
        "edges": [
            {
                "relation_id": e.relation_id, "relation_family": e.relation_family,
                "relation_type": e.relation_type,
                "member_node_ids": sorted(e.member_node_ids),
                "existing_tier": e.existing_tier, "existing_mode": e.existing_mode,
                "target_element": e.target_element,
                "source_resolver": e.source_resolver,
            }
            for e in sorted(graph.edges, key=lambda x: x.relation_id)
        ],
        "dependencies": [
            {
                "dependency_id": d.dependency_id,
                "relation_ids": list(d.relation_ids),   # 방향 보존 — 정렬 금지
                "link_type": d.link_type,
                "shared_node_ids": sorted(d.shared_node_ids),
                "target_elements": sorted(d.target_elements),
            }
            for d in sorted(graph.relation_dependencies, key=lambda x: x.dependency_id)
        ],
    }


def fingerprint_relation_dependency_graph(graph: RelationDependencyGraph) -> str:
    """정규 payload 의 SHA-256 **전체 64자**.

    Python `hash()` 나 dataclass 기본 해시는 프로세스 간 안정성이 없어 쓰지 않는다.
    축약값은 로그 표시용일 뿐 식별자로 쓰지 않는다.
    """
    payload = relation_graph_fingerprint_payload(graph)
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def build_luck_node_index(
    nodes: Sequence[RelationNode],
) -> dict[tuple[str, str], str]:
    """`adapt_branch_hap_results` 용 (자리, 글자) → node_id 인덱스. **모호하면 던진다.**

    이 인덱스를 호출부가 dict 리터럴로 손수 만들면 키 충돌이 조용한 덮어쓰기가 된다.
    P1-b1.5 실측에서 그게 드러났다.

        resolve_branch_hap 은 대운·세운·월운을 모두 `'luck'` 한 자리로 표기한다.
        대운 未 와 세운 未 가 함께 오면 ('luck', '未') 키가 겹치고, 나중 것이 앞 것을
        덮어써 **대운 未 의 참여가 세운 未 로 기록된다.**

    글자만 같고 자리가 다른 노드를 혼동하지 않는 것이 P1-a 이후 이 계층의 전제다. 층 사이
    상태 승계(P1-b2)와 환원 판정(P1-c)은 이전 층의 글자를 node_id 로 다시 찾으므로, 여기서
    한 번 잘못 붙으면 그 오류가 그대로 승계된다.

    resolver 어휘에 층 구분이 없어 키를 더 쪼갤 방법이 없다. 그래서 **조용히 하나를 고르지
    않고 예외를 던진다.** 어느 쪽을 버릴지는 이 함수가 정할 문제가 아니다.

    Args:
        nodes: 참여 가능한 자리 전체. 원국은 `pillar_position`, 운은 `'luck'` 로 키를 만든다.

    Returns:
        (자리, 글자) → node_id.

    Raises:
        ValueError: 같은 키에 서로 다른 node_id 가 오는 경우.
    """
    index: dict[tuple[str, str], str] = {}
    for node in sorted(nodes, key=lambda n: n.node_id):
        if node.component != "branch":
            continue
        key = (node.pillar_position if node.layer == "natal" else "luck", node.character)
        existing = index.get(key)
        if existing is not None and existing != node.node_id:
            raise ValueError(
                f"자리·글자 키가 겹친다: {key!r} → {existing!r} / {node.node_id!r}. "
                "resolver 의 positions 어휘에 층 구분이 없어 구별할 수 없다."
            )
        index[key] = node.node_id
    return index


def adapt_branch_hap_results(
    *,
    resolver_results: Sequence[BranchHapLike],
    node_index: Mapping[tuple[str, str], str],
    source_resolver: str = "branch_hap",
) -> tuple[RelationEdge, ...]:
    """기존 `resolve_branch_hap` 결과 → 엣지. **순수 함수이며 플래그를 모른다.**

    어댑터는 원시 의미를 그대로 옮긴다. 다음은 하지 않는다.

        tier=none + mode=transform 을 TRANSFORMED 로 확정
        충 때문에 어떤 합이 차단됐다고 확정
        경쟁 관계의 승자 결정
        기존 resolver 결과 수정

    자리는 **추측하지 않는다.** resolver 의 `positions` 와 `members` 를 짝지어
    `node_index[(position, character)]` 로 조회한다. 글자만 보고 노드를 고르면 원국에 戌 이
    둘일 때 두 관계가 허위로 붙는다(P1-a 실측: 링크 9건 → 자리 반영 후 7건).

    Args:
        resolver_results: `resolve_branch_hap` 반환값.
        node_index: (자리, 글자) → node_id. 자리는 resolver 의 positions 어휘를 쓴다
            ('year'|'month'|'day'|'hour'|'luck').
        source_resolver: 출처 표기.

    Returns:
        엣지 목록. 조회 실패한 관계는 **조용히 건너뛰지 않고** 제외 사유를 남길 수 없으므로
        ValueError 를 던진다 — 자리 매칭 실패는 인덱스 구성 오류이지 정상 상태가 아니다.

    Raises:
        ValueError: positions/members 길이가 다르거나 인덱스에 없는 자리·글자.
    """
    edges: list[RelationEdge] = []
    for res in resolver_results:
        positions = tuple(res.positions)
        members = tuple(res.members)
        # `members` 는 관계를 이루는 **글자쌍**, `positions` 는 실제로 참여한 **자리**다.
        # 길이가 다른 것이 정상이다 — 半合 卯未 는 원국 未·운 未 가 모두 참여해
        # members 2 / positions 3 이 된다. 짝지어 zip 하면 안 된다.
        member_ids: list[str] = []
        for pos in positions:
            hit = [node_index[(pos, ch)] for ch in members if (pos, ch) in node_index]
            if not hit:
                raise ValueError(
                    f"node_index 에 없는 자리: {pos!r} (members={members})"
                )
            member_ids.extend(hit)
        member_ids = sorted(set(member_ids))
        family = f"{res.kind}:{''.join(members)}"
        edges.append(edge_from_resolution(
            relation_id=f"{family}@{'+'.join(positions)}",
            relation_family=family, relation_type=str(res.kind),
            member_node_ids=member_ids, tier=res.transform_tier,
            mode=res.hap_mode, target_element=res.transform_element,
            source_resolver=source_resolver,
        ))
    return tuple(sorted(edges, key=lambda e: e.relation_id))


def edges_from_branch_relations(
    instances: Sequence[BranchRelationLike],
) -> tuple[RelationEdge, ...]:
    """`BranchRelationInstance` → 엣지(파괴 관계 쪽)."""
    return tuple(sorted(
        (
            RelationEdge(
                relation_id=str(i.relation_id), relation_family=str(i.relation_family),
                relation_type=str(i.kind), member_node_ids=tuple(i.member_node_ids),
                existing_tier=None, existing_mode=None, target_element=None,
                source_resolver="branch_relation_collector",
                # 탐지와 효과를 분리한다 — 형·파·해는 수집하되 변환 해제 후보가 아니다.
                normalized_observation={
                    "breaks_transformation": bool(
                        getattr(i, "breaks_transformation", False)
                    )
                },
            )
            for i in instances
        ),
        key=lambda e: e.relation_id,
    ))


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
            # 형·파·해는 **구조 정보만** 남긴다. '형·파·해가 있으면 합화가 풀린다' 는
            # 일반화를 하지 않는다 — 근거가 확인된 것은 충뿐이다(巳亥冲·卯酉冲).
            # 그렇지 않으면 사례 A 에서 링크가 20건으로 불어난다(실측).
            if not dis.normalized_observation.get("breaks_transformation", True):
                continue
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

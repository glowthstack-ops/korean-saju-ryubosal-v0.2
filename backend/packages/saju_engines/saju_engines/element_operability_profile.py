"""오행 실현도 — 역할 중립 신호 추출 (P2-1, 2026-08-01).

이 모듈의 질문은 하나다.

    지금 이 水·木·火·土·金 주변에 **어떤 구조 신호가 있는가**

"그래서 얼마나 작동하는가" 는 묻지 않는다(P2-2). 용신인지 기신인지도 모른다(P2-b). 등급·
앵커값·활성도를 만들지 않으며, 신호를 강도 계수로 환산하지도 않는다 — 지장간 정기/중기/여기
구분은 evidence 로만 남기고 가중치로 바꾸지 않는다.

P2-0에서 확정한 재사용 경계를 따른다.

    쓴다        hidden_stems_for · GENERATES · CONTROLS · main_hidden_stem ·
                twelve_unseong · P1-b0 위치 기반 관계 인스턴스
    쓰지 않는다  compute_rooting(일간 전용) · _clashed_branches(글자 기반·원국 한정) ·
                _ROOT_KIND_FACTOR · _root_reliability (둘 다 신강약 캘리브레이션 값)

**금생수는 水의 뿌리가 아니다.** 기존 `resource_root`(인성 통근)를 뿌리로 세면 그 구분이
무너진다. 생조는 `SupportProfile` 로 완전히 분리한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import (
    CONTROLS,
    GENERATES,
    STEM_ELEMENT,
    hidden_stems_for,
    main_hidden_stem,
)
from saju_shared_types.enums import Branch, Stem

from .branch_relation_collector import BranchRelationInstance, BranchRelationKind
from .luck_relation_graph import RelationNode

#: 생조원을 실제로 흔든다고 보는 관계. P1-b0 와 같은 기준(충 한정)이다.
_DISRUPTIVE_KINDS = frozenset({BranchRelationKind.CLASH})


class RootDepth(StrEnum):
    """직접 뿌리가 지장간의 **어느 자리**에 있는가.

    `NONE` 과 `UNKNOWN` 은 다르다.

        NONE      해당 범위의 지지를 정상적으로 전부 조사했고 같은 오행 뿌리가 없다
        UNKNOWN   resolved_element 미확정 등으로 전수 판정 자체가 불가능하다

    간접 생조는 여기 들어오지 않는다 — 금생수를 水의 `RESIDUAL_QI` 로 올리면 뿌리와 생조의
    구분이 무너진다.
    """

    MAIN_QI = "main_qi"
    MIDDLE_QI = "middle_qi"
    RESIDUAL_QI = "residual_qi"
    NONE = "none"
    UNKNOWN = "unknown"


#: 깊이 우선순위. MAIN_QI > MIDDLE_QI > RESIDUAL_QI > NONE.
_DEPTH_ORDER: dict[RootDepth, int] = {
    RootDepth.MAIN_QI: 3, RootDepth.MIDDLE_QI: 2,
    RootDepth.RESIDUAL_QI: 1, RootDepth.NONE: 0, RootDepth.UNKNOWN: -1,
}

#: 지장간 종류 → 깊이. **배열 순서나 길이로 역할을 추측하지 않는다** — 엔진 SSOT 가
#: `HiddenStemType` 으로 이미 정기·중기·여기를 구분하므로 그것만 읽는다.
_DEPTH_BY_HIDDEN_TYPE: dict[str, RootDepth] = {
    "main": RootDepth.MAIN_QI, "middle": RootDepth.MIDDLE_QI,
    "residual": RootDepth.RESIDUAL_QI,
}


def hidden_stems_with_depth(branch: Branch) -> tuple[tuple[str, RootDepth], ...]:
    """지지 → ((지장간, 깊이), …). 깊이 해석을 여기 한 곳에 고정한다.

    호출부마다 `hidden_stems_for` 의 배열을 각자 해석하면 표기가 갈리고, 지지마다 지장간
    개수가 달라(1~3) 길이로 역할을 배정하면 틀린다.
    """
    return tuple(
        (stem.value, _DEPTH_BY_HIDDEN_TYPE[str(getattr(kind, "value", kind))])
        for stem, kind, _budget in hidden_stems_for(branch)
        if str(getattr(kind, "value", kind)) in _DEPTH_BY_HIDDEN_TYPE
    )


def combine_root_depths(*depths: RootDepth) -> RootDepth:
    """여러 범위의 깊이를 합친다 — 가장 깊은 자격이 대표다.

    한 범위가 UNKNOWN 이면 전체를 UNKNOWN 으로 둔다. 다른 범위에 정기 뿌리가 있어도
    전수 판정이 불가능했던 범위가 있으면 "확실히 MAIN_QI" 라고 말할 수 없다(보수적).
    """
    if not depths:
        return RootDepth.NONE
    if any(d is RootDepth.UNKNOWN for d in depths):
        return RootDepth.UNKNOWN
    return max(depths, key=lambda d: _DEPTH_ORDER[d])


class RootStatus(StrEnum):
    """직접 뿌리 — **같은 오행**만 센다."""

    DIRECT_NATAL_ROOT = "direct_natal_root"
    DIRECT_TRANSIT_ROOT = "direct_transit_root"
    DIRECT_NATAL_AND_TRANSIT_ROOT = "direct_natal_and_transit_root"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class SupportStatus(StrEnum):
    """간접 생조 경로. 뿌리와 섞지 않는다."""

    INDIRECT_GENERATION_STABLE = "indirect_generation_stable"
    INDIRECT_GENERATION_DISRUPTED = "indirect_generation_disrupted"
    INDIRECT_GENERATION_PRESENT_MIXED = "indirect_generation_present_mixed"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class SupportPathStatus(StrEnum):
    STABLE = "stable"
    DISRUPTED = "disrupted"


class CutOffStatus(StrEnum):
    """절각 — 같은 기둥·지지 정기 한정(2026-08-01 확정)."""

    CUT_OFF_PRESENT = "cut_off_present"
    CUT_OFF_ABSENT = "cut_off_absent"
    #: 천간합 등으로 실제 천간 오행과 평가 오행이 달라진 경우. 자동 판단에 쓰지 않는다.
    CUT_OFF_REQUIRES_REVIEW = "cut_off_requires_review"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class StageApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RootInstance:
    """뿌리 1건. **자리마다 별개**다 — 같은 글자가 두 자리에 있으면 두 건이다."""

    node_id: str
    layer: str
    branch: str
    hidden_stem: str
    #: main | middle | residual. evidence 로만 남기고 계수로 바꾸지 않는다.
    hidden_stem_type: str
    #: 이 뿌리 하나의 깊이. 집계 필드만 두면 "어느 자리의 어떤 지장간 때문에 MAIN_QI 인가"
    #: 를 설명할 수 없다.
    depth: RootDepth = RootDepth.UNKNOWN


@dataclass(frozen=True)
class RootProfile:
    status: RootStatus
    instances: tuple[RootInstance, ...] = ()
    #: 범위별 깊이. 원국과 운을 따로 보존한 뒤 합친다.
    natal_root_depth: RootDepth = RootDepth.NONE
    transit_root_depth: RootDepth = RootDepth.NONE
    strongest_root_depth: RootDepth = RootDepth.NONE
    has_main_qi_root: bool = False


@dataclass(frozen=True)
class SupportPath:
    """생조 경로 1건. 교란은 **그 자리의** 관계로만 판정한다."""

    source_node_id: str
    source_element: str
    target_node_id: str
    target_element: str
    relation: Literal["generates"]
    disruption_relation_ids: tuple[str, ...]
    status: SupportPathStatus


@dataclass(frozen=True)
class SupportProfile:
    status: SupportStatus
    paths: tuple[SupportPath, ...] = ()


@dataclass(frozen=True)
class ObstructionProfile:
    cut_off: CutOffStatus
    #: 절각 판정에 쓰인 (천간, 지지, 지지 정기).
    stem: str | None = None
    branch: str | None = None
    controlling_hidden_stem: str | None = None


@dataclass(frozen=True)
class StageModifier:
    """12운성 — 기준 천간은 **같은 기둥의 실제 천간**이다(대표 천간을 지어내지 않는다)."""

    applicability: StageApplicability
    stem: str | None = None
    branch: str | None = None
    stage: str | None = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileTarget:
    """평가 대상 한 자리. 지지 노드일 수도, 천간일 수도 있다."""

    node_id: str
    layer: str
    pillar_position: str
    component: str            # stem | branch
    character: str
    raw_element: str
    #: P1 상태 원장의 최종 값. 환원된 노드는 이미 원래 오행이 들어 있다.
    resolved_element: str | None


@dataclass(frozen=True)
class ElementOperabilityProfile:
    """신호 묶음. **등급도 점수도 역할도 없다.**"""

    node_id: str
    raw_element: str
    resolved_element: str | None
    root: RootProfile
    support: SupportProfile
    obstruction: ObstructionProfile
    stage: StageModifier
    evidence_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


def _element_of(character: str) -> str | None:
    """지지 → 오행. 지지의 정기 오행을 그 지지의 오행으로 본다."""
    try:
        return STEM_ELEMENT[main_hidden_stem(Branch(character))].value
    except (ValueError, KeyError):
        return None


def _root_instances(
    element: str, nodes: Sequence[RelationNode], exclude_node_id: str,
) -> tuple[RootInstance, ...]:
    """지장간에 **같은 오행**을 가진 자리 전부. 생하는 오행은 세지 않는다.

    평가 대상 자신은 제외한다 — 지지가 자기 자신의 뿌리라는 판정은 의미가 없고, 넣으면 모든
    지지가 항상 유근이 된다.
    """
    out: list[RootInstance] = []
    for node in sorted(nodes, key=lambda n: n.node_id):
        if node.component != "branch" or node.node_id == exclude_node_id:
            continue
        try:
            hidden = hidden_stems_for(Branch(node.character))
        except ValueError:
            continue
        for stem, kind, _budget in hidden:
            if STEM_ELEMENT[stem].value != element:
                continue
            kind_name = str(getattr(kind, "value", kind))
            out.append(RootInstance(
                node_id=node.node_id, layer=node.layer, branch=node.character,
                hidden_stem=stem.value, hidden_stem_type=kind_name,
                depth=_DEPTH_BY_HIDDEN_TYPE.get(kind_name, RootDepth.UNKNOWN),
            ))
    return tuple(out)


def _scope_depth(instances: tuple[RootInstance, ...], natal: bool) -> RootDepth:
    picked = [
        i.depth for i in instances if (i.layer == "natal") is natal
    ]
    return combine_root_depths(*picked) if picked else RootDepth.NONE


def _root_profile(instances: tuple[RootInstance, ...]) -> RootProfile:
    natal_depth = _scope_depth(instances, natal=True)
    transit_depth = _scope_depth(instances, natal=False)
    strongest = combine_root_depths(natal_depth, transit_depth)
    # 키워드를 dict 로 묶어 언팩하지 않는다 — 값 타입이 섞여 dict[str, object] 로 추론되고
    # 필드 타입 검사가 통째로 사라진다.
    has_main = (natal_depth is RootDepth.MAIN_QI
                or transit_depth is RootDepth.MAIN_QI)
    layers = {i.layer for i in instances}
    if not instances:
        status = RootStatus.ABSENT
    elif "natal" in layers and (layers - {"natal"}):
        status = RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT
    elif "natal" in layers:
        status = RootStatus.DIRECT_NATAL_ROOT
    else:
        status = RootStatus.DIRECT_TRANSIT_ROOT
    return RootProfile(
        status, instances, natal_root_depth=natal_depth,
        transit_root_depth=transit_depth, strongest_root_depth=strongest,
        has_main_qi_root=has_main,
    )


def _support_profile(
    element: str,
    target_node_id: str,
    nodes: Sequence[RelationNode],
    relations: Sequence[BranchRelationInstance],
) -> SupportProfile:
    """생조 경로. **그 자리의** 충만 그 경로를 흔든다.

    같은 글자가 다른 자리에 또 있어도 자동으로 함께 교란된 것으로 보지 않는다 — 자리 기반
    관계 인스턴스를 쓰는 이유가 이것이다.
    """
    source_element = next(
        (src for src, dst in GENERATES.items() if dst.value == element), None,
    )
    if source_element is None:
        return SupportProfile(SupportStatus.ABSENT)

    disruptions: dict[str, list[str]] = {}
    for rel in relations:
        if rel.kind not in _DISRUPTIVE_KINDS:
            continue
        for node_id in rel.member_node_ids:
            disruptions.setdefault(node_id, []).append(rel.relation_id)

    paths: list[SupportPath] = []
    for node in sorted(nodes, key=lambda n: n.node_id):
        if node.component != "branch" or node.node_id == target_node_id:
            continue
        if _element_of(node.character) != source_element.value:
            continue
        hits = tuple(sorted(disruptions.get(node.node_id, ())))
        paths.append(SupportPath(
            source_node_id=node.node_id, source_element=source_element.value,
            target_node_id=target_node_id, target_element=element,
            relation="generates", disruption_relation_ids=hits,
            status=SupportPathStatus.DISRUPTED if hits else SupportPathStatus.STABLE,
        ))

    if not paths:
        return SupportProfile(SupportStatus.ABSENT)
    disrupted = [p for p in paths if p.status is SupportPathStatus.DISRUPTED]
    if not disrupted:
        status = SupportStatus.INDIRECT_GENERATION_STABLE
    elif len(disrupted) == len(paths):
        status = SupportStatus.INDIRECT_GENERATION_DISRUPTED
    else:
        # 어느 쪽이 우세한지는 정하지 않는다 — P2-2 가 판단한다.
        status = SupportStatus.INDIRECT_GENERATION_PRESENT_MIXED
    return SupportProfile(status, tuple(paths))


def _obstruction_profile(
    target: ProfileTarget, pillar_branch: str | None,
) -> ObstructionProfile:
    """절각 — 같은 기둥 + 지지 정기 + 정기가 실제 천간을 극.

    운 천간↔원국 지지, 인접 기둥, 다른 운 층은 세지 않는다(2026-08-01 확정). 판정 단위가
    간지 한 쌍이므로 지지 노드에는 적용되지 않는다.
    """
    if target.component != "stem" or pillar_branch is None:
        return ObstructionProfile(CutOffStatus.NOT_APPLICABLE)
    try:
        stem_element = STEM_ELEMENT[Stem(target.character)].value
        hidden = main_hidden_stem(Branch(pillar_branch))
    except (ValueError, KeyError):
        return ObstructionProfile(CutOffStatus.UNKNOWN)
    if target.resolved_element is not None and target.resolved_element != stem_element:
        # 천간합 등으로 평가 오행이 실제 천간과 달라졌다 — 자동 판단에 쓰지 않는다.
        return ObstructionProfile(
            CutOffStatus.CUT_OFF_REQUIRES_REVIEW, target.character, pillar_branch,
            hidden.value,
        )
    hidden_element = STEM_ELEMENT[hidden].value
    controlled = CONTROLS[_as_element(hidden_element)]
    return ObstructionProfile(
        # 지지 정기의 오행이 천간 오행을 극하는가.
        CutOffStatus.CUT_OFF_PRESENT if controlled.value == stem_element
        else CutOffStatus.CUT_OFF_ABSENT,
        target.character, pillar_branch, hidden.value,
    )


def _as_element(value: str):
    """오행 한자 → Element. `CONTROLS` 조회용."""
    for element in CONTROLS:
        if element.value == value:
            return element
    raise KeyError(value)


def _stage_modifier(
    target: ProfileTarget, pillar_branch: str | None,
) -> StageModifier:
    """12운성 — 같은 기둥의 실제 천간 기준.

    대표 천간을 지어내지 않는다. 壬-未는 양, 癸-未는 묘로 정반대라 임의 선택이 판정을 가른다.
    """
    if target.component != "stem":
        return StageModifier(
            StageApplicability.NOT_APPLICABLE, reason_codes=("TARGET_IS_BRANCH",))
    if pillar_branch is None:
        return StageModifier(
            StageApplicability.NOT_APPLICABLE, reason_codes=("NO_SAME_PILLAR_BRANCH",))
    try:
        stage = twelve_unseong(Stem(target.character), Branch(pillar_branch))
    except (ValueError, KeyError):
        return StageModifier(StageApplicability.UNKNOWN)
    return StageModifier(
        StageApplicability.APPLICABLE, target.character, pillar_branch, stage,
    )


def extract_element_operability_profile(
    *,
    target: ProfileTarget,
    nodes: Sequence[RelationNode],
    branch_relations: Sequence[BranchRelationInstance] = (),
    pillar_branches: Mapping[tuple[str, str], str] | None = None,
    extra_reason_codes: Sequence[str] = (),
) -> ElementOperabilityProfile:
    """신호 프로필을 뽑는다. **판단하지 않는다.**

    Args:
        target: 평가 대상 자리. `resolved_element` 는 P1 상태 원장의 최종 값이다.
        nodes: 뿌리·생조 탐색 대상 자리 전체(원국 + 현재 운).
        branch_relations: P1-b0 위치 기반 관계 인스턴스. 생조원 교란 판정에 쓴다.
        pillar_branches: (층, 궁위) → 같은 기둥 지지. 절각·12운성에 쓴다.
        extra_reason_codes: 호출부가 덧붙일 사유(예: 환원 이력).

    Returns:
        신호 묶음. 등급·앵커·역할·활성도는 들어 있지 않다.
    """
    reasons = list(extra_reason_codes)
    element = target.resolved_element
    if element is None:
        # 정체성이 확정되지 않았다. 프로필을 억지로 계산하지 않는다.
        reasons.append("OPERABILITY_UNKNOWN_CONFLICTING_RESOLUTION")
        return ElementOperabilityProfile(
            node_id=target.node_id, raw_element=target.raw_element,
            resolved_element=None,
            root=RootProfile(
                RootStatus.UNKNOWN,
                natal_root_depth=RootDepth.UNKNOWN,
                transit_root_depth=RootDepth.UNKNOWN,
                strongest_root_depth=RootDepth.UNKNOWN,
            ),
            support=SupportProfile(SupportStatus.UNKNOWN),
            obstruction=ObstructionProfile(CutOffStatus.UNKNOWN),
            stage=StageModifier(StageApplicability.UNKNOWN),
            reason_codes=tuple(reasons),
        )

    reasons.append(
        "RESOLVED_ELEMENT_CONFIRMED" if element == target.raw_element
        else "RESOLVED_ELEMENT_TRANSFORMED"
    )
    pillar_branch = (pillar_branches or {}).get(
        (target.layer, target.pillar_position)
    )
    root = _root_profile(_root_instances(element, nodes, target.node_id))
    support = _support_profile(element, target.node_id, nodes, branch_relations)
    obstruction = _obstruction_profile(target, pillar_branch)
    stage = _stage_modifier(target, pillar_branch)

    if root.status is RootStatus.ABSENT:
        reasons.append("NATAL_ROOT_ABSENT")
    if support.status is SupportStatus.INDIRECT_GENERATION_DISRUPTED:
        reasons.append("INDIRECT_SUPPORT_DISRUPTED")
    elif support.status is not SupportStatus.ABSENT:
        reasons.append("INDIRECT_SUPPORT_PRESENT")
    if obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT:
        reasons.append("CUT_OFF_PRESENT")

    # evidence 는 **발생 1건**으로 유지한다. 같은 충이 여러 관찰을 낳아도 ID 는 하나다 —
    # 중복 기여 방지는 P2-2 등급 평가기가 한다.
    evidence = sorted({
        rid for path in support.paths for rid in path.disruption_relation_ids
    })
    return ElementOperabilityProfile(
        node_id=target.node_id, raw_element=target.raw_element,
        resolved_element=element, root=root, support=support,
        obstruction=obstruction, stage=stage,
        evidence_ids=tuple(evidence), reason_codes=tuple(dict.fromkeys(reasons)),
    )

"""오행 실현도 shadow 배선 (P2-4, 2026-08-01).

**평가 대상 범위와 증거 탐색 범위를 분리한다.**

    평가 대상   현재 요청에 활성화된 대운·세운의 천간과 지지 (최대 4개)
    증거 문맥   원국 8자 · 원국↔운 · 운↔운 관계 · 변환/환원 상태 전체

원국을 평가하지 않는다고 원국 신호를 무시하는 것이 아니다. 원국 亥의 지장간 壬水는 세운
癸水의 직접 뿌리 근거가 되고, 원국 卯와 대운 酉의 충은 그 酉가 제공하는 생조 경로의 교란
근거가 된다.

## terminal frame 기준

대운을 대운 프레임에서 따로 평가하지 않는다. **현재 요청의 최종 프레임에서 활성 운 노드
전체를 평가**한다. 그래야 세운이 대운의 생조원이나 변환 상태를 흔든 결과까지 대운 노드
평가에 반영된다.

    evaluation_scope   EFFECTIVE_AS_OF_TERMINAL_LAYER

대운 단독 기준선과 결합 후 변화량은 만들지 않는다 — 필요해지면 후속 진단 모드로 분리한다.

## 천간 노드에 대하여

P1 그래프는 **지지 노드만** 만든다(관계 계산이 지지 기반이라서다). 그래서 운 천간은 여기서
`ProfileTarget` 으로 합성하며, 천간 변환(천간합)은 P1 이 추적하지 않으므로
`resolved_element = raw_element` 다. 천간합으로 오행이 달라지는 경우는 P2-1 이
`CUT_OFF_REQUIRES_REVIEW` 로 남긴다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from saju_shared_types.constants import STEM_ELEMENT
from saju_shared_types.enums import Stem

from .branch_relation_collector import collect_branch_relation_instances
from .element_operability_grade import (
    OperabilityEvaluation,
    OperabilityStatus,
    evaluate_element_operability,
)
from .element_operability_profile import (
    ElementOperabilityProfile,
    ProfileTarget,
    extract_element_operability_profile,
)
from .relation_shadow_config import should_build_element_operability
from .relation_state_chain import RelationStateChain, RelationStateFrame
from .role_activation_projection import (
    PRODUCTION_ALLOWED_ROLE_BASES,
    CanonicalRole,
    CanonicalRoleBasis,
    RoleActivationResult,
    project_role_activation,
)

_logger = logging.getLogger(__name__)

#: 현재 지원하는 평가 대상 층. 월운·일운은 P2-4 범위 밖이다.
SUPPORTED_OPERABILITY_TARGET_LAYERS: frozenset[str] = frozenset({"daewoon", "sewoon"})

#: 대상 구성요소.
SUPPORTED_TARGET_COMPONENTS: frozenset[str] = frozenset({"stem", "branch"})

#: 최대 대상 수 — 대운 간지 2 + 세운 간지 2.
MAX_OPERABILITY_TARGETS = 4


class OperabilityShadowFailureKind(StrEnum):
    """shadow 실패 분류. `UNKNOWN` 관측값은 실패가 아니다."""

    RELATION_CHAIN_UNAVAILABLE = "relation_chain_unavailable"
    TARGET_SELECTION_FAILURE = "target_selection_failure"
    PROFILE_EXTRACTION_FAILURE = "profile_extraction_failure"
    EVALUATION_FAILURE = "evaluation_failure"
    ROLE_PROJECTION_FAILURE = "role_projection_failure"
    ROLE_BASIS_NOT_ALLOWED = "role_basis_not_allowed"
    UNEXPECTED_ERROR = "unexpected_error"


class OperabilityShadowError(Exception):
    """실현도 shadow 실패. 호출부가 잡아 기록하고 요청은 정상 완료시킨다."""

    def __init__(self, kind: OperabilityShadowFailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class OperabilityShadowMetrics:
    """저카디널리티 집계. 간지·node ID·기간키를 담지 않는다."""

    target_count: int = 0
    profile_count: int = 0
    evaluation_count: int = 0
    projection_count: int = 0
    build_duration_ms: float = 0.0
    status_counts: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class OperabilityShadowTargetResult:
    node_id: str
    layer: str
    component: str
    raw_element: str
    resolved_element: str | None
    profile: ElementOperabilityProfile
    evaluation: OperabilityEvaluation
    role_projection: RoleActivationResult


@dataclass(frozen=True)
class LuckElementOperabilityShadowBundle:
    """내부 shadow 산출물. 응답·LLM 입력·점수 어디에도 넣지 않는다."""

    as_of_layer: str
    terminal_snapshot_id: str
    relation_graph_fingerprint: str
    role_basis: CanonicalRoleBasis
    targets: tuple[OperabilityShadowTargetResult, ...]
    build_metrics: OperabilityShadowMetrics


def select_operability_targets(
    *,
    terminal_frame: RelationStateFrame,
    luck_stems: Mapping[str, str],
) -> tuple[ProfileTarget, ...]:
    """대운·세운의 천간·지지를 대상으로 고른다. **원국은 제외한다.**

    Args:
        terminal_frame: 현재 요청의 최종 frame.
        luck_stems: 층 → 천간 한자(예: {'daewoon': '己', 'sewoon': '癸'}).

    Returns:
        평가 대상. 같은 오행이라도 자리마다 별개 대상이다 — 앉은 지지·뿌리·생조·절각·
        12운성·변환 이력이 모두 다를 수 있어 병합하면 그 차이가 사라진다.
    """
    states = {s.node_id: s for s in terminal_frame.snapshot.element_states}
    out: list[ProfileTarget] = []

    for node in sorted(terminal_frame.graph.nodes, key=lambda n: n.node_id):
        if node.layer not in SUPPORTED_OPERABILITY_TARGET_LAYERS:
            continue
        if node.component not in SUPPORTED_TARGET_COMPONENTS:
            continue
        state = states.get(node.node_id)
        out.append(ProfileTarget(
            node_id=node.node_id, layer=node.layer,
            pillar_position=node.pillar_position, component=node.component,
            character=node.character, raw_element=node.original_element,
            # terminal final snapshot 의 값을 그대로 쓴다 — 변환·환원을 다시 계산하지 않는다.
            resolved_element=state.resolved_element if state else None,
        ))

    for layer, stem_char in sorted(luck_stems.items()):
        if layer not in SUPPORTED_OPERABILITY_TARGET_LAYERS or not stem_char:
            continue
        try:
            element = STEM_ELEMENT[Stem(stem_char)].value
        except (ValueError, KeyError) as exc:
            raise OperabilityShadowError(
                OperabilityShadowFailureKind.TARGET_SELECTION_FAILURE,
                f"알 수 없는 천간: {stem_char!r}",
            ) from exc
        out.append(ProfileTarget(
            node_id=f"{layer}.stem:{stem_char}", layer=layer, pillar_position="",
            component="stem", character=stem_char, raw_element=element,
            # P1 은 천간 변환을 추적하지 않는다. 달라지는 경우는 P2-1 이 REQUIRES_REVIEW 로 남긴다.
            resolved_element=element,
        ))
    return tuple(sorted(out, key=lambda t: t.node_id))


def build_operability_shadow_bundle(
    *,
    chain: RelationStateChain,
    luck_stems: Mapping[str, str],
    roles_by_element: Mapping[str, CanonicalRole],
    role_basis: CanonicalRoleBasis = CanonicalRoleBasis.ENGINE_NATIVE,
    pillar_branches: Mapping[tuple[str, str], str] | None = None,
) -> LuckElementOperabilityShadowBundle:
    """terminal frame 문맥에서 운 간지 실현도를 평가한다. **순수 함수다.**

    Args:
        chain: P1-b2 상태 체인.
        luck_stems: 층 → 운 천간.
        roles_by_element: 오행 → 용희기구한. **최종 resolved element 로 조회한다.**
        role_basis: 역할표 출처. production 경로는 ENGINE_NATIVE 만 허용한다.
        pillar_branches: (층, 궁위) → 같은 기둥 지지. 절각·12운성에 쓴다.

    Returns:
        내부 shadow 묶음.

    Raises:
        OperabilityShadowError: 단계별 실패. `UNKNOWN` 관측값은 실패가 아니다.
    """
    started = time.perf_counter()
    if not chain.frames:
        raise OperabilityShadowError(
            OperabilityShadowFailureKind.RELATION_CHAIN_UNAVAILABLE, "frame 없음")
    terminal = chain.terminal_frame
    # 생조원 교란 근거. 이걸 빼면 SupportProfile 이 DISRUPTED·PRESENT_MIXED 로 갈 수
    # 없다(첫 분포 측정에서 두 값이 0건으로 나와 드러났다).
    branch_relations = collect_branch_relation_instances(nodes=terminal.graph.nodes)
    targets = select_operability_targets(
        terminal_frame=terminal, luck_stems=luck_stems)

    results: list[OperabilityShadowTargetResult] = []
    for target in targets:
        try:
            profile = extract_element_operability_profile(
                target=target, nodes=terminal.graph.nodes,
                branch_relations=branch_relations,
                pillar_branches=pillar_branches or {},
            )
        except Exception as exc:  # noqa: BLE001 - 분류해서 다시 던진다
            raise OperabilityShadowError(
                OperabilityShadowFailureKind.PROFILE_EXTRACTION_FAILURE, repr(exc),
            ) from exc
        try:
            evaluation = evaluate_element_operability(profile)
        except Exception as exc:  # noqa: BLE001
            raise OperabilityShadowError(
                OperabilityShadowFailureKind.EVALUATION_FAILURE, repr(exc)) from exc
        # 역할은 raw 가 아니라 **최종 resolved element** 로 조회한다.
        role = roles_by_element.get(target.resolved_element or "", CanonicalRole.HAN)
        try:
            projection = project_role_activation(
                node_id=target.node_id, canonical_role=role, role_basis=role_basis,
                evaluation=evaluation,
            )
        except Exception as exc:  # noqa: BLE001
            raise OperabilityShadowError(
                OperabilityShadowFailureKind.ROLE_PROJECTION_FAILURE, repr(exc),
            ) from exc
        results.append(OperabilityShadowTargetResult(
            node_id=target.node_id, layer=target.layer, component=target.component,
            raw_element=target.raw_element, resolved_element=target.resolved_element,
            profile=profile, evaluation=evaluation, role_projection=projection,
        ))

    counts: dict[str, int] = {}
    for result in results:
        key = result.evaluation.status.value
        counts[key] = counts.get(key, 0) + 1
    return LuckElementOperabilityShadowBundle(
        as_of_layer=terminal.layer,
        terminal_snapshot_id=terminal.snapshot.snapshot_id,
        relation_graph_fingerprint=terminal.snapshot.graph_fingerprint,
        role_basis=role_basis, targets=tuple(results),
        build_metrics=OperabilityShadowMetrics(
            target_count=len(results), profile_count=len(results),
            evaluation_count=len(results), projection_count=len(results),
            build_duration_ms=(time.perf_counter() - started) * 1000.0,
            status_counts=tuple(sorted(counts.items())),
        ),
    )


def element_operability_shadow(
    *,
    chain: RelationStateChain | None,
    luck_stems: Mapping[str, str],
    roles_by_element: Mapping[str, CanonicalRole],
    pillar_branches: Mapping[tuple[str, str], str] | None = None,
    role_basis: CanonicalRoleBasis = CanonicalRoleBasis.ENGINE_NATIVE,
) -> LuckElementOperabilityShadowBundle | None:
    """마스터 게이트 wrapper — 플래그가 꺼져 있으면 **아무것도 하지 않고** None.

    production 은 fail-open, shadow 의미론은 fail-closed 다. 실패하면 부분 결과를 정상처럼
    쓰지 않고 묶음 전체를 버린다.
    """
    if not should_build_element_operability():
        return None
    if role_basis not in PRODUCTION_ALLOWED_ROLE_BASES:
        # 출처 역할표는 테스트·감사 하네스 전용이다. 생산 경로로 들어오면 거부한다.
        _logger.info(
            "실현도 shadow 거부 — error_kind=%s",
            OperabilityShadowFailureKind.ROLE_BASIS_NOT_ALLOWED.value)
        return None
    if chain is None:
        return None
    try:
        bundle = build_operability_shadow_bundle(
            chain=chain, luck_stems=luck_stems, roles_by_element=roles_by_element,
            role_basis=role_basis, pillar_branches=pillar_branches,
        )
    except OperabilityShadowError as exc:
        _logger.info("실현도 shadow 실패 — error_kind=%s status=failure", exc.kind.value)
        return None
    except Exception as exc:  # noqa: BLE001 - shadow 가 요청을 실패시키지 않는다
        _logger.info(
            "실현도 shadow 실패 — error_kind=%s",
            OperabilityShadowFailureKind.UNEXPECTED_ERROR.value, exc_info=exc)
        return None
    _logger.debug(
        "실현도 shadow — status=success targets=%d duration_ms=%.1f",
        bundle.build_metrics.target_count, bundle.build_metrics.build_duration_ms)
    return bundle


def status_distribution(
    bundle: LuckElementOperabilityShadowBundle,
) -> dict[str, int]:
    """등급 분포. `UNKNOWN` 도 유효한 관측값이므로 함께 센다."""
    out = {s.value: 0 for s in OperabilityStatus}
    for key, count in bundle.build_metrics.status_counts:
        out[key] = count
    return out

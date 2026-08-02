"""용신 역할 실현 경계 (CAL-ROLE-BORDERLINE-01c1-a, 2026-08-03).

**inert 추출이다.** 명리 규칙을 추가하지 않고, 역할표 재계산 방식·모델 선택을 바꾸지
않는다. `build_yongsin` 안에 흩어져 있던 "용신 오행 하나가 정해진 뒤 5역할이 실제로
어떻게 확정되는가" 를 입력·출력이 명시된 순수 경계로 옮긴다.

01c0 이 남긴 문제가 이 경계를 요구했다. canonical 역할표의 출처를 소스 읽기로만
추적하다 두 번 뒤집혔고, runner-up 을 같은 경로로 재생할 수 있는지조차 확인할 수
없었다. 경로가 함수 안에 잠겨 있으면 반사실을 실행할 방법이 없다.

    실현 출처는 네 갈래다 — **뭉뚱그리지 않는다**

    COMPLETE_MODEL_ROLE_MAP                완비 선택 모델의 자체 역할표를 승격
    STATIC_FALLBACK_ROLE_MAP               정적 생극 순환(부분맵 모델)
    BRIDGE_SPECIAL_ROLE_MAP                통관 특수분기
    SUPPORT_DAY_MASTER_SPECIAL_ROLE_MAP    무비겁 부일간 특수분기

이 모듈은 `candidates` 를 import 하지 않는다(순환 방지). 두 분류기는 호출부가
주입하며, 그래서 의존성이 시그니처에 드러난다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.enums import Branch, Element
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.yongsin import YongsinCandidateModel

#: 2계층 역할(YONGSIN_OPERATIONAL_ROLE_SPEC) — 역할 키 순서.
_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")

#: 무비겁 부일간 특수분기의 강약 밴드 조건.
_WEAK = {"극신약", "태신약", "신약", "중화신약"}

_BRIDGE_MODEL = "bridge_tonggwan"
_SUPPORT_MODEL = "support_day_master"


def _e(el: Element) -> str:
    return str(el)


class RoleRealizationOrigin(StrEnum):
    """최종 역할표가 **실제로 어느 경로에서** 나왔는가."""

    COMPLETE_MODEL_ROLE_MAP = "complete_model_role_map"
    STATIC_FALLBACK_ROLE_MAP = "static_fallback_role_map"
    BRIDGE_SPECIAL_ROLE_MAP = "bridge_special_role_map"
    SUPPORT_DAY_MASTER_SPECIAL_ROLE_MAP = "support_day_master_special_role_map"


@dataclass(frozen=True)
class RealizedRoleMap:
    """5역할 전체. 부분 저장하지 않는다.

    `saju_engines.role_candidates.CanonicalRoleMap` 과 모양이 같지만 **그 타입을 쓰지
    않는다** — 그 계약(`eeaed83`)은 SUPERSEDED 이고 production 배선이 취소돼 있다.
    """

    yongsin: str | None
    heesin: str | None
    gisin: str | None
    gusin: str | None
    hansin: str | None

    @classmethod
    def from_mapping(cls, role_map: Mapping[str, str | None]) -> RealizedRoleMap:
        return cls(**{k: role_map.get(k) for k in _ROLE_KEYS})

    def as_dict(self) -> dict[str, str | None]:
        """호출부가 쓸 **새 dict**. 내부 상태를 넘겨주지 않는다."""
        return {k: getattr(self, k) for k in _ROLE_KEYS}


@dataclass(frozen=True)
class RoleRealizationChartContext:
    """특수분기가 소비하는 원국 맥락. 실현 판정에 필요한 것만 담는다."""

    group_elements: Mapping[str, Element]
    group_strengths: Mapping[str, float]
    strength_band: str
    pillars: FourPillarsResult
    force: ForceAnalysis
    month_branch: Branch
    bridge_required_detail: str | None


@dataclass(frozen=True)
class RoleRealizationResult:
    """실현 판정의 전체 근거. 어느 갈래로 갔는지를 사후에 재구성할 수 있어야 한다."""

    selected_yongsin_element: str | None
    top_model_type: str | None
    selected_model_type: str | None
    selected_model_confidence: Decimal | None
    special_role_kind: str | None
    model_complete: bool
    model_map_promoted: bool
    base_role_map: RealizedRoleMap
    final_role_map: RealizedRoleMap
    realization_origin: RoleRealizationOrigin
    reason_codes: tuple[str, ...]
    #: 특수분기가 만든 경고. 순수성을 지키려고 호출부의 리스트를 직접 건드리지 않는다.
    warnings: tuple[str, ...]
    #: 후속 operational 계층이 소비하는 선택 모델 **참조**. 여기서 변형하지 않는다.
    selected_model: YongsinCandidateModel | None


class StaticRoleClassifier(Protocol):
    """용신 오행 → 정적 생극 순환 역할표."""

    def __call__(self, yongsin_el: str | None) -> dict[str, str | None]: ...


class BridgeRoleClassifier(Protocol):
    """통관 역할표 + 동점 타이브레이크 사유."""

    def __call__(
        self,
        g: dict[str, Element],
        groups: dict[str, float],
        detail: str | None,
        useful: dict[str, tuple[float, str, str]],
        yongsin_el: str,
        pillars: FourPillarsResult,
        force: ForceAnalysis,
        month_branch: Branch,
    ) -> tuple[dict[str, str | None], str | None]: ...


def resolve_realized_roles(
    *,
    chart_context: RoleRealizationChartContext,
    selected_yongsin_element: str | None,
    useful_scores: Mapping[str, tuple[float, str, str]],
    model_outputs: Sequence[YongsinCandidateModel],
    top_model_type: str | None,
    static_classifier: StaticRoleClassifier,
    bridge_classifier: BridgeRoleClassifier,
) -> RoleRealizationResult:
    """용신 오행이 정해진 뒤의 5역할 확정을 그대로 재현한다.

    판정 순서는 기존 코드와 같다. **특수분기가 승격보다 앞선다** — 통관·무비겁 맵은
    이미 맥락 교정값이라 모델맵으로 덮으면 안 된다.

        ① 정적 생극 순환으로 base 를 만든다
        ② 통관·무비겁이면 그 맵으로 교체하고 special 로 표시한다
        ③ 선택 모델(동일 model_type·yongsin 중 최고 confidence)을 찾는다
        ④ special 이 아니고 5역할 완비면 그 모델의 자체 역할표로 승격한다

    Args:
        chart_context: 특수분기가 쓰는 원국 맥락.
        selected_yongsin_element: 이미 확정된 용신 오행(없으면 None).
        useful_scores: 통관 희신 폴백이 참조하는 후보 점수표.
        model_outputs: 후보 모델 전체.
        top_model_type: 최상위 후보를 만든 모델 종류.
        static_classifier: 정적 생극 분류기(호출부 주입 — 순환 import 방지).
        bridge_classifier: 통관 분류기(호출부 주입).

    Returns:
        실현 결과. 역할표는 frozen 이고 `as_dict()` 는 매번 새 dict 를 만든다.
    """
    base_map = static_classifier(selected_yongsin_element)
    roles: dict[str, str | None] = dict(base_map)
    reason_codes: list[str] = []
    warnings: list[str] = []
    special_kind: str | None = None

    g = dict(chart_context.group_elements)
    groups = dict(chart_context.group_strengths)

    if top_model_type == _BRIDGE_MODEL and selected_yongsin_element:
        roles, tiebreak_reason = bridge_classifier(
            g, groups, chart_context.bridge_required_detail, dict(useful_scores),
            selected_yongsin_element, chart_context.pillars, chart_context.force,
            chart_context.month_branch,
        )
        if tiebreak_reason:
            warnings.append(tiebreak_reason)
            reason_codes.append("bridge_tiebreak_applied")
        special_kind = _BRIDGE_MODEL
        reason_codes.append("special_branch:bridge_tonggwan")
    elif (
        top_model_type == _SUPPORT_MODEL
        and chart_context.strength_band in _WEAK
        and groups.get("peer", 0.0) <= 0.0
        and selected_yongsin_element == _e(g["peer"])
    ):
        roles = {
            "yongsin": _e(g["peer"]),
            "heesin": _e(g["resource"]),
            "gisin": _e(g["output"]),
            "gusin": _e(g["wealth"]),
            "hansin": _e(g["officer"]),
        }
        special_kind = _SUPPORT_MODEL
        reason_codes.append("special_branch:support_day_master")

    selected_model = next(
        (
            m
            for m in sorted(model_outputs, key=lambda x: -x.confidence)
            if m.model_type == top_model_type and m.yongsin == selected_yongsin_element
        ),
        None,
    )
    model_complete = selected_model is not None and all(
        getattr(selected_model, k) for k in _ROLE_KEYS
    )
    model_map_promoted = special_kind is None and model_complete
    if model_map_promoted and selected_model is not None:
        roles = {k: getattr(selected_model, k) for k in _ROLE_KEYS}
        reason_codes.append("model_map_promoted")
    elif special_kind is None:
        reason_codes.append(
            "static_fallback:model_incomplete" if selected_model is not None
            else "static_fallback:no_selected_model"
        )

    if special_kind == _BRIDGE_MODEL:
        origin = RoleRealizationOrigin.BRIDGE_SPECIAL_ROLE_MAP
    elif special_kind == _SUPPORT_MODEL:
        origin = RoleRealizationOrigin.SUPPORT_DAY_MASTER_SPECIAL_ROLE_MAP
    elif model_map_promoted:
        origin = RoleRealizationOrigin.COMPLETE_MODEL_ROLE_MAP
    else:
        origin = RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP

    confidence = (
        Decimal(str(selected_model.confidence)) if selected_model is not None else None
    )
    return RoleRealizationResult(
        selected_yongsin_element=selected_yongsin_element,
        top_model_type=top_model_type,
        selected_model_type=selected_model.model_type if selected_model else None,
        selected_model_confidence=confidence,
        special_role_kind=special_kind,
        model_complete=model_complete,
        model_map_promoted=model_map_promoted,
        base_role_map=RealizedRoleMap.from_mapping(base_map),
        final_role_map=RealizedRoleMap.from_mapping(roles),
        realization_origin=origin,
        reason_codes=tuple(reason_codes),
        warnings=tuple(warnings),
        selected_model=selected_model,
    )

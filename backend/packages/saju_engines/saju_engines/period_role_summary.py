"""연·월·일 역할 요약 빌더 + 슬롯 상태 계산기 (P2 — 2026-07-27 데굴님 확정).

대상 층위(target)는 **요청 범위**가 정한다. 사전계산에 일진이 함께 있더라도 월운
질문의 target은 월운이다(활성 스택의 마지막 층위를 자동으로 target 삼지 않는다).
"""

from __future__ import annotations

from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.luck_hierarchy import LuckHierarchy, ParticipantLayer
from saju_shared_types.period_role_summary import (
    ROLE_DIRECTION,
    BackgroundState,
    HierarchySummary,
    PeriodRoleSummary,
    PillarRoleState,
    PillarState,
    SlotStatus,
    SlotStatusResult,
    SlotStatusSource,
)

from .period_v2_config import PILLAR_ROLE_WEIGHT

#: 부동소수점 오차 처리용. 체감 임계값을 도입하면 새 규칙이 되므로 이 수준만 쓴다.
FLOAT_EPSILON = 1e-9

#: 요청 레벨 → 대상 층위. 활성 스택의 마지막이 아니라 요청 범위가 정한다.
_LEVEL_TO_TARGET: dict[str, ParticipantLayer] = {
    "year": ParticipantLayer.ANNUAL,
    "month": ParticipantLayer.MONTHLY,
    "day": ParticipantLayer.DAILY,
}
#: 상하 관계 — 앞쪽이 더 상위(장기 배경).
_LAYER_ORDER = (
    ParticipantLayer.DAEWOON,
    ParticipantLayer.ANNUAL,
    ParticipantLayer.MONTHLY,
    ParticipantLayer.DAILY,
)


def _state_of(role: str) -> PillarState:
    """역할 라벨 → 방향 상태. 미상은 NEUTRAL로 축약하지 않는다."""
    direction = ROLE_DIRECTION.get(role)
    if direction is None:
        return PillarState.UNKNOWN
    if direction > 0:
        return PillarState.FAVORABLE
    if direction < 0:
        return PillarState.ADVERSE
    return PillarState.NEUTRAL


def _combine(stem: PillarState, branch: PillarState) -> PillarState:
    """천간·지지 상태 → 운주 상태.

    방향이 반대면 net 부호와 무관하게 MIXED다(乙未는 sort_net이 양수여도 MIXED).
    """
    if PillarState.UNKNOWN in (stem, branch):
        return PillarState.UNKNOWN
    pair = {stem, branch}
    if PillarState.FAVORABLE in pair and PillarState.ADVERSE in pair:
        return PillarState.MIXED
    if PillarState.FAVORABLE in pair:
        return PillarState.FAVORABLE
    if PillarState.ADVERSE in pair:
        return PillarState.ADVERSE
    return PillarState.NEUTRAL


def build_pillar_role_state(
    layer: ParticipantLayer, ganji: str, favorability: dict[str, str]
) -> PillarRoleState:
    """간지 1개의 역할 상태.

    Args:
        layer: 층위.
        ganji: 간지 2자.
        favorability: 오행(한자) → 용희기구한 역할.

    Returns:
        천간·지지 역할과 합성 상태를 담은 PillarRoleState.
    """
    stem_role = favorability.get(str(STEM_ELEMENT[Stem(ganji[0])]), "")
    branch_role = favorability.get(str(BRANCH_ELEMENT[Branch(ganji[1])]), "")
    stem_state = _state_of(stem_role)
    branch_state = _state_of(branch_role)
    # sort_net은 정렬·진단 전용. 상태 결정에 절대 쓰지 않는다.
    sort_net = round(
        ROLE_DIRECTION.get(stem_role, 0) * PILLAR_ROLE_WEIGHT["stem"]
        + ROLE_DIRECTION.get(branch_role, 0) * PILLAR_ROLE_WEIGHT["branch"],
        4,
    )
    return PillarRoleState(
        layer=layer, ganji=ganji,
        stem_role=stem_role, branch_role=branch_role,
        stem_state=stem_state, branch_state=branch_state,
        state=_combine(stem_state, branch_state),
        sort_net=sort_net,
        direction_available=PillarState.UNKNOWN not in (stem_state, branch_state),
    )


def _background_state(rows: list[PillarRoleState]) -> BackgroundState:
    """배경 층위들의 방향 증거를 합친다 — 숫자 평균이 아니라 존재 증거로.

    중립은 방향성 증거를 상쇄하지 않는다(NEUTRAL + FAVORABLE = SUPPORT).
    """
    usable = [r for r in rows if r.direction_available]
    if not rows:
        return BackgroundState.NONE
    if not usable:
        return BackgroundState.UNKNOWN
    states = {r.state for r in usable}
    if PillarState.MIXED in states:
        return BackgroundState.MIXED
    if PillarState.FAVORABLE in states and PillarState.ADVERSE in states:
        return BackgroundState.MIXED
    if PillarState.FAVORABLE in states:
        return BackgroundState.SUPPORT
    if PillarState.ADVERSE in states:
        return BackgroundState.PRESSURE
    return BackgroundState.NEUTRAL


def _summary(background: BackgroundState, target: PillarState) -> HierarchySummary:
    """배경 × 대상 → 종합 유형. MIXED를 sort 값으로 재분류하지 않는다."""
    if background is BackgroundState.MIXED or target is PillarState.MIXED:
        return HierarchySummary.MIXED_ACROSS_LAYERS
    if background is BackgroundState.SUPPORT:
        if target is PillarState.FAVORABLE:
            return HierarchySummary.CONSISTENT_SUPPORT
        if target is PillarState.ADVERSE:
            return HierarchySummary.BACKGROUND_SUPPORT_TARGET_FRICTION
    if background is BackgroundState.PRESSURE:
        if target is PillarState.FAVORABLE:
            return HierarchySummary.BACKGROUND_PRESSURE_TARGET_RELIEF
        if target is PillarState.ADVERSE:
            return HierarchySummary.CONSISTENT_PRESSURE
    return HierarchySummary.NO_CLEAR_DIRECTION


def build_period_role_summary(
    hierarchy: LuckHierarchy, favorability: dict[str, str]
) -> PeriodRoleSummary:
    """계층형 grounding + 용희기구한 → 연·월·일 역할 요약.

    Args:
        hierarchy: P1이 만든 계층 SSOT(활성 층위 보유).
        favorability: 오행 → 역할 맵.

    Returns:
        background/target 상태를 각각 보존한 PeriodRoleSummary.
    """
    target_layer = _LEVEL_TO_TARGET.get(hierarchy.requested_level)
    rows = [
        build_pillar_role_state(p.layer, p.ganji, favorability)
        for p in hierarchy.active_layers
        if len(p.ganji) >= 2
    ]
    target_row = next((r for r in rows if r.layer is target_layer), None)
    # 배경 = 대상보다 **상위** 층위만. 하위(예: 월운 질문의 일진)는 배경이 아니다.
    if target_layer is None:
        background = []
    else:
        cut = _LAYER_ORDER.index(target_layer)
        background = [
            r for r in rows
            if r.layer in _LAYER_ORDER and _LAYER_ORDER.index(r.layer) < cut
        ]
    bg_state = _background_state(background)
    tg_state = target_row.state if target_row else PillarState.UNKNOWN
    return PeriodRoleSummary(
        requested_level=hierarchy.requested_level,
        target_layer=target_layer,
        target=target_row,
        background=background,
        background_state=bg_state,
        target_state=tg_state,
        hierarchy_summary=_summary(bg_state, tg_state),
    )


def derive_slot_status(
    *,
    positive_total: float,
    negative_total: float,
    neutral_signal_count: int,
    volatility_signal_count: int,
    source: SlotStatusSource,
    volatility_total: float = 0.0,
    signed_signal_count: int = 0,
    mixed_unallocated_signal_count: int = 0,
    display_score: int = 0,
) -> SlotStatusResult:
    """슬롯의 의미 상태를 판정한다(화면 clamp와 분리).

    체감 임계값은 도입하지 않는다 — 부동소수점 오차만 흡수한다. 임의 임계값을 넣으면
    docs에 없는 새 규칙이 된다(절대원칙 10).

    Args:
        positive_total: 유리 신호 합.
        negative_total: 불리 신호 합(양수 크기).
        neutral_signal_count: 방향이 중립인 신호 수.
        volatility_signal_count: 길흉 미판정(충·형·해) 신호 수.
        source: 원재료 출처. LEGACY_V1이면 사용자 서술 불가.
        volatility_total: 변동성 합.
        signed_signal_count: 부호가 있는 신호 수.
        display_score: 화면 점수(0~100).

    Returns:
        의미 상태와 표시 정보를 함께 담은 SlotStatusResult.
    """
    net = positive_total - negative_total
    if positive_total <= FLOAT_EPSILON and negative_total <= FLOAT_EPSILON:
        if mixed_unallocated_signal_count > 0:
            # 양방향 효과는 있으나 크기를 배분하지 못한 상태 — 신호 없음이 아니다.
            status = SlotStatus.DIRECTION_UNRESOLVED
        elif volatility_signal_count > 0:
            status = SlotStatus.VOLATILITY_ONLY
        elif neutral_signal_count > 0:
            status = SlotStatus.NEUTRAL
        else:
            status = SlotStatus.NO_SIGNAL
    elif negative_total <= FLOAT_EPSILON:
        status = SlotStatus.FAVORABLE_DOMINANT
    elif positive_total <= FLOAT_EPSILON:
        status = SlotStatus.ADVERSE_DOMINANT
    elif abs(net) <= FLOAT_EPSILON:
        status = SlotStatus.MIXED_BALANCED
    elif net > 0:
        status = SlotStatus.FAVORABLE_DOMINANT
    else:
        status = SlotStatus.ADVERSE_DOMINANT

    return SlotStatusResult(
        status=status, source=source,
        positive_total=positive_total, negative_total=negative_total,
        net_raw=round(net, 4),
        signed_signal_count=signed_signal_count,
        neutral_signal_count=neutral_signal_count,
        volatility_signal_count=volatility_signal_count,
        volatility_total=volatility_total,
        mixed_unallocated_signal_count=mixed_unallocated_signal_count,
        display_score=display_score,
        display_clamped=display_score == 0 and net < -FLOAT_EPSILON,
    )

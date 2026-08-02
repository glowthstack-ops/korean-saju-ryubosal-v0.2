"""오행 실현도 등급 평가 (P2-2, 2026-08-01).

**등급이 SSOT이고 0~1 앵커는 보조값이다.** 자유로운 연속 점수를 먼저 계산한 뒤 등급으로
자르지 않는다. 감산 누적도 쓰지 않는다.

    쓰지 않는다   1.0 − 무근 0.2 − 절각 0.3 − 묘지 0.15 = 0.35
    쓴다          복합 규칙 하나 선택 → WEAKENED → anchor 0.35

감산 누적을 피하는 이유는 신호들이 독립 사건이 아니기 때문이다. 하나의 卯酉冲이 생조원을
흔들고, 합 완성을 막고, 그 결과 절각 노출을 남긴다 — 각각 깎으면 같은 원인을 세 번 센다.
`matched_rule_id` 로 **최종 규칙 하나**를 고정해 구조적으로 차단한다.

역할(용희기구한)을 모른다. 이 계층은 `ElementOperabilityProfile` 만 읽는다.

## 원국 뿌리와 운 뿌리

`ABSENT` 만 무근이다. `DIRECT_TRANSIT_ROOT` 는 **유근 분기로 들어간다** — 지금 이 시기에는
실제로 기반이 있다는 사실이 먼저다.

다만 그 기반은 해당 운에 종속된 일시적인 것이라 `FULLY_OPERABLE` 자격을 주지 않고
`OPERABLE` 을 상한으로 둔다. 일괄 한 단계 감점은 하지 않는다 — `root_source=transit` 이라는
정보가 이미 있는데 결과까지 깎으면 시간적 한계를 두 번 반영하게 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .element_operability_profile import (
    CutOffStatus,
    ElementOperabilityProfile,
    RootDepth,
    RootStatus,
    SupportStatus,
)


class OperabilityStatus(StrEnum):
    """실현도 등급. **이것이 SSOT다.**

    `NULLIFIED`("완전히 작동하지 않는다")는 첫 버전에 넣지 않는다 — 강한 판정이라 fixture가
    쌓인 뒤 추가해도 늦지 않다.
    """

    FULLY_OPERABLE = "fully_operable"
    OPERABLE = "operable"
    PARTIALLY_OPERABLE = "partially_operable"
    WEAKENED = "weakened"
    SUPPRESSED = "suppressed"
    UNKNOWN = "unknown"


#: 보조 앵커. shadow 분포 측정·정렬 보조·변화량 감사·캘리브레이션 기준선에만 쓴다.
#: **사용자에게 "35%" 처럼 노출하지 않는다** — 실측 보정되지 않은 값을 확률처럼 보이게 한다.
OPERABILITY_ANCHOR: dict[OperabilityStatus, float | None] = {
    OperabilityStatus.FULLY_OPERABLE: 0.90,
    OperabilityStatus.OPERABLE: 0.75,
    OperabilityStatus.PARTIALLY_OPERABLE: 0.55,
    OperabilityStatus.WEAKENED: 0.35,
    OperabilityStatus.SUPPRESSED: 0.15,
    OperabilityStatus.UNKNOWN: None,
}

#: 약한 12운성. **명시적으로 확인된 것만 넣는다**(2026-08-01 지시: "묘·절 등").
#: 병·사·쇠·태는 경계이고 확인되지 않아 제외한다 — 넣으면 하향이 넓어지는데, 좁게 두면
#: 등급이 한 단계 덜 내려갈 뿐이라 보수적인 쪽이다.
WEAK_TWELVE_STAGES: frozenset[str] = frozenset({"묘", "절"})

#: 생조가 신뢰 가능하지 않은 상태 — SUPPRESSED 성립 조건에 쓴다.
_UNRELIABLE_SUPPORT = frozenset({
    SupportStatus.INDIRECT_GENERATION_DISRUPTED, SupportStatus.ABSENT,
})


@dataclass(frozen=True)
class OperabilityEvaluation:
    """등급 판정 1건. 규칙 하나만 선택된다."""

    status: OperabilityStatus
    anchor: float | None
    matched_rule_id: str
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def _is_weak_stage(profile: ElementOperabilityProfile) -> bool:
    """약한 12운성인가. **단독으로는 등급을 바꾸지 않는다** — 절각과 함께일 때만 쓴다."""
    return bool(profile.stage.stage and profile.stage.stage in WEAK_TWELVE_STAGES)


def _match_rule(profile: ElementOperabilityProfile) -> tuple[str, OperabilityStatus]:
    """복합 규칙표에서 **하나**를 고른다.

    12운성 하향을 사후 보정으로 두지 않고 규칙에 직접 넣는다. 사후에 한 단계 깎으면
    `matched_rule_id` 가 최종 결과를 설명하지 못하고, 감산 누적 방식으로 되돌아간다.
    """
    if profile.resolved_element is None:
        return "R00_UNRESOLVED_ELEMENT", OperabilityStatus.UNKNOWN
    if profile.root.status is RootStatus.UNKNOWN:
        return "R01_UNKNOWN_ROOT", OperabilityStatus.UNKNOWN

    cut_off = profile.obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT
    weak = _is_weak_stage(profile)
    support = profile.support.status
    stable_support = support is SupportStatus.INDIRECT_GENERATION_STABLE

    # 정기 뿌리가 없으면 최고 등급 자격을 주지 않는다(CAL-ROOT-01c). 유근 여부는 그대로
    # 유지하고 **자격만** 제한한다 — 중기·여기 차등 감점이나 가중치는 도입하지 않는다.
    #
    # `has_main_qi_root=False` 로 판정하지 않는다. 그 값은 중기·여기뿐 아니라 NONE·UNKNOWN
    # 에서도 False 라서, 직접 뿌리가 있는데 깊이가 NONE 인 모순 조합까지 조용히 하향시킨다.
    # 하향은 **명시적으로 중기·여기일 때만** 한다.
    main_qi = profile.root.strongest_root_depth is RootDepth.MAIN_QI
    non_main = profile.root.strongest_root_depth in (
        RootDepth.MIDDLE_QI, RootDepth.RESIDUAL_QI)

    # ── 유근: 원국 + 운 ─────────────────────────────────────────────
    if profile.root.status is RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT:
        if not cut_off and main_qi:
            return "R10_NATAL_AND_TRANSIT_ROOT_CLEAR", OperabilityStatus.FULLY_OPERABLE
        if not cut_off and non_main:
            return ("R10_NATAL_AND_TRANSIT_NON_MAIN_ROOT_CAP",
                    OperabilityStatus.OPERABLE)
        if not cut_off:
            # 직접 뿌리인데 깊이가 NONE·UNKNOWN — 프로필 불변식 위반이다. 조용히 하향하지
            # 않고 기존 결과를 유지한다.
            return "R10_NATAL_AND_TRANSIT_ROOT_CLEAR", OperabilityStatus.FULLY_OPERABLE
        if weak:
            return "R11_NATAL_AND_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE", (
                OperabilityStatus.WEAKENED)
        return "R12_NATAL_AND_TRANSIT_ROOT_CUT_OFF", (
            OperabilityStatus.PARTIALLY_OPERABLE)

    # ── 유근: 원국 ─────────────────────────────────────────────────
    if profile.root.status is RootStatus.DIRECT_NATAL_ROOT:
        if not cut_off and stable_support and non_main:
            return "R20_NATAL_NON_MAIN_ROOT_CAP", OperabilityStatus.OPERABLE
        if not cut_off and stable_support:
            return "R20_NATAL_ROOT_STABLE_SUPPORT", OperabilityStatus.FULLY_OPERABLE
        if not cut_off:
            # 간접 생조원이 흔들렸다고 원국의 직접 뿌리까지 무효로 만들지 않는다.
            return "R21_NATAL_ROOT_CLEAR", OperabilityStatus.OPERABLE
        if weak:
            return "R22_NATAL_ROOT_CUT_OFF_WEAK_STAGE", OperabilityStatus.WEAKENED
        return "R23_NATAL_ROOT_CUT_OFF", OperabilityStatus.PARTIALLY_OPERABLE

    # ── 유근: 운 전용 ───────────────────────────────────────────────
    if profile.root.status is RootStatus.DIRECT_TRANSIT_ROOT:
        if not cut_off:
            # 안정 생조가 함께 있어도 FULLY 로 올리지 않는다. 작동력이 약해서가 아니라
            # 해당 시기의 운에 의존하는 기반이라 최고 확정 등급을 보류하는 것이다.
            return "R30_TRANSIT_ROOT_CLEAR", OperabilityStatus.OPERABLE
        if weak:
            return "R31_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE", OperabilityStatus.WEAKENED
        return "R32_TRANSIT_ROOT_CUT_OFF", OperabilityStatus.PARTIALLY_OPERABLE

    # ── 무근 ───────────────────────────────────────────────────────
    if cut_off:
        if support in _UNRELIABLE_SUPPORT:
            # 첫 버전 SUPPRESSED 의 핵심 성립 규칙.
            return "R40_ROOTLESS_CUT_OFF_NO_RELIABLE_SUPPORT", (
                OperabilityStatus.SUPPRESSED)
        # 안정 경로가 하나라도 남아 있으면 바로 낮추지 않는다(MIXED 포함).
        return "R41_ROOTLESS_CUT_OFF_WITH_SUPPORT", OperabilityStatus.WEAKENED
    if support in _UNRELIABLE_SUPPORT:
        return "R42_ROOTLESS_NO_RELIABLE_SUPPORT", OperabilityStatus.WEAKENED
    # STABLE · PRESENT_MIXED — 우세 판단은 하지 않는다.
    return "R43_ROOTLESS_WITH_SUPPORT", OperabilityStatus.PARTIALLY_OPERABLE


def evaluate_element_operability(
    profile: ElementOperabilityProfile,
) -> OperabilityEvaluation:
    """신호 프로필 → 등급. **역할을 모른다.**

    Args:
        profile: P2-1 역할 중립 프로필.

    Returns:
        등급·앵커·선택된 규칙·사유·근거. 앵커는 등급에서 결정되며 개별 신호의 가감으로
        만들어지지 않는다.
    """
    rule_id, status = _match_rule(profile)
    reasons = list(profile.reason_codes)
    if profile.obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT:
        reasons.append("CUT_OFF_PRESENT")
    if _is_weak_stage(profile):
        reasons.append(
            "TWELVE_STAGE_TOMB" if profile.stage.stage == "묘" else "TWELVE_STAGE_WEAK")
    if status is OperabilityStatus.SUPPRESSED:
        reasons.append("COMPOSITE_SUPPRESSION")
    return OperabilityEvaluation(
        status=status, anchor=OPERABILITY_ANCHOR[status], matched_rule_id=rule_id,
        # 같은 evidence 가 사유 여럿에 연결돼도 기여는 한 번이다 — 규칙이 하나뿐이라
        # 구조적으로 중복 감점이 불가능하다.
        reason_codes=tuple(dict.fromkeys(reasons)),
        evidence_ids=tuple(sorted(set(profile.evidence_ids))),
    )

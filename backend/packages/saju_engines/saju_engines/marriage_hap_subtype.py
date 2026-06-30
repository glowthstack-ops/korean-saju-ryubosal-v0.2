"""MT4 — 관계 도메인 한정 HAP 합 종류(subtype) 재가중 (v2.2, 2026-06-30).

육합/삼합/방합은 모두 `_REL_KIND`에서 HAP으로 붕괴해 relation_palace가 동일 보너스로 처리한다.
영상·통설상 부부의 합은 육합 > 삼합 > 방합 순이므로, **관계/결혼 도메인에 한해** 합 종류별
multiplier로 기존 HAP 보너스를 **재분배**한다(MARRIAGE_TIMING_ENHANCEMENT §9).

**상향 보정 없음**: 모든 multiplier ≤ 1.0(포화 방지 목적). 육합은 1.0(불변), 삼합·방합만 감쇠.
unknown/천간합 등 판정 누락은 반드시 1.0(기존값 보존). gender 미상이면 partnerElement 완화(0.80)를
적용하지 않고 0.75까지만(보수적). 이 모듈은 **순수 함수**이며 점수 적용·모드 분기는 호출부가 한다.
"""

from __future__ import annotations

# 오행 상극(한자) — 재성=일간이 극하는 오행 / 관살=일간을 극하는 오행.
_CONTROLS: dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def partner_elements(day_element: str, gender: str) -> set[str]:
    """배우자성 오행 — 여=관살(일간을 극) / 남=재성(일간이 극). gender 미상은 빈 집합(보수적)."""
    if gender == "female":
        officer = next((e for e, v in _CONTROLS.items() if v == day_element), "")
        return {officer} - {""}
    if gender == "male":
        wealth = _CONTROLS.get(day_element, "")
        return {wealth} - {""}
    return set()  # 미상 — partnerElement 완화(0.80) 미적용(보수적)


def mt4_subtype_multiplier(
    hap_subtype: str | None,
    *,
    on_spouse_palace: bool,
    partner_element: bool,
) -> tuple[float, str]:
    """합 종류·일지 포함·배우자성 오행 → (multiplier, reason_code).

    Args:
        hap_subtype: 'six_harmony'|'three_harmony'|'directional'|'stem'|None.
        on_spouse_palace: 활성 궁이 일지(배우자궁)인가(방합 게이트).
        partner_element: 방합 완성 오행이 배우자성 오행인가(gender 미상이면 호출부가 False로 전달).

    Returns:
        (multiplier(≤1.0), reason_code). 미상/천간합/누락은 (1.0, fallback).
    """
    if hap_subtype == "six_harmony":
        return (1.00, "MT4_HAP_SIX_MULTIPLIER_1_00")
    if hap_subtype == "three_harmony":
        return (0.85, "MT4_HAP_THREE_MULTIPLIER_0_85")
    if hap_subtype == "directional":
        if on_spouse_palace and partner_element:
            return (0.80, "MT4_HAP_DIRECTIONAL_PARTNER_ELEMENT_0_80")
        if on_spouse_palace:
            return (0.75, "MT4_HAP_DIRECTIONAL_DAY_BRANCH_0_75")
        return (0.70, "MT4_HAP_DIRECTIONAL_MULTIPLIER_0_70")
    return (1.00, "MT4_HAP_UNKNOWN_FALLBACK_1_00")  # stem/None/미지 — 기존값 보존

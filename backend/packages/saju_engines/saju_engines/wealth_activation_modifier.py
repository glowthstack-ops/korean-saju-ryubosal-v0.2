"""횡재 발동 모디파이어 (v2.2 Phase 2, 2026-06-16).

원국 횡재 그릇(WealthCapacity)과 그 시점의 재물 발동(재성국 완성·묘고 충개고·재성 투간·식상생재)을
결합해 windfall/wealth_change 후보 점수를 **보수적으로** 가산한다. 그릇은 하드 게이트가 아니라
**배율**로 쓴다 — 원국 그릇이 없어도 운에서 완성되면 일부 인정(weak도 0.5배). 가중치는 단일 사례
가설에서 출발한 **잠정값**이며 Phase 4 캘리브레이션(당첨 코퍼스+대조군)에서 확정한다(절대원칙 5).

당첨을 단정하지 않는다 — 점수는 표시용 내부값(display_score)일 뿐이고, windfall 표현 제한(당첨·
번호 단정 금지)은 별도 금기룰·프롬프트가 강제한다.
"""

from __future__ import annotations

from saju_shared_types.event_engine import EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import EventKeyV2
from saju_shared_types.wealth_capacity import WealthCapacity

# 원국 그릇 배율 — 그릇이 받쳐줄수록 크게 쥔다(운 완성만으로도 weak 0.5 인정).
_CAP_MULT: dict[str, float] = {"strong": 1.0, "moderate": 0.7, "weak": 0.5}
# 발동별 base 가중(잠정 — Phase 4 캘리브레이션 전). 재성국 완성 > 충개고 > 투간·식상생재.
_ACT_WEIGHT: dict[str, float] = {
    "재성국 완성": 0.18,
    "묘고 충개고": 0.12,
    "식상생재": 0.10,
}
# 계열 인지 감쇠(2차-2단계) — 발동은 모두 '재성 작동' 한 계열이라, 대표 1개만 full로 두고
# 추가는 감쇠한다(중복 집계 방지). 같은 현상을 여러 이름으로 더해 100에 붙던 문제(2026-06-16).
_DIMINISH_TIERS: tuple[float, ...] = (1.0, 0.45, 0.25)  # 대표·2번째·3번째
# 교차 중복 — 그 발동이 이미 base 십성 조합으로 점수화됐으면(같은 fingerprint) 추가 가산 최소화.
_ACT_BASE_OVERLAP: dict[str, set[str]] = {
    "식상생재": {
        "COMBO_OUTPUT_WEALTH", "SPEC_SHISHEN_ZHENGCAI",
        "SPEC_SHISHEN_PIANCAI", "SPEC_SHANGGUAN_ZHENGCAI",
    },
}
_DUP_FACTOR = 0.35  # base에 이미 잡힌 발동 — 추가 가산 35%만
_TARGET_KEYS = (EventKeyV2.WINDFALL, EventKeyV2.WEALTH_CHANGE)


def _family_boost(activations: list[str], reason_codes: list[str], mult: float) -> float:
    """발동들을 '재성 작동' 한 계열로 보고 대표 강·추가 감쇠·교차중복 제거로 boost 산출.

    가중 큰 순으로 대표(1.0)·2번째(0.45)·3번째(0.25)…, 그 발동이 이미 base 조합에 잡혔으면
    추가로 ×0.35(이중 집계 방지). 단순 sum이 아니라 감쇠 합 → 같은 현상 반복 누적을 막는다.
    """
    rc = set(reason_codes)
    items = sorted(
        ((_ACT_WEIGHT.get(a, 0.0), a) for a in activations if _ACT_WEIGHT.get(a, 0.0) > 0),
        key=lambda x: -x[0],
    )
    total = 0.0
    for i, (w, a) in enumerate(items):
        factor = _DIMINISH_TIERS[i] if i < len(_DIMINISH_TIERS) else 0.1
        if _ACT_BASE_OVERLAP.get(a, set()) & rc:  # base에 이미 같은 fingerprint
            factor *= _DUP_FACTOR
        total += w * factor
    return total * mult


class WealthActivationModifier:
    """그릇 × 발동 → windfall/wealth_change 보수 가산(다른 도메인·미발동 시 무영향)."""

    @staticmethod
    def apply(
        candidates: list[EventCandidateV2],
        capacity: WealthCapacity,
        activations: list[str],
    ) -> list[EventCandidateV2]:
        """발동이 있을 때만 재물 후보 점수를 (1+boost)배 한다(클램프 0~100)."""
        if not activations:
            return candidates
        mult = _CAP_MULT.get(capacity.capacity_band, 0.5)
        tag = "WEALTHACT_" + "+".join(activations)
        diminished = len(activations) > 1  # 같은 계열 복수 발동 → 감쇠 적용 표식
        out: list[EventCandidateV2] = []
        for c in candidates:
            # boost는 후보별로(교차 중복은 그 후보의 base 조합 유무에 따라 달라진다).
            boost = _family_boost(activations, c.reason_codes, mult)
            if c.event_key in _TARGET_KEYS and boost > 0:
                reasons = [*c.reason_codes, tag]
                if diminished or (_ACT_BASE_OVERLAP.keys() & set(activations)):
                    reasons.append("WEALTHACT_FAMILY_DIMINISH")
                new_score = max(0, round(c.score * (1 + boost)))  # 중간 100 클램프 제거
                out.append(c.model_copy(update={
                    "score": new_score,
                    "reason_codes": reasons,
                    "contributions": {**c.contributions, "wealth_act": float(new_score - c.score)},
                }))
            else:
                out.append(c)
        return out

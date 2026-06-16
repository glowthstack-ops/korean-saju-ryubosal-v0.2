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
_TARGET_KEYS = (EventKeyV2.WINDFALL, EventKeyV2.WEALTH_CHANGE)


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
        boost = sum(_ACT_WEIGHT.get(a, 0.0) for a in activations) * mult
        if boost <= 0:
            return candidates
        tag = "WEALTHACT_" + "+".join(activations)
        out: list[EventCandidateV2] = []
        for c in candidates:
            if c.event_key in _TARGET_KEYS:
                out.append(c.model_copy(update={
                    "score": max(0, min(100, round(c.score * (1 + boost)))),
                    "reason_codes": [*c.reason_codes, tag],
                }))
            else:
                out.append(c)
        return out

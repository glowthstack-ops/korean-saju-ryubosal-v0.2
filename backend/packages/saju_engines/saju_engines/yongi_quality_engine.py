"""YongiQualityEngine (Phase 6) — 용신·희신·기신 극성으로 사건 '품질(길흉)'을 확정한다.

transit_ten_god_branching.polarity_rules(점수 배율 + 기신 quality_flip)와 yonggi_quality_matrix
(이벤트별 yong/gi 서술)를 결합한다. 사건 '타입'은 바꾸지 않고 점수·quality·서술 힌트만 보정한다.
극성(polarity_role)은 상위 통합 계층이 운의 오행 길흉으로 채워 넣으며, NEUTRAL이면 무보정이다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    EventQuality,
    PolarityRole,
)

# 기신(흉) 발현 시 사건별 품질 — 재물형=손실, 갈등형=충돌, 그 외=압박.
_GI_LOSS = {
    EventKeyV2.WEALTH_CHANGE,
    EventKeyV2.WINDFALL,
    EventKeyV2.BUSINESS_START,
    EventKeyV2.BUSINESS_EXPANSION,
}
_GI_CONFLICT = {
    EventKeyV2.LEGAL_CONFLICT,
    EventKeyV2.SOCIAL_CONFLICT,
    EventKeyV2.RELATIONSHIP_CHANGE,
}
# 용신(길) 발현 시 성취형으로 서술되는 사건.
_YONG_ACHIEVE = {
    EventKeyV2.PROMOTION,
    EventKeyV2.EDUCATION_ADMISSION,
    EventKeyV2.EDUCATION_COMPLETION,
    EventKeyV2.CHILDBIRTH,
    EventKeyV2.CREATIVE_OUTPUT,
    EventKeyV2.PUBLIC_EXPOSURE,
}
# yonggi 품질로 덮어써도 되는(중립적) 기존 quality — 시차/관계성 신호는 보존.
_OVERRIDABLE = {None, EventQuality.OPPORTUNITY, EventQuality.ACHIEVEMENT, EventQuality.MIXED}


class YongiQualityEngine:
    """극성 배율 + 길흉 품질 보정."""

    def __init__(self, dictionaries_dir: Path) -> None:
        base = dictionaries_dir / "event_engine"
        branching = json.loads(
            (base / "transit_ten_god_branching.json").read_text(encoding="utf-8")
        )
        self._mult: dict[str, float] = {
            k: float(v["score_multiplier"]) for k, v in branching["polarity_rules"].items()
        }
        self._flip: set[str] = {
            k for k, v in branching["polarity_rules"].items() if v.get("quality_flip")
        }
        matrix = json.loads((base / "yonggi_quality_matrix.json").read_text(encoding="utf-8"))
        self._matrix: dict[str, dict] = matrix["rules"]

    def apply(self, candidates: list[EventCandidateV2]) -> list[EventCandidateV2]:
        """후보의 polarity_role에 따라 점수 배율과 길흉 quality를 적용한다."""
        out: list[EventCandidateV2] = []
        for c in candidates:
            role = c.polarity_role
            if role is PolarityRole.NEUTRAL:
                out.append(c)
                continue
            reasons = [*c.reason_codes]
            mult = self._mult.get(role.value, 1.0)
            score = c.score * mult
            quality = c.quality
            if role.value in self._flip:  # 기신 — 흉 방향
                if quality in _OVERRIDABLE:
                    quality = self._gi_quality(c.event_key)
                reasons.append(f"YONGGI_{role.value}_flip")
            else:  # 용신·희신 — 길 방향
                if quality is None:
                    quality = self._yong_quality(c.event_key)
                reasons.append(f"YONGGI_{role.value}")
            out.append(c.model_copy(update={
                "score": max(0, min(100, round(score))),
                "quality": quality,
                "reason_codes": reasons,
            }))
        return sorted(out, key=lambda x: -x.score)

    @staticmethod
    def _gi_quality(ek: EventKeyV2) -> EventQuality:
        if ek in _GI_LOSS:
            return EventQuality.LOSS
        if ek in _GI_CONFLICT:
            return EventQuality.CONFLICT
        return EventQuality.PRESSURE

    @staticmethod
    def _yong_quality(ek: EventKeyV2) -> EventQuality:
        return EventQuality.ACHIEVEMENT if ek in _YONG_ACHIEVE else EventQuality.OPPORTUNITY

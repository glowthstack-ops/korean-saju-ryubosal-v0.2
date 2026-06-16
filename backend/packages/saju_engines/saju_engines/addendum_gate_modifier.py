"""AddendumGateModifier (Phase 5) — 과잉 해석을 막는 게이트 계층.

event_gate_safety_rules(안전 downgrade) + user_profile_event_gate(현실 상태 분기) +
void_repetition_modifier(공망 지연·해공)를 적용한다. 사양 조건(한글)을 기계 평가로 옮긴
reviewed:false 초안 — 점수 약화·라벨 강등·품질 태깅으로 후보를 줄인다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    EventTiming,
    LuckLayer,
    TenGod,
)

_WEALTH = {TenGod.ZHENGCAI, TenGod.PIANCAI}
_OUTPUT = {TenGod.SHISHEN, TenGod.SHANGGUAN}
_AUTHORITY = {TenGod.ZHENGGUAN, TenGod.QISHA}
_RESOURCE = {TenGod.ZHENGYIN, TenGod.PIANYIN}


@dataclass
class GateContext:
    """게이트 평가 컨텍스트(엔진이 채움 — 미입력 필드는 게이트 미적용)."""

    present_gods: set[TenGod] = field(default_factory=set)
    layers: set[LuckLayer] = field(default_factory=set)
    void_active: bool = False  # 그 기간 운 지지가 원국 공망(미해공)
    # student/employee/business_owner/freelancer/unemployed/retired
    occupation_status: str | None = None
    relationship_status: str | None = None  # single/dating/married/divorced


class AddendumGateModifier:
    """후보에 안전 게이트·프로필 분기·공망 보정을 적용한다."""

    def apply(
        self, candidates: list[EventCandidateV2], ctx: GateContext
    ) -> list[EventCandidateV2]:
        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = c.event_key
            score = c.score
            quality = c.quality
            timing = c.timing
            new_key = ek
            reasons = [*c.reason_codes]

            # ── event_gate_safety_rules ──────────────────────────
            if ek is EventKeyV2.BUSINESS_START and not (ctx.present_gods & _WEALTH):
                score -= 12
                timing = EventTiming.DELAY  # 방향(quality)은 그대로, 발현만 보류
                reasons.append("GATE_business_start_no_wealth")
            day_trigger = bool({LuckLayer.WOLWOON, LuckLayer.ILWOON} & ctx.layers)
            if ek is EventKeyV2.WINDFALL and not day_trigger:
                new_key = EventKeyV2.WEALTH_CHANGE
                reasons.append("GATE_windfall_to_wealth")
            no_partner_ctx = ctx.relationship_status in (None, "single", "divorced")
            if ek is EventKeyV2.CHILDBIRTH and no_partner_ctx:
                new_key = EventKeyV2.CREATIVE_OUTPUT
                reasons.append("GATE_childbirth_to_creative")
            if ek is EventKeyV2.MARRIAGE_SIGNAL and ctx.relationship_status == "single":
                score -= 12
                reasons.append("GATE_marriage_signal_weak")
            if ek is EventKeyV2.JOB_GAIN and not (ctx.present_gods & (_RESOURCE | _WEALTH)):
                score -= 8  # 관성 단독 — 인성·재성 보조 없음
                reasons.append("GATE_job_gain_unsupported")

            # ── user_profile_event_gate ──────────────────────────
            if ek is EventKeyV2.JOB_GAIN and ctx.occupation_status == "employee":
                new_key = EventKeyV2.PROMOTION  # 재직자 → 취업보다 승진·직무변경
                reasons.append("PROFILE_job_gain_to_promotion")
            if ek is EventKeyV2.NEW_RELATIONSHIP and ctx.relationship_status == "married":
                new_key = EventKeyV2.RELATIONSHIP_CHANGE  # 기혼 → 배우자 이슈
                reasons.append("PROFILE_new_relationship_to_change")
            if ek is EventKeyV2.WEALTH_CHANGE and ctx.occupation_status == "business_owner":
                if ctx.present_gods & _OUTPUT:
                    new_key = EventKeyV2.BUSINESS_EXPANSION  # 사업자 + 식상 → 확장
                    reasons.append("PROFILE_wealth_to_expansion")

            # ── void_activation_modifier ─────────────────────────
            if ctx.void_active:
                score -= 10
                timing = EventTiming.DELAY  # 공망 — 방향은 유지하고 발현만 지연
                reasons.append("VOID_delay")

            out.append(c.model_copy(update={
                "event_key": new_key,
                "score": max(0, min(100, score)),
                "quality": quality,
                "timing": timing,
                "reason_codes": reasons,
            }))
        return self._merge_and_sort(out)

    @staticmethod
    def _merge_and_sort(cands: list[EventCandidateV2]) -> list[EventCandidateV2]:
        """라벨 강등으로 같은 event_key가 생기면 점수 최댓값으로 병합한다."""
        best: dict[EventKeyV2, EventCandidateV2] = {}
        for c in cands:
            cur = best.get(c.event_key)
            if cur is None or c.score > cur.score:
                if cur is not None:
                    c = c.model_copy(update={
                        "reason_codes": sorted(set(c.reason_codes) | set(cur.reason_codes)),
                    })
                best[c.event_key] = c
        return sorted(best.values(), key=lambda x: -x.score)

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
    void_active: bool = False  # 그 기간 운 지지가 원국 공망을 자극(종류 무관 — risk facts 호환)
    # 공망 자극 종류(2026-08-21 데굴님 확정 의미론 — 三命通會 '合則不能空'):
    #   'clash'   충발 — 확정 불변식(발현 지연+변동성 보조)대로 지연 게이트 적용
    #   'fill'    전실 — 가장 명확한 실체화(지연·감점 아님, 신호만)
    #   'combine' 합   — 공망 차단막 약화 + 억제되던 대상의 활성화(지연·감점 아님, 신호만)
    # 비어 있으면(구 호출자) void_active 만으로 기존 동작(충발 취급)을 유지한다.
    void_kinds: set[str] = field(default_factory=set)
    # student/employee/public_official/business_owner/freelancer/unemployed/retired
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
            # 공직자(O02): 재직 공직자의 취업 신호는 승진으로, 승진·인사는 발령·근무지 전보를
            # 동반한다(자료 7-3·12-4 — 공직 승진 = 승진시험 + 발령 + 이동). 사건 종류는 유지하고
            # 동반 가능성만 reason_code로 부여(LLM이 발령·이동을 함께 서술, 점수 불변).
            if ctx.occupation_status == "public_official" and ek in (
                EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION
            ):
                if ek is EventKeyV2.JOB_GAIN:
                    new_key = EventKeyV2.PROMOTION
                    reasons.append("PROFILE_public_official_promotion")
                reasons.append("PROFILE_public_official_transfer")
            if ek is EventKeyV2.NEW_RELATIONSHIP and ctx.relationship_status == "married":
                new_key = EventKeyV2.RELATIONSHIP_CHANGE  # 기혼 → 배우자 이슈
                reasons.append("PROFILE_new_relationship_to_change")
            if ek is EventKeyV2.WEALTH_CHANGE and ctx.occupation_status == "business_owner":
                if ctx.present_gods & _OUTPUT:
                    new_key = EventKeyV2.BUSINESS_EXPANSION  # 사업자 + 식상 → 확장
                    reasons.append("PROFILE_wealth_to_expansion")

            # ── void_activation_modifier ─────────────────────────
            # 확정 의미론(2026-08-21): 지연·감점은 **충발에만**. 전실·합은 공망의
            # 억제가 풀리는 신호라 방향이 반대다 — 서술용 reason만 남긴다.
            # ('해소=공허·지연'으로 뒤집혀 서술되던 결함의 원인 수정 — 申·巳 육합 사례)
            if "clash" in ctx.void_kinds or (ctx.void_active and not ctx.void_kinds):
                score -= 10
                timing = EventTiming.DELAY  # 공망 충발 — 방향은 유지하고 발현만 지연
                reasons.append("VOID_delay")
            if "fill" in ctx.void_kinds:
                reasons.append("VOID_FILL")  # 전실 — 실체화(감점·지연 없음)
            if "combine" in ctx.void_kinds:
                reasons.append("VOID_COMBINE_RELEASE")  # 합 — 차단막 약화·대상 활성화

            new_score = max(0, score)  # 중간 100 클램프 제거 — raw 누적 보존(게이트는 감점만)
            out.append(c.model_copy(update={
                "event_key": new_key,
                "score": new_score,
                "quality": quality,
                "timing": timing,
                "reason_codes": reasons,
                "contributions": {**c.contributions, "gate": float(new_score - c.score)},
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

"""reality_gate — 현실 맥락으로 life_fit을 부여한다(LIFE_EVENT_INFERENCE.md §3).

"있으면 강하게, 없으면 폴백"(규칙11): 맥락 입력이 있으면 맞는 후보의 life_fit을 올리고, 없으면
life_fit=0(차단·오류 없음). 모든 필드 optional. 점수·타입은 바꾸지 않고 life_fit만 채운다.
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2

# 맥락 플래그 → life_fit을 올릴 이벤트 키.
_CAREER = {EventKeyV2.CAREER_CHANGE, EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION}
_RELOCATE = {EventKeyV2.RELOCATION, EventKeyV2.CONTRACT_DOCUMENT}
_MARRIAGE = {EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.RELATIONSHIP_CHANGE}
_NEW_REL = {EventKeyV2.NEW_RELATIONSHIP}
_BIZ = {EventKeyV2.BUSINESS_EXPANSION, EventKeyV2.WEALTH_CHANGE}
_EDU = {EventKeyV2.EDUCATION_ADMISSION, EventKeyV2.EDUCATION_COMPLETION}

_FIT = 40.0  # 맥락 직접 적합 가점
_FIT_SOFT = 20.0  # 약한 적합


@dataclass
class RealityContext:
    """현실 맥락(전부 optional — 미입력은 life_fit 0, 차단 금지)."""

    # student/employee/business_owner/freelancer/unemployed/retired
    occupation_status: str | None = None
    relationship_status: str | None = None    # single/dating/married/divorced
    relocation_planned: bool = False          # 이사 계획
    contract_pending: bool = False            # 계약 진행
    job_change_intent: bool = False           # 이직 의향
    exam_planned: bool = False                # 시험·입시 계획

    def is_empty(self) -> bool:
        return not (
            self.occupation_status or self.relationship_status
            or self.relocation_planned or self.contract_pending
            or self.job_change_intent or self.exam_planned
        )


def apply_life_fit(
    candidates: list[EventCandidateV2], ctx: RealityContext | None
) -> list[EventCandidateV2]:
    """맥락에 맞는 후보의 life_fit을 올린다(미입력=무보정)."""
    if ctx is None or ctx.is_empty():
        return candidates
    fit: dict[EventKeyV2, float] = {}

    def add(keys: set[EventKeyV2], amount: float) -> None:
        for k in keys:
            fit[k] = max(fit.get(k, 0.0), amount)

    if ctx.relocation_planned:
        add(_RELOCATE, _FIT)
    if ctx.contract_pending:
        add({EventKeyV2.CONTRACT_DOCUMENT}, _FIT)
    if ctx.job_change_intent:
        add(_CAREER, _FIT)
    if ctx.exam_planned:
        add(_EDU, _FIT)
    occ = ctx.occupation_status
    if occ == "employee":
        add({EventKeyV2.PROMOTION, EventKeyV2.CAREER_CHANGE}, _FIT_SOFT)
    elif occ == "business_owner":
        add(_BIZ, _FIT_SOFT)
    elif occ in ("unemployed", "student"):
        add({EventKeyV2.JOB_GAIN}, _FIT_SOFT)
    rel = ctx.relationship_status
    if rel == "dating":
        add(_MARRIAGE, _FIT_SOFT)
    elif rel == "single":
        add(_NEW_REL, _FIT_SOFT)

    if not fit:
        return candidates
    out: list[EventCandidateV2] = []
    for c in candidates:
        amt = fit.get(c.event_key, 0.0)
        if amt <= 0:
            out.append(c)
            continue
        out.append(c.model_copy(update={
            "life_fit": amt, "reason_codes": [*c.reason_codes, "LIFE_FIT"],
        }))
    return out

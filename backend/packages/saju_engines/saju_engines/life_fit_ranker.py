"""LifeFitRanker — 삶의 맥락에 가장 맞는 후보를 우선 정렬한다(LIFE_EVENT_INFERENCE.md §1).

EventEngineV2가 만든 후보를 받아 ① 누락 사건 시드(개인 반복/예정 테마) ② 개인 시그니처 매칭
(personal_match) ③ 현실 맥락(life_fit)을 적용하고, 최종 정렬축으로 재정렬한다:

  life_fit > confidence(사건화 증거) > personal_match > potential(=score) > 시점·키

코호트는 활성 게이트(§4.4) 통과 후 별도로 personal_match에 합산된다(본 단계는 개인 시그니처만).
입력이 비면(시그니처·맥락 없음) 결과는 EventEngineV2 정렬과 동치(life_fit·personal_match=0).
"""

from __future__ import annotations

from saju_shared_types.event_engine import EventCandidateV2, lei_rank_key
from saju_shared_types.life_event import LifeEventRow

from .cohort_calibration import CohortStats, apply_cohort_match
from .personal_calibration import apply_personal_match, seed_missing_events
from .reality_context import RealityContext, apply_life_fit


class LifeFitRanker:
    """개인 시그니처·현실 맥락으로 후보를 재정렬한다(점수·타입 불변, 정렬축만 재정의)."""

    def rank(
        self,
        candidates: list[EventCandidateV2],
        *,
        signature: list[LifeEventRow] | None = None,
        reality_context: RealityContext | None = None,
        cohort: CohortStats | None = None,
    ) -> list[EventCandidateV2]:
        """시드 → personal_match(개인) → 코호트 합산 → life_fit 적용 후 LEI 정렬축으로 재정렬한다.

        코호트는 활성 게이트(§4.4)를 통과한 CohortStats만 personal_match에 합산된다(미활성=미반영).
        """
        out = list(candidates)
        if signature:
            periods = sorted({c.period for c in out})
            out = seed_missing_events(out, signature, periods)
            out = apply_personal_match(out, signature)
        if cohort is not None:
            out = apply_cohort_match(out, cohort)
        out = apply_life_fit(out, reality_context)
        return sorted(out, key=lei_rank_key)

"""코호트 활성 게이트 검증 (Life Event Inference 5단계).

백오프(fine>coarse>none) + 임계 미만 미반영(저장만) + 활성 시 personal_match 합산을 확인한다.
순수 단위(DB 미사용 — CohortStats를 합성 입력).
"""

from __future__ import annotations

from saju_engines.cohort_calibration import (
    COARSE_THRESHOLD,
    FINE_THRESHOLD,
    CohortStats,
    apply_cohort_match,
    cohort_stats_from_counts,
    select_tier,
)
from saju_engines.life_fit_ranker import LifeFitRanker
from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2


def _cand(event: str) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=event, period="2026", score=50,
        confidence_level=ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    )


def test_tier_backoff() -> None:
    assert select_tier(0, 0) == "none"
    assert select_tier(COARSE_THRESHOLD, 0) == "coarse"
    assert select_tier(COARSE_THRESHOLD, FINE_THRESHOLD) == "fine"  # fine 우선
    assert select_tier(COARSE_THRESHOLD - 1, FINE_THRESHOLD - 1) == "none"


def test_below_threshold_not_applied() -> None:
    # 임계 미만 → none → personal_match 미반영(저장만).
    coarse = (5, {"relocation": 3})
    fine = (2, {"relocation": 2})
    stats = cohort_stats_from_counts(coarse, fine)
    assert stats.tier == "none"
    out = apply_cohort_match([_cand("relocation")], stats)
    assert out[0].personal_match == 0.0


def test_fine_tier_applies_rate() -> None:
    # fine 표본 충분 → fine 비율을 personal_match에 합산.
    coarse = (30, {"relocation": 12})
    fine = (FINE_THRESHOLD, {"relocation": FINE_THRESHOLD})  # 비율 1.0
    stats = cohort_stats_from_counts(coarse, fine)
    assert stats.tier == "fine"
    out = apply_cohort_match([_cand("relocation"), _cand("career_change")], stats)
    by = {str(c.event_key): c for c in out}
    assert by["relocation"].personal_match > 0
    assert "COHORT_fine" in by["relocation"].reason_codes
    assert by["career_change"].personal_match == 0.0  # 코호트에 없음


def test_coarse_fallback_when_fine_sparse() -> None:
    coarse = (COARSE_THRESHOLD, {"relocation": COARSE_THRESHOLD // 2})  # 0.5
    fine = (1, {"relocation": 1})
    stats = cohort_stats_from_counts(coarse, fine)
    assert stats.tier == "coarse"
    out = apply_cohort_match([_cand("relocation")], stats)
    assert out[0].personal_match > 0
    assert "COHORT_coarse" in out[0].reason_codes


def test_ranker_cohort_only_when_active() -> None:
    r = LifeFitRanker()
    inactive = CohortStats()  # tier none
    out = r.rank([_cand("relocation")], cohort=inactive)
    assert out[0].personal_match == 0.0  # 미활성 — 미반영
    active = CohortStats("fine", 10, {"relocation": 0.7})
    out2 = r.rank([_cand("relocation")], cohort=active)
    assert out2[0].personal_match > 0  # 활성 — 합산

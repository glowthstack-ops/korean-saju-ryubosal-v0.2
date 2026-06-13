"""cohort_calibration — 동일사주 코호트 신호 + 활성 게이트(LIFE_EVENT_INFERENCE.md §4.3·§4.4).

같은 사주(일주+성별=coarse / 전체 4기둥+성별=fine) 사용자들의 확인 사건 빈도를 personal_match에
합산한다. 단, **코호트 표본이 임계 미만이면 미반영(저장만)** — 소표본 왜곡 차단(활성 게이트).
백오프: fine 표본이 충분하면 fine, 아니면 coarse, 둘 다 미달이면 none(코호트 신호 0).
익명 집계만(개인 비노출). 확률적 경향이며 단정 아님(규칙3·8) — confidence/personal_match에만 기여.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.event_engine import EventCandidateV2

# 활성 임계(표본=확정 사건 보유 distinct subject 수). fine은 특이해 적은 표본도 유의,
# coarse는 넓어 노이즈가 커 더 많은 표본을 요구한다(reviewed:false 초안 — 데이터 축적 후 조정).
COARSE_THRESHOLD = 20
FINE_THRESHOLD = 8
_SCALE = 60.0  # 코호트 빈도(0~1) → personal_match 기여 상한(개인 시그니처보다 약하게)


@dataclass
class CohortStats:
    """선택된 코호트 계층의 집계(활성 게이트 통과 결과)."""

    tier: str = "none"  # 'fine' | 'coarse' | 'none'
    total: int = 0      # 코호트 표본(distinct subject) 수
    rate_by_event: dict[str, float] = field(default_factory=dict)  # event_key → 보유 비율 0~1


def select_tier(
    coarse_total: int, fine_total: int,
    *, coarse_threshold: int = COARSE_THRESHOLD, fine_threshold: int = FINE_THRESHOLD,
) -> str:
    """백오프 — fine 충분하면 fine, 아니면 coarse, 둘 다 미달이면 none(미반영)."""
    if fine_total >= fine_threshold:
        return "fine"
    if coarse_total >= coarse_threshold:
        return "coarse"
    return "none"


def cohort_stats_from_counts(
    coarse: tuple[int, dict[str, int]], fine: tuple[int, dict[str, int]],
    *, coarse_threshold: int = COARSE_THRESHOLD, fine_threshold: int = FINE_THRESHOLD,
) -> CohortStats:
    """coarse/fine (총인원, 이벤트별 인원) → 활성 계층의 비율 통계(미달이면 none)."""
    coarse_total, coarse_cnt = coarse
    fine_total, fine_cnt = fine
    tier = select_tier(
        coarse_total, fine_total,
        coarse_threshold=coarse_threshold, fine_threshold=fine_threshold,
    )
    if tier == "fine":
        return CohortStats("fine", fine_total, _rates(fine_total, fine_cnt))
    if tier == "coarse":
        return CohortStats("coarse", coarse_total, _rates(coarse_total, coarse_cnt))
    return CohortStats()


def _rates(total: int, counts: dict[str, int]) -> dict[str, float]:
    return {ek: c / total for ek, c in counts.items()} if total else {}


def apply_cohort_match(
    candidates: list[EventCandidateV2], stats: CohortStats
) -> list[EventCandidateV2]:
    """활성 코호트면 이벤트별 보유 비율을 personal_match에 합산한다(미활성=미반영)."""
    if stats.tier == "none" or stats.total == 0:
        return candidates  # 활성 게이트 미통과 — 코호트 신호 0(저장만)
    out: list[EventCandidateV2] = []
    for c in candidates:
        rate = stats.rate_by_event.get(str(c.event_key), 0.0)
        if rate <= 0:
            out.append(c)
            continue
        bonus = round(rate * _SCALE, 1)
        out.append(c.model_copy(update={
            "personal_match": c.personal_match + bonus,
            "reason_codes": [*c.reason_codes, f"COHORT_{stats.tier}"],
        }))
    return out

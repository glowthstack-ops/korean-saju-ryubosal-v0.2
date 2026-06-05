"""검증 기간 선택: 후보 모델의 예측이 갈리거나 강하게 작동하는 해를 고른다."""

from __future__ import annotations

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.constants import BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.yongsin import AggregatedYongsinResult, YongsinCandidateModel


def _model_elements(m: YongsinCandidateModel) -> tuple[set[str], set[str]]:
    favorable = {x for x in (m.yongsin, m.heesin) if x}
    unfavorable = {x for x in (m.gisin, m.gusin) if x}
    return favorable, unfavorable


def expected_effect(m: YongsinCandidateModel, year_elements: set[str]) -> str:
    fav, unfav = _model_elements(m)
    hit_f = bool(fav & year_elements)
    hit_u = bool(unfav & year_elements)
    if hit_f and not hit_u:
        return "positive"
    if hit_u and not hit_f:
        return "negative"
    if hit_f and hit_u:
        return "mixed"
    return "neutral"


def select_validation_periods(
    yongsin: AggregatedYongsinResult,
    birth_year: int,
    reference_year: int,
    min_age: int = 12,
) -> list[dict]:
    """기억 가능 연령대(min_age~현재)의 해를 정보량 순으로 정렬해 반환."""
    models = yongsin.candidate_models
    periods: list[dict] = []
    for year in range(birth_year + min_age, reference_year + 1):
        stem, branch = year_ganzi(year)
        year_elements = {str(STEM_ELEMENT[stem]), str(BRANCH_ELEMENT[branch])}
        exp_by_model = {m.model_type: expected_effect(m, year_elements) for m in models}
        nonneutral = [v for v in exp_by_model.values() if v != "neutral"]
        distinct = {v for v in nonneutral}
        disagree = len(distinct) > 1
        score = len(nonneutral) + (3 if disagree else 0)
        periods.append({
            "year": year,
            "age": year - birth_year,
            "ganji": f"{stem}{branch}",
            "activated_elements": sorted(year_elements),
            "expected_by_model": exp_by_model,
            "disagree": disagree,
            "score": score,
        })
    periods.sort(key=lambda p: (p["score"], p["year"]), reverse=True)
    return periods

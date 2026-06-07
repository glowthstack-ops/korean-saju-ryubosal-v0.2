"""검증 기간 선택: 후보 모델의 예측이 갈리거나 강하게 작동하는 해를 고른다."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.constants import BRANCH_CLASHES, BRANCH_ELEMENT, STEM_ELEMENT
from saju_shared_types.enums import Branch
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.yongsin import AggregatedYongsinResult, YongsinCandidateModel

_KST = ZoneInfo("Asia/Seoul")


def _apply_dynamics(effect: str, is_void: bool, has_clash: bool) -> str:
    """세운 지지의 공망·충이 발현을 바꾼다 — 공망=실속 약화(mixed), 충=사건성(volatile).

    검증 채점에서 공망으로 muted된 해를 '모델 오답'으로 깎지 않게(mixed=절반 반영),
    충 해는 방향보다 변동으로 보게(volatile=약한 반영) 한다.
    """
    if effect in ("positive", "negative"):
        if has_clash:  # 공망+충 포함 — 사건성 우세
            return "volatile"
        if is_void:
            return "mixed"
    return effect


def _sewoon_range(year: int) -> str:
    """세운 = [입춘 year, 입춘 year+1). KST 날짜 범위 라벨로(양력연도-세운 불일치 명시)."""
    tbl = get_table()
    start = tbl.lichun_for_year(year).astimezone(_KST).date()
    nxt = tbl.lichun_for_year(year + 1).astimezone(_KST)
    end = (nxt - timedelta(days=1)).date()
    return f"입춘 기준 {start.isoformat()} ~ {end.isoformat()}"


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
    pillars: FourPillarsResult | None = None,
    min_age: int = 12,
) -> list[dict]:
    """기억 가능 연령대(min_age~현재)의 해를 정보량 순으로 정렬해 반환.

    세운 지지가 원국 공망이거나 충을 맺으면 발현이 변형되므로(공망=실속 약화, 충=사건성),
    expected_effect를 보정하고 '깨끗한'(공망·충 없는) 해를 검증 우선순위로 올린다.
    """
    models = yongsin.candidate_models
    void_set = set(pillars.gongmang_branches) if pillars else set()
    natal_branches: list[Branch] = []
    if pillars is not None:
        natal_pillars = [pillars.year, pillars.month, pillars.day]
        if pillars.hour is not None:
            natal_pillars.append(pillars.hour)
        natal_branches = [Branch(p.branch) for p in natal_pillars]
    periods: list[dict] = []
    for year in range(birth_year + min_age, reference_year + 1):
        stem, branch = year_ganzi(year)
        year_elements = {str(STEM_ELEMENT[stem]), str(BRANCH_ELEMENT[branch])}
        is_void = str(branch) in void_set
        has_clash = any(frozenset({branch, nb}) in BRANCH_CLASHES for nb in natal_branches)
        clean = not is_void and not has_clash
        raw = {m.model_type: expected_effect(m, year_elements) for m in models}
        exp_by_model = {mt: _apply_dynamics(e, is_void, has_clash) for mt, e in raw.items()}
        nonneutral = [v for v in exp_by_model.values() if v != "neutral"]
        distinct = {v for v in nonneutral}
        disagree = len(distinct) > 1
        # 깨끗한 해(공망·충 없음)는 방향 신호가 또렷 → 검증 우선순위 상향.
        score = len(nonneutral) + (3 if disagree else 0) + (2 if clean else 0)
        periods.append({
            "year": year,
            "is_void": is_void,
            "has_clash": has_clash,
            "clean": clean,
            "age": year - birth_year,
            "ganji": f"{stem}{branch}",
            "range_label": _sewoon_range(year),
            "activated_elements": sorted(year_elements),
            "expected_by_model": exp_by_model,
            "disagree": disagree,
            "score": score,
        })
    periods.sort(key=lambda p: (p["score"], p["year"]), reverse=True)
    return periods

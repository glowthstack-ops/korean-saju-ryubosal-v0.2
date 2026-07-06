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


# 교운기(대운 교체) 거리별 질문 후보 boost(CAL-P0-a — 상담 사례 파생, 2026-07-03 확정).
# 교체 연도와의 거리 |Δ|년 → 가중. ranking(질문 후보 순서)에만 관여하며 event score·
# favorability·용신 role·세운/월운 산출에는 절대 개입하지 않는다.
_TRANSITION_WEIGHTS: dict[int, float] = {0: 1.0, 1: 0.368, 2: 0.135, 3: 0.05}


def transition_weight(year: int, transition_years: list[int] | None) -> float:
    """해당 연도의 교운기 근접 가중(0~1.0) — 가장 가까운 교체 연도 기준."""
    if not transition_years:
        return 0.0
    return max(
        (_TRANSITION_WEIGHTS.get(abs(year - t), 0.0) for t in transition_years),
        default=0.0,
    )


def select_validation_periods(
    yongsin: AggregatedYongsinResult,
    birth_year: int,
    reference_year: int,
    pillars: FourPillarsResult | None = None,
    min_age: int = 12,
    transition_years: list[int] | None = None,
) -> list[dict]:
    """기억 가능 연령대(min_age~현재)의 해를 정보량 순으로 정렬해 반환.

    세운 지지가 원국 공망이거나 충을 맺으면 발현이 변형되므로(공망=실속 약화, 충=사건성),
    expected_effect를 보정하고 '깨끗한'(공망·충 없는) 해를 검증 우선순위로 올린다.

    transition_years(대운 교체 연도)가 주어지면 교운기 전후 해(±3년 감쇠)에 boost를 더해
    질문 후보 순위를 올린다(CAL-P0-a) — 변화 체감이 크고 기억이 선명한 구간을 먼저 묻기
    위함이며, expected_by_model 등 엔진 판정값은 불변(후보 순서·score 필드만 변화).
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
        # 교운기 근접 boost(최대 +1.0)는 ranking에만 가산(CAL-P0-a).
        t_weight = transition_weight(year, transition_years)
        score = (
            len(nonneutral) + (3 if disagree else 0) + (2 if clean else 0) + t_weight
        )
        periods.append({
            "year": year,
            "is_void": is_void,
            "has_clash": has_clash,
            "clean": clean,
            "age": year - birth_year,
            "ganji": f"{stem}{branch}",
            "range_label": _sewoon_range(year),
            "activated_elements": sorted(year_elements),
            # CAL-P1-b — B 앵커 강도(천간·지지 동시 활성 판별)용 분리 필드.
            "stem_element": str(STEM_ELEMENT[stem]),
            "branch_element": str(BRANCH_ELEMENT[branch]),
            "expected_by_model": exp_by_model,
            "disagree": disagree,
            "score": score,
            "transition_weight": t_weight,
        })
    periods.sort(key=lambda p: (p["score"], p["year"]), reverse=True)
    return periods

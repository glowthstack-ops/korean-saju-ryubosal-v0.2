"""Internal helpers: decode a FourPillarsResult into stem/branch enums."""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

# Position weights (오행/십성 effective distribution) — five_element spec §8.
# NOTE: 분포(effective/visible)의 지장간 가중치는 별도 상수가 아니라 지지별 budget(합=1.0,
# constants.hidden_stems_for)을 쓴다(버그픽스). 분포용 hidden 가중치 상수를 두지 않는다.
STEM_POS_WEIGHT: dict[str, int] = {"year": 8, "month": 12, "day": 0, "hour": 10}
BRANCH_POS_WEIGHT: dict[str, int] = {"year": 12, "month": 28, "day": 24, "hour": 16}

# 표시용 분포율(오행/십성)의 자리별 가중치 — 천간 각 10, 지지 年15·月25·日15·時15.
# 십성/환경오행은 일간 제외(7자리=100), 원국오행은 일간 포함(raw 110 → 100 정규화).
# 지지는 지장간 비율(constants.hidden_stems_for)로 분배. 월령/투간/공망 보정은 미적용(별도 레이어).
DIST_STEM_WEIGHT: dict[str, int] = {"year": 10, "month": 10, "day": 10, "hour": 10}
DIST_BRANCH_WEIGHT: dict[str, int] = {"year": 15, "month": 25, "day": 15, "hour": 15}

# Root-score weights — strength_9_band spec §4. 통근 점수 전용이며, 분포의 budget(0.75/0.25 …)과
# 의도적으로 다르다(통근은 '뿌리의 버팀'을 보므로 본기 1.0/중기 0.60/여기 0.35로 더 강하게 본다).
# 분포 계산에는 절대 사용하지 않는다.
ROOT_BRANCH_WEIGHT: dict[str, int] = {"month": 35, "day": 30, "hour": 18, "year": 12}
ROOT_HIDDEN_WEIGHT: dict[str, float] = {"main": 1.00, "middle": 0.60, "residual": 0.35}
ROOT_STRENGTH_BY_POSITION: dict[str, str] = {
    "month": "strong", "day": "strong", "hour": "medium", "year": "weak",
}


@dataclass
class ChartView:
    day_master: Stem
    month_branch: Branch
    # position -> (stem, branch); hour omitted when time unknown
    stems: list[tuple[str, Stem]]  # (position, stem) including day
    branches: list[tuple[str, Branch]]
    heavenly_stems: set[Stem]
    heavenly_elements: set[str]


def view(pillars: FourPillarsResult) -> ChartView:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))

    stems = [(pos, Stem(p.stem)) for pos, p in items]
    branches = [(pos, Branch(p.branch)) for pos, p in items]
    heavenly = {s for _, s in stems}
    from saju_shared_types.constants import STEM_ELEMENT

    return ChartView(
        day_master=Stem(pillars.day.stem),
        month_branch=Branch(pillars.month.branch),
        stems=stems,
        branches=branches,
        heavenly_stems=heavenly,
        heavenly_elements={str(STEM_ELEMENT[s]) for s in heavenly},
    )

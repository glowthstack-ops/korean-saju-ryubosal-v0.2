"""재물 준비기(lead-up) 판정 — 발현 후보년과 선행 준비 신호 (2026-07-12 데굴님 확정).

세운의 십성 라벨(천간·지지 본기)만 조회하는 순수 함수. 재물운 강의 대조 P3 반영.

확정 규칙:
- 발현 후보년: 세운 천간 또는 지지 본기에 재성 유입(등급제 — 확정 발현년 아님).
  두 자리 모두 재성군=strong, 한쪽 재성+식상 동반(식상생재 유입)=moderate, 한쪽 단독=weak.
- 준비기 창: 발현 후보년 직전 2년(Y-1 가중 1.0, Y-2 가중 0.55). Y-3 이전·대운 확장 금지.
- 준비 신호: 식상=1차, 비겁=2차(조건부). 인성은 준비년 단독 생성 금지(식상 동반 시
  resource_support 보조 태그만). 이벤트 엔진은 발현년 결정에 관여하지 않는다(순환 참조 방지).
- 서술 전용 inert: 점수·순위·발현 시점·confidence·favorability 불변, 사건 생성 금지.
"""

from __future__ import annotations

from saju_shared_types.event_engine import TEN_GOD_GROUP, TEN_GOD_KO_TO_KEY, TenGodGroup
from saju_shared_types.luck import LuckPillar
from saju_shared_types.preparation_context import (
    ManifestationCandidate,
    PreparationContext,
    PreparationYear,
)

_Y2_WEIGHT = 0.55  # Y-2 약한 선행 준비기(데굴님 확정 0.5~0.6의 중앙값)
_GRADE_ORDER = {"strong": 0, "moderate": 1, "weak": 2}
_MAX_CANDIDATES = 3  # 서술 소음 방지 — 등급 우선·근접년 우선 상위만


def _position_groups(pillar: LuckPillar) -> dict[str, TenGodGroup | None]:
    """기둥의 천간/지지 본기 자리별 십성군(라벨 미해석 시 None)."""
    stem = TEN_GOD_KO_TO_KEY.get(pillar.stem_ten_god)
    branch = TEN_GOD_KO_TO_KEY.get(pillar.branch_ten_god)
    return {
        "stem": TEN_GOD_GROUP[stem] if stem is not None else None,
        "branch_main": TEN_GOD_GROUP[branch] if branch is not None else None,
    }


def _grade_manifestation(groups: dict[str, TenGodGroup | None]) -> tuple[str, list[str]] | None:
    """재성 유입 등급 판정 — 재성 없으면 None."""
    wealth_pos = [pos for pos, g in groups.items() if g is TenGodGroup.WEALTH]
    if not wealth_pos:
        return None
    if len(wealth_pos) == 2:
        return "strong", wealth_pos
    if TenGodGroup.OUTPUT in groups.values():  # 같은 해 식상 동반 = 식상생재 유입 보강
        return "moderate", wealth_pos
    return "weak", wealth_pos


def _grade_preparation(groups: dict[str, TenGodGroup | None]) -> tuple[str, list[str], bool] | None:
    """준비 신호 강도 판정 — 식상/비겁 없으면 None(인성 단독은 준비년 생성 금지)."""
    prep_pos = [pos for pos, g in groups.items() if g in (TenGodGroup.OUTPUT, TenGodGroup.PEER)]
    if not prep_pos:
        return None
    has_output = TenGodGroup.OUTPUT in groups.values()
    has_peer = TenGodGroup.PEER in groups.values()
    signals = ([] if not has_output else ["output"]) + ([] if not has_peer else ["peer"])
    # 식상+비겁 또는 두 자리 모두 준비 신호 = strong / 식상 = moderate / 비겁 단독 = weak(조건부).
    if (has_output and has_peer) or len(prep_pos) == 2:
        strength = "strong"
    elif has_output:
        strength = "moderate"
    else:
        strength = "weak"
    resource_support = has_output and TenGodGroup.RESOURCE in groups.values()
    return strength, signals, resource_support


def build_preparation_context(
    yearly_luck: list[LuckPillar],
    reference_year: int,
    horizon_years: int = 5,
) -> PreparationContext:
    """세운 목록 → 준비기 컨텍스트(서술 전용).

    발현 후보년 탐색 창 = [기준년, 기준년+horizon_years] (docs/16 전망 지평 5년과 정합).
    준비년은 후보년 직전 2년 — 기준년 이전 과거 해도 세운 창에 있으면 판정한다
    (과거 준비년 서술은 회상·확인형으로만 — 사건 생성 금지, 디렉티브에서 강제).
    """
    by_year: dict[int, LuckPillar] = {}
    for p in yearly_luck:
        if p.period_type != "year":
            continue
        try:
            by_year[int(p.label)] = p
        except ValueError:
            continue

    candidates: list[ManifestationCandidate] = []
    for year in range(reference_year, reference_year + horizon_years + 1):
        pillar = by_year.get(year)
        if pillar is None:
            continue
        graded = _grade_manifestation(_position_groups(pillar))
        if graded is None:
            continue
        grade, wealth_pos = graded
        candidates.append(ManifestationCandidate(
            year=str(year), ganji=pillar.ganji, grade=grade, wealth_positions=wealth_pos,
        ))
    candidates.sort(key=lambda c: (_GRADE_ORDER[c.grade], int(c.year)))
    candidates = candidates[:_MAX_CANDIDATES]

    prep_years: list[PreparationYear] = []
    for cand in candidates:
        target = int(cand.year)
        for offset, weight in ((1, 1.0), (2, _Y2_WEIGHT)):
            pillar = by_year.get(target - offset)
            if pillar is None:
                continue
            graded_prep = _grade_preparation(_position_groups(pillar))
            if graded_prep is None:
                continue
            strength, signals, resource_support = graded_prep
            prep_years.append(PreparationYear(
                year=str(target - offset), ganji=pillar.ganji, target_year=cand.year,
                weight=weight, signals=signals, strength=strength,
                resource_support=resource_support,
            ))

    cand_years = {c.year for c in candidates}
    prep_year_set = {p.year for p in prep_years}
    ref = str(reference_year)
    if ref in cand_years:
        role = "manifestation"
    elif ref in prep_year_set:
        role = "preparation"
    else:
        role = "none"

    return PreparationContext(
        is_detected=bool(candidates),
        manifestation_candidates=candidates,
        preparation_years=prep_years,
        current_year_role=role,
    )

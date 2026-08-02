"""경계 명식 역할 후보 투영 비교 — measurement-only (CAL-ROLE-BORDERLINE-01a, 2026-08-02).

**어느 역할표가 맞는지 판정하지 않는다.** 이 감사의 결과는 역할 정답이 아니라 **역할
불확실성의 영향도**다.

P2-1 profile 과 P2-2 evaluation 은 **한 번만** 계산하고 P2-3 만 두 번 실행한다. 후보별로
프로필이나 등급을 다시 계산하면 역할 선택이 작동성 평가에 역으로 침투한다.

    후보 간 동일해야 함   profile · evaluation · RootDepth · operability anchor
    달라질 수 있음        canonical role · target activation axis · projection reason

production schema·callsite 는 변경하지 않는다. `SOURCE_FIXTURE` 를 production wrapper 에
넣지 않고 감사 하네스에서 명시적 후보 역할표로 투영한다.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

from saju_api.services.manse_service import calculate
from saju_engines.element_operability_shadow import build_operability_shadow_bundle
from saju_engines.event_scoring import favorability_map
from saju_engines.relation_state_chain import (
    assemble_relation_state_chain,
    relation_nodes_from_branches,
)
from saju_engines.role_activation_projection import (
    CanonicalRole,
    CanonicalRoleBasis,
    project_role_activation,
)
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.birth_input import BirthInput

#: 사례 A — 0A 에서 고정한 두 후보. pattern 후보는 출처 해석에 가깝다(정답 판정 아님).
CASE_A = (1987, 8, 5, "21:00", "male")
ENGINE_ROLE_MAP = {
    "土": CanonicalRole.YONG, "金": CanonicalRole.HUI, "木": CanonicalRole.GI,
    "火": CanonicalRole.GU, "水": CanonicalRole.HAN,
}
PATTERN_ROLE_MAP = {
    "水": CanonicalRole.YONG, "金": CanonicalRole.HUI, "土": CanonicalRole.GI,
    "火": CanonicalRole.GU, "木": CanonicalRole.HAN,
}

#: census 모집단 — 기존 회귀 fixture 의 고유 명식. 실제 사용자 비율이 아니다.
CENSUS_BIRTHS = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)
REFERENCE_DATES = (date(2024, 6, 15), date(2026, 7, 27), date(2031, 3, 1))

_FAVORABLE = frozenset({CanonicalRole.YONG, CanonicalRole.HUI})
_ADVERSE = frozenset({CanonicalRole.GI, CanonicalRole.GU})
_ROLE_BY_KOREAN = {
    "용신": CanonicalRole.YONG, "희신": CanonicalRole.HUI, "기신": CanonicalRole.GI,
    "구신": CanonicalRole.GU, "한신": CanonicalRole.HAN,
}


class DifferenceKind(StrEnum):
    ROLE_EQUIVALENT = "role_equivalent"
    SAME_POLARITY_ROLE_CHANGE = "same_polarity_role_change"
    FAVORABLE_NEUTRAL_SHIFT = "favorable_neutral_shift"
    ADVERSE_NEUTRAL_SHIFT = "adverse_neutral_shift"
    FAVORABLE_ADVERSE_FLIP = "favorable_adverse_flip"
    UNKNOWN_ROLE_COMPARISON = "unknown_role_comparison"


class PeriodSignature(StrEnum):
    PROJECTION_EQUIVALENT = "projection_equivalent"
    NEUTRAL_RECLASSIFICATION_ONLY = "neutral_reclassification_only"
    POLARITY_FLIP_PRESENT = "polarity_flip_present"
    UNKNOWN_COMPARISON = "unknown_comparison"


class Materiality(StrEnum):
    IMMATERIAL = "IMMATERIAL"
    NARRATIVE_ONLY = "NARRATIVE_ONLY"
    MATERIAL_AXIS_DIVERGENCE = "MATERIAL_AXIS_DIVERGENCE"
    PERVASIVE_AXIS_DIVERGENCE = "PERVASIVE_AXIS_DIVERGENCE"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class RoleProjectionDifference:
    chart_key: str
    period_key: str
    target_node_id: str
    element: str | None
    primary_role: str
    alternate_role: str
    operability_status: str
    activation_level: str
    difference_kind: str


def classify(primary: CanonicalRole, alternate: CanonicalRole) -> DifferenceKind:
    """역할 family 전환과 polarity 반전을 구분한다."""
    if primary is alternate:
        return DifferenceKind.ROLE_EQUIVALENT
    p_fav, a_fav = primary in _FAVORABLE, alternate in _FAVORABLE
    p_adv, a_adv = primary in _ADVERSE, alternate in _ADVERSE
    if (p_fav and a_fav) or (p_adv and a_adv):
        return DifferenceKind.SAME_POLARITY_ROLE_CHANGE
    if (p_fav and a_adv) or (p_adv and a_fav):
        return DifferenceKind.FAVORABLE_ADVERSE_FLIP
    if p_fav or a_fav:
        return DifferenceKind.FAVORABLE_NEUTRAL_SHIFT
    return DifferenceKind.ADVERSE_NEUTRAL_SHIFT


def _bundle_for(birth: BirthInput, ref: date) -> tuple[Any, dict[str, str]]:
    """P2-1·P2-2 를 **한 번만** 계산한다."""
    result = calculate(birth)
    cycles = result.luck_cycles
    daewoon = cycles.daewoon_table[cycles.current_daewoon_index].ganji
    stem, branch = year_ganzi(ref.year)
    sewoon = f"{stem.value}{branch.value}"
    roles = favorability_map(result)
    pillars = result.pillars
    natal = [(p, getattr(pillars, p).branch) for p in ("year", "month", "day", "hour")]

    def call(luck_branches: Any = None) -> Any:
        return resolve_branch_hap(
            pillars, favorability=roles, luck_branches=list(luck_branches or []))

    chain = assemble_relation_state_chain(
        natal_nodes=relation_nodes_from_branches(layer="natal", branches=natal),
        daewoon_nodes=relation_nodes_from_branches(
            layer="daewoon", branches=[("", daewoon[1])]),
        sewoon_nodes=relation_nodes_from_branches(
            layer="sewoon", branches=[("", sewoon[1])]),
        resolve_branch_hap=call,
        period_keys={"natal": "natal", "daewoon": daewoon, "sewoon": str(ref.year)},
    )
    bundle = build_operability_shadow_bundle(
        chain=chain, luck_stems={"daewoon": daewoon[0], "sewoon": sewoon[0]},
        roles_by_element={
            e: _ROLE_BY_KOREAN[label] for e, label in roles.items()
            if label in _ROLE_BY_KOREAN},
        role_basis=CanonicalRoleBasis.ENGINE_NATIVE,
        pillar_branches={("daewoon", ""): daewoon[1], ("sewoon", ""): sewoon[1]},
    )
    return bundle, {"daewoon": daewoon, "sewoon": sewoon}


def _case_a() -> dict[str, Any]:
    y, m, d, hhmm, gender = CASE_A
    diffs: list[RoleProjectionDifference] = []
    signatures: Counter[str] = Counter()
    invariant_breaks = 0

    for ref in REFERENCE_DATES:
        bundle, ganji = _bundle_for(
            BirthInput(birth_date=date(y, m, d), birth_time=hhmm,
                       birth_place_name="서울", gender=gender, reference_date=ref), ref)
        period_kinds: list[str] = []
        for target in bundle.targets:
            element = target.resolved_element
            if element is None:
                period_kinds.append(DifferenceKind.UNKNOWN_ROLE_COMPARISON.value)
                continue
            primary = ENGINE_ROLE_MAP.get(element, CanonicalRole.HAN)
            alternate = PATTERN_ROLE_MAP.get(element, CanonicalRole.HAN)
            # P2-3 만 두 번 — evaluation 은 재사용한다.
            p = project_role_activation(
                node_id=target.node_id, canonical_role=primary,
                role_basis=CanonicalRoleBasis.ENGINE_NATIVE,
                evaluation=target.evaluation)
            a = project_role_activation(
                node_id=target.node_id, canonical_role=alternate,
                role_basis=CanonicalRoleBasis.SOURCE_FIXTURE,
                evaluation=target.evaluation)
            if (p.operability_status is not a.operability_status
                    or p.operability_anchor != a.operability_anchor):
                invariant_breaks += 1
            kind = classify(primary, alternate)
            period_kinds.append(kind.value)
            if kind is not DifferenceKind.ROLE_EQUIVALENT:
                diffs.append(RoleProjectionDifference(
                    chart_key="丁卯丁未丙戌戊戌", period_key=str(ref.year),
                    target_node_id=target.node_id, element=element,
                    primary_role=primary.value, alternate_role=alternate.value,
                    operability_status=target.evaluation.status.value,
                    activation_level=p.favorable_activation.level.value
                    if primary in _FAVORABLE else (
                        p.adverse_activation.level.value if primary in _ADVERSE
                        else p.neutral_activation.level.value),
                    difference_kind=kind.value))
        if DifferenceKind.FAVORABLE_ADVERSE_FLIP.value in period_kinds:
            signatures[PeriodSignature.POLARITY_FLIP_PRESENT.value] += 1
        elif DifferenceKind.UNKNOWN_ROLE_COMPARISON.value in period_kinds:
            signatures[PeriodSignature.UNKNOWN_COMPARISON.value] += 1
        elif any(k in period_kinds for k in (
                DifferenceKind.FAVORABLE_NEUTRAL_SHIFT.value,
                DifferenceKind.ADVERSE_NEUTRAL_SHIFT.value)):
            signatures[PeriodSignature.NEUTRAL_RECLASSIFICATION_ONLY.value] += 1
        else:
            signatures[PeriodSignature.PROJECTION_EQUIVALENT.value] += 1

    flips = sum(1 for d in diffs
                if d.difference_kind == DifferenceKind.FAVORABLE_ADVERSE_FLIP.value)
    if invariant_breaks:
        materiality = Materiality.INDETERMINATE
    elif flips == 0:
        materiality = (Materiality.NARRATIVE_ONLY if diffs
                       else Materiality.IMMATERIAL)
    elif signatures[PeriodSignature.POLARITY_FLIP_PRESENT.value] > 1:
        materiality = Materiality.PERVASIVE_AXIS_DIVERGENCE
    else:
        materiality = Materiality.MATERIAL_AXIS_DIVERGENCE

    return {
        "periods": len(REFERENCE_DATES),
        "targets": len(REFERENCE_DATES) * 4,
        "differences": len(diffs),
        "kind_counts": dict(sorted(Counter(d.difference_kind for d in diffs).items())),
        "flip_by_operability": dict(sorted(Counter(
            d.operability_status for d in diffs
            if d.difference_kind == DifferenceKind.FAVORABLE_ADVERSE_FLIP.value
        ).items())),
        "period_signatures": dict(sorted(signatures.items())),
        "invariant_breaks": invariant_breaks,
        "materiality": materiality.value,
        "role_transitions": dict(sorted(Counter(
            f"{d.primary_role}->{d.alternate_role}" for d in diffs).items())),
    }


def _census() -> dict[str, Any]:
    """existing-fixture borderline census — **실제 사용자 비율이 아니다.**"""
    charts: dict[str, dict[str, Any]] = {}
    for y, m, d, hhmm in CENSUS_BIRTHS:
        for gender in ("male", "female"):
            result = calculate(BirthInput(
                birth_date=date(y, m, d), birth_time=hhmm, birth_place_name="서울",
                gender=gender, reference_date=REFERENCE_DATES[1]))
            p = result.pillars
            key = f"{p.year.ganji}{p.month.ganji}{p.day.ganji}{p.hour.ganji}|{gender}"
            ya = result.yongsin_analysis
            axes = sorted(
                ((a.get("axis") if isinstance(a, dict) else getattr(a, "axis", None),
                  a.get("score") if isinstance(a, dict) else getattr(a, "score", 0.0))
                 for a in (ya.axes or [])),
                key=lambda kv: -(kv[1] or 0.0))
            margin = (axes[0][1] - axes[1][1]) if len(axes) >= 2 else None
            charts[key] = {
                "requires_validation": bool(
                    getattr(ya, "requires_validation", False)),
                "top_axis": axes[0][0] if axes else None,
                "margin": round(margin, 4) if margin is not None else None,
                "distinct_candidate_elements": len({
                    (c.get("yongsin") if isinstance(c, dict)
                     else getattr(c, "yongsin", None))
                    for c in (ya.candidate_models or [])
                }),
            }
    borderline = [v for v in charts.values() if v["requires_validation"]]
    multi = [v for v in charts.values() if v["distinct_candidate_elements"] > 1]
    return {
        "cohort": "existing-fixture borderline census",
        "unique_charts": len(charts),
        "requires_validation": len(borderline),
        "multiple_candidate_elements": len(multi),
        "margin_below_0_02": sum(
            1 for v in charts.values()
            if v["margin"] is not None and v["margin"] < 0.02),
        "top_axis_counts": dict(sorted(
            Counter(v["top_axis"] for v in charts.values()).items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "case_a": _case_a(),
        "census": _census(),
    }
    (args.out / "role_borderline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

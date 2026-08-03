"""대안 역할표의 P2 하류 영향 감사 — MC-D (CAL-ROLE-MARGIN-CENSUS, 2026-08-03).

MC-B 에서 "역할표가 달라지는가" 가 13/13 항상 참이라 판별력이 없음을 확인했다. 그래서
**대안이 P2 작동성 계층에서 실제로 다른 결론을 내는가**를 본다.

near-tie 3건만 보면 안 된다 — 그러면 또 near-tie 안에서만 참인 성질을 판별자로 착각한다.
13 independent charts 전체를 대조군으로 돌린다.

    primary   production 이 고른 오행으로 실현 → 역할표 → P2
    alternate runner-up 오행을 강제해 실현 → 역할표 → P2

두 실행은 각각 fresh capture 에서 시작하고, primary 산출물이 alternate 입력에 들어가지
않는다(01c1-b0 계약).

**역할표는 chain 조립에도 들어간다.** `resolve_branch_hap(favorability=...)` 가 역할을
받으므로 alternate 실행은 chain 부터 다시 만든다. 역할표만 바꿔 P2 만 다시 돌리면 상류
차이를 통째로 놓친다.

비교는 세 단계다.

    P2_EFFECT_IDENTICAL          유효 출력이 전부 같다
    P2_NUMERIC_DIVERGENCE_ONLY   수치만 다르고 범주·판정·축 선택은 같다
    P2_DECISION_DIVERGENCE       등급·활성 축·역할 분류 중 하나라도 달라진다

사용법:
    python scripts/audits/measure_p2_downstream_effect.py --out var/audit/p2_downstream
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1]
for _path in (_BACKEND / "apps/api", _BACKEND / "packages", _HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from saju_manse_analysis.relations.hap_modes import resolve_branch_hap  # noqa: E402
from saju_manse_analysis.yongsin import candidates as cand_mod  # noqa: E402
from saju_manse_analysis.yongsin.role_realization import (  # noqa: E402
    RealizedRoleMap,
    resolve_realized_roles,
)

from saju_api.services import manse_service  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines.element_operability_shadow import (  # noqa: E402
    OperabilityShadowError,
    build_operability_shadow_bundle,
)
from saju_engines.relation_state_chain import (  # noqa: E402
    RelationStateAssemblyError,
    relation_nodes_from_branches,
)
from saju_engines.relation_state_chain import (  # noqa: E402
    assemble_relation_state_chain as _assemble,
)
from saju_engines.role_activation_projection import (  # noqa: E402
    CanonicalRole,
    CanonicalRoleBasis,
)
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402

#: MC-A 기준 코호트(baseline cohort). 성별은 결과를 바꾸지 않아 하나만 쓴다.
BASELINE_CHARTS: tuple[tuple[int, int, int, str], ...] = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)
REFERENCE_DATE = date(2026, 7, 27)

#: legacy operational cutoff. **대안 보존 판별자로 쓰지 않는다**(MC-A: 밀도 근거 없음).
LEGACY_NEAR_TIE_CUTOFF = Decimal("0.02")

_ROLE_KO = {
    "yongsin": "용신", "heesin": "희신", "gisin": "기신",
    "gusin": "구신", "hansin": "한신",
}
_ROLE_BY_KOREAN = {
    "용신": CanonicalRole.YONG, "희신": CanonicalRole.HUI, "기신": CanonicalRole.GI,
    "구신": CanonicalRole.GU, "한신": CanonicalRole.HAN,
}
#: 축 분류 — 판정 차이를 보는 단위. 용·희 / 기·구 / 한.
_ROLE_CLASS = {
    CanonicalRole.YONG: "favorable", CanonicalRole.HUI: "favorable",
    CanonicalRole.GI: "adverse", CanonicalRole.GU: "adverse",
    CanonicalRole.HAN: "neutral",
}


class Ineligible(Exception):
    """대조 실행 불가. 버리지 않고 사유별로 집계한다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _birth(year: int, month: int, day: int, hhmm: str) -> BirthInput:
    return BirthInput(
        birth_date=date(year, month, day), birth_time=hhmm,
        birth_place_name="서울", gender="male", reference_date=REFERENCE_DATE,
    )


def _fresh_capture(birth: BirthInput) -> tuple[Any, dict[str, Any]]:
    """production 을 새로 돌려 실현 경계 입력을 포획한다."""
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    original = cand_mod.resolve_realized_roles
    cand_mod.resolve_realized_roles = _spy
    try:
        manse_service._cache.clear()
        result = calculate(birth)
        manse_service._cache.clear()
    finally:
        cand_mod.resolve_realized_roles = original
    if result.pillars is None:
        raise Ineligible("UNSUPPORTED_INPUT")
    return result, captured


def _luck_ganji(result: Any) -> tuple[str, str]:
    cycles = getattr(result, "luck_cycles", None)
    if cycles is None or not getattr(cycles, "daewoon_table", None):
        raise Ineligible("MISSING_DAEWOON")
    index = getattr(cycles, "current_daewoon_index", None)
    if index is None or index < 0 or index >= len(cycles.daewoon_table):
        raise Ineligible("MISSING_DAEWOON")
    daewoon = cycles.daewoon_table[index].ganji
    stem, branch = year_ganzi(REFERENCE_DATE.year)
    sewoon = f"{stem.value}{branch.value}"
    if len(daewoon) < 2 or len(sewoon) < 2:
        raise Ineligible("MISSING_SEWOON")
    return daewoon, sewoon


def _korean_favorability(role_map: RealizedRoleMap) -> dict[str, str]:
    """역할표 → 오행→한글 역할. chain 조립과 P2 조회가 함께 쓴다."""
    out: dict[str, str] = {}
    for key, korean in _ROLE_KO.items():
        element = getattr(role_map, key)
        if element:
            out[element] = korean
    return out


def _p2_targets(result: Any, role_map: RealizedRoleMap) -> list[dict[str, Any]]:
    """이 역할표로 chain·P2 를 끝까지 돌려 target 별 산출을 뽑는다."""
    favorability = _korean_favorability(role_map)
    roles_by_element = {
        element: _ROLE_BY_KOREAN[label] for element, label in favorability.items()
    }
    daewoon, sewoon = _luck_ganji(result)
    pillars = result.pillars
    natal = [
        (position, getattr(pillars, position).branch)
        for position in ("year", "month", "day", "hour")
    ]

    def call(luck_branches: Any = None) -> Any:
        return resolve_branch_hap(
            pillars, favorability=favorability,
            luck_branches=list(luck_branches or []))

    try:
        chain = _assemble(
            natal_nodes=relation_nodes_from_branches(layer="natal", branches=natal),
            daewoon_nodes=relation_nodes_from_branches(
                layer="daewoon", branches=[("", daewoon[1])]),
            sewoon_nodes=relation_nodes_from_branches(
                layer="sewoon", branches=[("", sewoon[1])]),
            resolve_branch_hap=call,
            period_keys={
                "natal": "natal", "daewoon": daewoon,
                "sewoon": str(REFERENCE_DATE.year),
            },
        )
    except RelationStateAssemblyError as exc:
        raise Ineligible(f"CHAIN_BUILD_FAILURE:{exc.kind.value}") from exc

    try:
        bundle = build_operability_shadow_bundle(
            chain=chain, luck_stems={"daewoon": daewoon[0], "sewoon": sewoon[0]},
            roles_by_element=roles_by_element,
            role_basis=CanonicalRoleBasis.ENGINE_NATIVE,
            pillar_branches={("daewoon", ""): daewoon[1], ("sewoon", ""): sewoon[1]},
        )
    except OperabilityShadowError as exc:
        raise Ineligible(f"TARGET_BINDING_FAILURE:{exc.kind.value}") from exc

    rows: list[dict[str, Any]] = []
    for target in bundle.targets:
        projection = target.role_projection
        rows.append({
            "node_id": target.node_id,
            "resolved_element": target.resolved_element,
            "status": target.evaluation.status.value,
            "matched_rule_id": target.evaluation.matched_rule_id,
            "anchor": target.evaluation.anchor,
            "canonical_role": projection.canonical_role.value,
            "role_class": _ROLE_CLASS[projection.canonical_role],
            "favorable": projection.favorable_activation.level.value,
            "adverse": projection.adverse_activation.level.value,
            "mitigation": projection.mitigation.level.value,
            "neutral": projection.neutral_activation.level.value,
            "structural_tension": projection.structural_tension.level.value,
        })
    return rows


def _decision_view(row: dict[str, Any]) -> tuple:
    """결정 수준 — 수치(anchor)는 제외한다."""
    return (
        row["node_id"], row["status"], row["role_class"], row["canonical_role"],
        row["favorable"], row["adverse"], row["mitigation"],
        row["neutral"], row["structural_tension"],
    )


def _numeric_view(row: dict[str, Any]) -> tuple:
    return (row["node_id"], row["anchor"], row["matched_rule_id"])


def _classify(primary: list[dict], alternate: list[dict]) -> str:
    p_dec = [_decision_view(r) for r in primary]
    a_dec = [_decision_view(r) for r in alternate]
    if p_dec != a_dec:
        return "P2_DECISION_DIVERGENCE"
    if [_numeric_view(r) for r in primary] != [_numeric_view(r) for r in alternate]:
        return "P2_NUMERIC_DIVERGENCE_ONLY"
    return "P2_EFFECT_IDENTICAL"


def _row(chart: tuple[int, int, int, str]) -> dict[str, Any]:
    birth = _birth(*chart)
    result, captured = _fresh_capture(birth)
    analysis = result.yongsin_analysis
    candidates = list(analysis.useful_candidates)
    if len(candidates) < 2:
        raise Ineligible("SINGLE_CANDIDATE")

    raw_scores = captured["useful_scores"]
    margin = (
        Decimal(repr(raw_scores[candidates[0].element][0]))
        - Decimal(repr(raw_scores[candidates[1].element][0]))
    )
    primary = resolve_realized_roles(**captured).result

    _, second = _fresh_capture(birth)
    alternate = resolve_realized_roles(**{
        **second, "selected_yongsin_element": candidates[1].element,
    }).result

    primary_targets = _p2_targets(result, primary.final_role_map)
    alternate_targets = _p2_targets(result, alternate.final_role_map)
    divergence = _classify(primary_targets, alternate_targets)

    changed = [
        p["node_id"] for p, a in zip(primary_targets, alternate_targets, strict=True)
        if _decision_view(p) != _decision_view(a)
    ]
    class_changed = [
        p["node_id"] for p, a in zip(primary_targets, alternate_targets, strict=True)
        if p["role_class"] != a["role_class"]
    ]
    return {
        "chart": f"{chart[0]}-{chart[1]:02d}-{chart[2]:02d} {chart[3]}",
        "raw_margin": str(margin),
        "near_tie_legacy": margin <= LEGACY_NEAR_TIE_CUTOFF,
        "primary_element": candidates[0].element,
        "alternate_element": candidates[1].element,
        "primary_model": candidates[0].model,
        "alternate_model": candidates[1].model,
        "primary_origin": primary.realization_origin.value,
        "alternate_origin": alternate.realization_origin.value,
        "completeness_pair": (
            f"{'complete' if primary.model_complete else 'fallback'}/"
            f"{'complete' if alternate.model_complete else 'fallback'}"
        ),
        "target_count": len(primary_targets),
        "divergence": divergence,
        "decision_changed_nodes": changed,
        "role_class_changed_nodes": class_changed,
        "statuses_identical": (
            [r["status"] for r in primary_targets]
            == [r["status"] for r in alternate_targets]
        ),
        "primary_targets": primary_targets,
        "alternate_targets": alternate_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    ineligible: Counter[str] = Counter()
    for chart in BASELINE_CHARTS:
        try:
            rows.append(_row(chart))
        except Ineligible as exc:
            ineligible[exc.reason] += 1

    near = [r for r in rows if r["near_tie_legacy"]]
    wide = [r for r in rows if not r["near_tie_legacy"]]
    decision = [r for r in rows if r["divergence"] == "P2_DECISION_DIVERGENCE"]
    summary: dict[str, Any] = {
        "verdict": "P2_EFFECT_DISTRIBUTION_MEASURED",
        "cohort": "baseline",
        "charts": len(BASELINE_CHARTS),
        "measured": len(rows),
        "ineligible": dict(ineligible),
        "divergence_distribution": dict(Counter(r["divergence"] for r in rows)),
        "decision_divergence": {
            "total": f"{len(decision)}/{len(rows)}",
            "near_tie": f"{sum(1 for r in near if r in decision)}/{len(near)}",
            "wide_margin": f"{sum(1 for r in wide if r in decision)}/{len(wide)}",
        },
        "statuses_identical_everywhere": all(r["statuses_identical"] for r in rows),
        "completeness_pairs": dict(Counter(r["completeness_pair"] for r in rows)),
        "by_chart": [
            {
                "chart": r["chart"], "raw_margin": r["raw_margin"],
                "near_tie": r["near_tie_legacy"], "divergence": r["divergence"],
                "targets": r["target_count"],
                "decision_changed": len(r["decision_changed_nodes"]),
                "role_class_changed": len(r["role_class_changed_nodes"]),
                "completeness": r["completeness_pair"],
            }
            for r in sorted(rows, key=lambda x: Decimal(x["raw_margin"]))
        ],
    }

    (args.out / "rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

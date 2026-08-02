"""오행 실현도 첫 shadow 분포 측정 (P2 감사, 2026-08-01).

세 코호트를 **분리해서** 재는 것이 이 스크립트의 요지다.

    A 생산 비회귀   기존 회귀 스위트 전체를 R0~R3 플래그 조합으로 실행
                    중복 입력을 제거하지 않는다 — 목적이 분포가 아니라 불변 확인이다
    B 분포          A 에서 canonical key 로 중복 제거한 적격 입력만
                    이것만 백분율의 모집단이 된다
    C 의미론 골든   규칙이 의도대로 작동하는지 확인. **분포 비율에 넣지 않는다**

기존 fixture 는 경계·회귀 사례가 과대표집돼 있어 서비스 사용자 분포가 아니다. 보고서에는
`existing-fixture shadow distribution` 으로만 적는다.

    python scripts/audits/measure_luck_element_operability_shadow.py --out <dir>
    python scripts/audits/measure_luck_element_operability_shadow.py --out <dir> --with-suite
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

from saju_api.services.manse_service import calculate
from saju_engines.element_operability_grade import OPERABILITY_ANCHOR
from saju_engines.element_operability_shadow import (
    OperabilityShadowError,
    build_operability_shadow_bundle,
)
from saju_engines.event_scoring import favorability_map
from saju_engines.relation_state_chain import (
    RelationStateAssemblyError,
    relation_nodes_from_branches,
)
from saju_engines.relation_state_chain import (
    assemble_relation_state_chain as _assemble,
)
from saju_engines.role_activation_projection import CanonicalRole, CanonicalRoleBasis
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.birth_input import BirthInput

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _activation_resolution_candidates import (  # noqa: E402
    ACTIVATION_RESOLUTION_CANDIDATES_V1,
)
from _activation_resolution_candidates import summarize as _activation_summary  # noqa: E402
from _operability_ablations import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    KNOWN_ABLATIONS,
    ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1,
    apply_root_depth_ablation,
    derive_root_depth_for_audit,
)

#: 기존 회귀 픽스처에서 수집한 고유 명식(생년월일·시각). 무작위 생성은 넣지 않는다.
FIXTURE_BIRTHS: tuple[tuple[int, int, int, str], ...] = (
    (1980, 11, 22, "09:08"), (1980, 11, 22, "09:40"), (1985, 3, 5, "12:00"),
    (1985, 3, 15, "14:30"), (1985, 4, 18, "16:00"), (1985, 5, 5, "14:00"),
    (1987, 8, 5, "21:00"), (1988, 3, 5, "10:30"), (1990, 3, 3, "10:00"),
    (1990, 3, 15, "10:00"), (1990, 5, 5, "13:30"), (1990, 5, 15, "09:30"),
    (1992, 7, 20, "14:00"),
)

#: 기준일 — 서로 다른 대운·세운 조합을 만들되 임의 확장하지 않는다.
FIXTURE_REFERENCE_DATES: tuple[date, ...] = (
    date(2024, 6, 15), date(2026, 7, 27), date(2031, 3, 1),
)

GENDERS: tuple[str, ...] = ("male", "female")

#: R0~R3 플래그 조합. 각 실행은 subprocess 에 env 를 명시 주입한다 — 현재 셸을 오염시키지 않는다.
RUN_MATRIX: dict[str, dict[str, str]] = {
    "R0": {"graph": "false", "state": "false", "operability": "false"},
    "R1": {"graph": "false", "state": "true", "operability": "false"},
    "R2": {"graph": "false", "state": "false", "operability": "true"},
    "R3": {"graph": "true", "state": "true", "operability": "true"},
}

_ENV_NAMES = {
    "graph": "SAJU_LUCK_RELATION_GRAPH_SHADOW_ENABLED",
    "state": "SAJU_LUCK_RELATION_STATE_SHADOW_ENABLED",
    "operability": "SAJU_LUCK_ELEMENT_OPERABILITY_SHADOW_ENABLED",
}

_ROLE_BY_KOREAN = {
    "용신": CanonicalRole.YONG, "희신": CanonicalRole.HUI, "기신": CanonicalRole.GI,
    "구신": CanonicalRole.GU, "한신": CanonicalRole.HAN,
}


class Ineligible(Exception):
    """분포 코호트 적격 조건 미충족. **버리지 않고 사유별로 집계한다.**"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _birth(y: int, m: int, d: int, hhmm: str, gender: str, ref: date) -> BirthInput:
    return BirthInput(
        birth_date=date(y, m, d), birth_time=hhmm, birth_place_name="서울",
        gender=gender, reference_date=ref,
    )


def _luck_ganji(result: Any, ref: date) -> tuple[str, str]:
    """(대운 간지, 세운 간지). 세운은 입춘 경계를 쓰는 엔진 함수로 구한다."""
    cycles = getattr(result, "luck_cycles", None)
    if cycles is None or not getattr(cycles, "daewoon_table", None):
        raise Ineligible("MISSING_DAEWOON")
    index = getattr(cycles, "current_daewoon_index", None)
    if index is None or index < 0 or index >= len(cycles.daewoon_table):
        raise Ineligible("MISSING_DAEWOON")
    daewoon = cycles.daewoon_table[index].ganji
    stem, branch = year_ganzi(ref.year)
    sewoon = f"{stem.value}{branch.value}"
    if len(daewoon) < 2 or len(sewoon) < 2:
        raise Ineligible("MISSING_SEWOON")
    return daewoon, sewoon


def _canonical_key(result: Any, gender: str, daewoon: str, sewoon: str) -> str:
    p = result.pillars
    return "|".join((
        p.year.ganji, p.month.ganji, p.day.ganji, p.hour.ganji,
        daewoon, sewoon, gender, "engine_native",
    ))


def _measure_one(
    birth: BirthInput, ref: date, ablation: str | None = None,
) -> dict[str, Any]:
    """입력 하나의 shadow 결과. 순수 계산이라 플래그와 무관하다."""
    result = calculate(birth)
    if result.pillars is None:
        raise Ineligible("UNSUPPORTED_INPUT")
    daewoon, sewoon = _luck_ganji(result, ref)

    roles = favorability_map(result)
    if not roles:
        raise Ineligible("ROLE_CONTEXT_UNAVAILABLE")
    roles_by_element = {
        element: _ROLE_BY_KOREAN[label] for element, label in roles.items()
        if label in _ROLE_BY_KOREAN
    }

    pillars = result.pillars
    natal = [(pos, getattr(pillars, pos).branch) for pos in
             ("year", "month", "day", "hour")]

    def call(luck_branches: Any = None) -> Any:
        return resolve_branch_hap(
            pillars, favorability=roles, luck_branches=list(luck_branches or []))

    try:
        chain = _assemble(
            natal_nodes=relation_nodes_from_branches(layer="natal", branches=natal),
            daewoon_nodes=relation_nodes_from_branches(
                layer="daewoon", branches=[("", daewoon[1])]),
            sewoon_nodes=relation_nodes_from_branches(
                layer="sewoon", branches=[("", sewoon[1])]),
            resolve_branch_hap=call,
            period_keys={"natal": "natal", "daewoon": daewoon, "sewoon": str(ref.year)},
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

    return {
        "canonical_key": _canonical_key(result, birth.gender, daewoon, sewoon),
        "reference_year": ref.year,
        "chain_frames": len(chain.frames),
        "chain_metrics": chain.aggregate_metrics(),
        "unresolved_relations": len(
            chain.terminal_frame.snapshot.unresolved_relation_ids),
        "targets": [
            _paired(t, _target_row(t))
            if ablation == ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1 else _target_row(t)
            for t in bundle.targets
        ],
        "build_duration_ms": round(bundle.build_metrics.build_duration_ms, 3),
    }


def _paired(target: Any, row: dict[str, Any]) -> dict[str, Any]:
    """같은 target 의 baseline·candidate 를 한 행에 담는다.

    별도 실행 두 번으로 만들면 모집단·정렬 차이가 결과 이동으로 오인된다.
    """
    depth = derive_root_depth_for_audit(target.profile)
    status, reason = apply_root_depth_ablation(
        status=target.evaluation.status, has_main_qi_root=depth.has_main_qi_root)
    projection = target.role_projection
    row.update({
        "natal_root_depth": depth.natal_root_depth.value,
        "transit_root_depth": depth.transit_root_depth.value,
        "strongest_root_depth": depth.strongest_root_depth.value,
        "has_main_qi_root": depth.has_main_qi_root,
        "baseline_status": target.evaluation.status.value,
        "candidate_status": status.value,
        "baseline_anchor": target.evaluation.anchor,
        "candidate_anchor": OPERABILITY_ANCHOR[status],
        "ablation_reason": reason.value,
        # 활성도는 overlay 로 바꾸지 않는다 — P2-3 매핑을 함께 바꾸면 원인이 섞인다.
        "baseline_favorable": projection.favorable_activation.level.value,
        "baseline_adverse": projection.adverse_activation.level.value,
        "baseline_neutral": projection.neutral_activation.level.value,
        "baseline_tension": projection.structural_tension.level.value,
        "candidate_activation_level": _ACTIVATION_BY_STATUS[status.value],
        "baseline_activation_level": _ACTIVATION_BY_STATUS[
            target.evaluation.status.value],
    })
    return row


#: P2-3 의 실현도 → 활성도 매핑. **여기서 바꾸지 않는다** — 후보 정책이 활성도까지
#: 움직이는지 보려면 기존 매핑을 그대로 적용해야 한다.
_ACTIVATION_BY_STATUS = {
    "fully_operable": "high", "operable": "high",
    "partially_operable": "moderate", "weakened": "low",
    "suppressed": "low", "unknown": "unknown",
}


def _target_row(target: Any) -> dict[str, Any]:
    profile, evaluation, projection = (
        target.profile, target.evaluation, target.role_projection)
    return {
        "layer": target.layer, "component": target.component,
        "raw_element": target.raw_element,
        "resolved_element": target.resolved_element,
        "root_status": profile.root.status.value,
        "support_status": profile.support.status.value,
        "cut_off_status": profile.obstruction.cut_off.value,
        "stage_applicability": profile.stage.applicability.value,
        "stage": profile.stage.stage,
        "operability_status": evaluation.status.value,
        "matched_rule_id": evaluation.matched_rule_id,
        "canonical_role": projection.canonical_role.value,
        "favorable": projection.favorable_activation.level.value,
        "adverse": projection.adverse_activation.level.value,
        "neutral": projection.neutral_activation.level.value,
        "tension": projection.structural_tension.level.value,
        "baseline_anchor": evaluation.anchor,
        "reason_codes": list(evaluation.reason_codes),
        "disruption_evidence": len(profile.evidence_ids),
    }


def _invariant_violations(rows: list[dict[str, Any]]) -> Counter[str]:
    """의미론 불변식 위반. **모두 0건이어야 한다.**"""
    out: Counter[str] = Counter()
    for row in rows:
        for t in row["targets"]:
            role, status = t["canonical_role"], t["operability_status"]
            if role in ("용신", "희신") and t["adverse"] != "none":
                out["FAVORABLE_ROLE_WITH_ADVERSE_ACTIVATION"] += 1
            if role == "한신" and (t["favorable"] != "none" or t["adverse"] != "none"):
                out["NEUTRAL_ROLE_WITH_DIRECTIONAL_ACTIVATION"] += 1
            if status == "unknown" and t["resolved_element"] is not None:
                out["UNKNOWN_WITH_RESOLVED_ELEMENT"] += 1
            # 관계 참여만으로 정체성이 사라졌는가 — 수정 후 0건이어야 한다.
            if t["resolved_element"] is None and t["disruption_evidence"] > 0:
                out["IDENTITY_LOST_BY_DISRUPTION_ONLY"] += 1
        if len(row["targets"]) > 4:
            out["TOO_MANY_TARGETS"] += 1
        node_ids = [f"{t['layer']}.{t['component']}" for t in row["targets"]]
        if len(node_ids) != len(set(node_ids)):
            out["DUPLICATE_TARGET"] += 1
    return out


def _run_suite_matrix(repo_root: Path) -> dict[str, dict[str, Any]]:
    """A 코호트 — 기존 스위트를 플래그 조합별로 돌린다. 생산 불변의 직접 증거다."""
    out: dict[str, dict[str, Any]] = {}
    for run_id, flags in RUN_MATRIX.items():
        env = {**os.environ, **{_ENV_NAMES[k]: v for k, v in flags.items()}}
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly"],
            cwd=repo_root / "backend", env=env, capture_output=True, text=True,
            check=False,
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        out[run_id] = {"flags": flags, "exit_code": proc.returncode, "summary": tail}
    return out


def _ablation_summary(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """baseline↔candidate 이동. **활성도 이동을 따로 센다** — 상태만 움직이고 활성도는
    그대로일 수 있고, 그렇다면 P3 입력의 변별력은 늘지 않는다."""
    transitions = Counter(
        f"{t['baseline_status']}->{t['candidate_status']}" for t in targets)
    illegal = sorted({
        k for k in transitions
        if tuple(k.split("->")) not in ALLOWED_TRANSITIONS
    })
    moved = [t for t in targets
             if t["baseline_status"] != t["candidate_status"]]
    return {
        "policy": ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1,
        "status_transitions": dict(sorted(transitions.items())),
        "illegal_transitions": illegal,
        "status_changed": len(moved),
        "activation_changed": sum(
            1 for t in targets
            if t["baseline_activation_level"] != t["candidate_activation_level"]),
        "root_depth": dict(sorted(
            Counter(t["strongest_root_depth"] for t in targets).items())),
        "moved_by_layer_component": dict(sorted(
            Counter(f"{t['layer']}.{t['component']}" for t in moved).items())),
        "moved_by_role": dict(sorted(
            Counter(t["canonical_role"] for t in moved).items())),
        "moved_by_rule": dict(sorted(
            Counter(t["matched_rule_id"] for t in moved).items())),
        "ablation_reason": dict(sorted(
            Counter(t["ablation_reason"] for t in targets).items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--ablation",
        choices=(*KNOWN_ABLATIONS, ACTIVATION_RESOLUTION_CANDIDATES_V1), default=None,
        help="이름 있는 감사 overlay. 없으면 기존 첫 shadow 측정을 그대로 재현한다.")
    parser.add_argument(
        "--with-suite", action="store_true",
        help="A 코호트(스위트 R0~R3)까지 실행 — 오래 걸린다")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[3]

    rows: list[dict[str, Any]] = []
    ineligible: Counter[str] = Counter()
    seen: set[str] = set()
    total = 0

    for y, m, d, hhmm in FIXTURE_BIRTHS:
        for gender in GENDERS:
            for ref in FIXTURE_REFERENCE_DATES:
                total += 1
                try:
                    row = _measure_one(
                        _birth(y, m, d, hhmm, gender, ref), ref, args.ablation)
                except Ineligible as exc:
                    ineligible[exc.reason] += 1
                    continue
                except Exception as exc:  # noqa: BLE001 - 감사 스크립트는 계속 진행한다
                    ineligible[f"UNEXPECTED:{type(exc).__name__}"] += 1
                    continue
                if row["canonical_key"] in seen:
                    continue
                seen.add(row["canonical_key"])
                rows.append(row)

    targets = [t for row in rows for t in row["targets"]]
    summary = {
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "cohort": "existing-fixture shadow distribution",
        "total_inputs": total,
        "unique_eligible_inputs": len(rows),
        "ineligible": dict(sorted(ineligible.items())),
        "target_count": len(targets),
        "operability_status": dict(sorted(
            Counter(t["operability_status"] for t in targets).items())),
        "matched_rule_id": dict(sorted(
            Counter(t["matched_rule_id"] for t in targets).items())),
        "root_status": dict(sorted(Counter(t["root_status"] for t in targets).items())),
        "support_status": dict(sorted(
            Counter(t["support_status"] for t in targets).items())),
        "cut_off_status": dict(sorted(
            Counter(t["cut_off_status"] for t in targets).items())),
        "stage_applicability": dict(sorted(
            Counter(t["stage_applicability"] for t in targets).items())),
        "canonical_role": dict(sorted(
            Counter(t["canonical_role"] for t in targets).items())),
        "by_layer_component": dict(sorted(Counter(
            f"{t['layer']}.{t['component']}={t['operability_status']}"
            for t in targets).items())),
        "transformed_targets": sum(
            1 for t in targets if t["raw_element"] != t["resolved_element"]),
        "invariant_violations": dict(sorted(_invariant_violations(rows).items())),
    }
    if args.ablation == ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1:
        summary["ablation"] = _ablation_summary(targets)
    if args.ablation == ACTIVATION_RESOLUTION_CANDIDATES_V1:
        summary["activation_candidates"] = _activation_summary(targets)
    if args.with_suite:
        summary["production_matrix"] = _run_suite_matrix(repo_root)

    (args.out / "distribution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with (args.out / "targets.jsonl").open("w", encoding="utf-8") as fh:
        for row in sorted(rows, key=lambda r: r["canonical_key"]):
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

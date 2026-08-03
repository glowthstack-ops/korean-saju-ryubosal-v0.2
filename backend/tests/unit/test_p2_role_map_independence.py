"""P2 실현도가 역할표에 독립인가 (CAL-ROLE-MARGIN-CENSUS / MC-D, 2026-08-03).

MC-D 는 "대안 역할표가 P2 에서 다른 결론을 내는가" 를 판별자 후보로 봤다. 결과는 13/13
`P2_DECISION_DIVERGENCE` — role-map 차이와 마찬가지로 **항상 참이라 판별력이 없다.**

이유는 구조에 있다.

    등급(OperabilityStatus)  대상 오행의 profile 로만 결정된다 — 역할과 무관
    투영(activation axis)    같은 등급을 어느 축에 올릴지만 역할이 정한다

두 역할표는 5오행을 역할에 배정하는 서로 다른 순열이므로, 운 간지 대상 중 하나는 거의
언제나 다른 역할을 받는다. 그래서 P2 산출은 자동으로 갈린다.

이 파일은 **등급의 역할 독립성**을 고정한다. 이게 깨지면 "역할이 실현도를 만든다" 는
순환이 생기고, 대안 비교의 전제(같은 등급을 다른 축에 올린 것뿐)가 무너진다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from saju_manse_analysis.relations.hap_modes import resolve_branch_hap
from saju_manse_analysis.yongsin import candidates as cand_mod
from saju_manse_analysis.yongsin.role_realization import (
    RealizedRoleMap,
    resolve_realized_roles,
)

from saju_api.services import manse_service
from saju_api.services.manse_service import calculate
from saju_engines.element_operability_shadow import build_operability_shadow_bundle
from saju_engines.relation_state_chain import (
    assemble_relation_state_chain,
    relation_nodes_from_branches,
)
from saju_engines.role_activation_projection import CanonicalRole, CanonicalRoleBasis
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_shared_types.birth_input import BirthInput

_REFERENCE = date(2026, 7, 27)

#: MC-A 기준 코호트에서 실현 경로가 갈리는 대표 4건만 쓴다 — 전건은 감사 스크립트가 돈다.
_CHARTS: tuple[tuple[int, int, int, str], ...] = (
    (1990, 5, 15, "09:30"),   # complete / complete
    (1992, 7, 20, "14:00"),   # fallback / fallback
    (1987, 8, 5, "21:00"),    # complete / fallback
    (1990, 3, 15, "10:00"),   # 역할 class 는 그대로인 사례
)

_ROLE_KO = {
    "yongsin": "용신", "heesin": "희신", "gisin": "기신",
    "gusin": "구신", "hansin": "한신",
}
_ROLE_BY_KOREAN = {
    "용신": CanonicalRole.YONG, "희신": CanonicalRole.HUI, "기신": CanonicalRole.GI,
    "구신": CanonicalRole.GU, "한신": CanonicalRole.HAN,
}


def _fresh_capture(birth: BirthInput, patcher: pytest.MonkeyPatch) -> tuple[Any, dict]:
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    patcher.setattr(cand_mod, "resolve_realized_roles", _spy)
    manse_service._cache.clear()
    result = calculate(birth)
    manse_service._cache.clear()
    return result, captured


def _p2_targets(result: Any, role_map: RealizedRoleMap) -> list[dict[str, Any]]:
    """역할표 하나로 chain·P2 를 끝까지 돌린다. 역할표는 chain 조립에도 들어간다."""
    favorability = {
        getattr(role_map, key): korean
        for key, korean in _ROLE_KO.items() if getattr(role_map, key)
    }
    cycles = result.luck_cycles
    daewoon = cycles.daewoon_table[cycles.current_daewoon_index].ganji
    stem, branch = year_ganzi(_REFERENCE.year)
    sewoon = f"{stem.value}{branch.value}"
    pillars = result.pillars
    natal = [
        (position, getattr(pillars, position).branch)
        for position in ("year", "month", "day", "hour")
    ]

    chain = assemble_relation_state_chain(
        natal_nodes=relation_nodes_from_branches(layer="natal", branches=natal),
        daewoon_nodes=relation_nodes_from_branches(
            layer="daewoon", branches=[("", daewoon[1])]),
        sewoon_nodes=relation_nodes_from_branches(
            layer="sewoon", branches=[("", sewoon[1])]),
        resolve_branch_hap=lambda luck_branches=None: resolve_branch_hap(
            pillars, favorability=favorability,
            luck_branches=list(luck_branches or [])),
        period_keys={
            "natal": "natal", "daewoon": daewoon, "sewoon": str(_REFERENCE.year)},
    )
    bundle = build_operability_shadow_bundle(
        chain=chain, luck_stems={"daewoon": daewoon[0], "sewoon": sewoon[0]},
        roles_by_element={
            element: _ROLE_BY_KOREAN[label] for element, label in favorability.items()
        },
        role_basis=CanonicalRoleBasis.ENGINE_NATIVE,
        pillar_branches={("daewoon", ""): daewoon[1], ("sewoon", ""): sewoon[1]},
    )
    return [
        {
            "node_id": t.node_id,
            "resolved_element": t.resolved_element,
            "status": t.evaluation.status.value,
            "matched_rule_id": t.evaluation.matched_rule_id,
            "anchor": t.evaluation.anchor,
            "canonical_role": t.role_projection.canonical_role.value,
        }
        for t in bundle.targets
    ]


@pytest.fixture(scope="module")
def pairs(request) -> list[dict[str, Any]]:
    """명식별 primary·alternate P2 산출. 각 실행은 fresh capture 에서 시작한다."""
    patcher = pytest.MonkeyPatch()
    request.addfinalizer(patcher.undo)

    rows: list[dict[str, Any]] = []
    for year, month, day, hhmm in _CHARTS:
        birth = BirthInput(
            birth_date=date(year, month, day), birth_time=hhmm,
            birth_place_name="서울", gender="male", reference_date=_REFERENCE,
        )
        result, captured = _fresh_capture(birth, patcher)
        candidates = result.yongsin_analysis.useful_candidates
        primary = resolve_realized_roles(**captured).result

        second_result, second = _fresh_capture(birth, patcher)
        alternate = resolve_realized_roles(**{
            **second, "selected_yongsin_element": candidates[1].element,
        }).result
        rows.append({
            "chart": f"{year}-{month:02d}-{day:02d}",
            "primary": _p2_targets(result, primary.final_role_map),
            "alternate": _p2_targets(second_result, alternate.final_role_map),
        })
    return rows


# ── 등급은 역할표에 독립이다 ─────────────────────────────────────────────


def test_operability_grade_does_not_depend_on_the_role_map(pairs) -> None:
    """등급·규칙·앵커가 두 역할표에서 같다.

    깨지면 역할이 실현도를 만드는 순환이 생기고, "같은 등급을 다른 축에 올린 것" 이라는
    대안 비교의 전제가 무너진다.
    """
    assert pairs
    for row in pairs:
        graded = [
            (t["node_id"], t["resolved_element"], t["status"],
             t["matched_rule_id"], t["anchor"])
            for t in row["primary"]
        ]
        alternate = [
            (t["node_id"], t["resolved_element"], t["status"],
             t["matched_rule_id"], t["anchor"])
            for t in row["alternate"]
        ]
        assert graded == alternate, row["chart"]


def test_only_the_projected_role_changes(pairs) -> None:
    """달라지는 것은 역할 배정뿐이다 — 대상 자리와 오행은 그대로다."""
    for row in pairs:
        assert [t["node_id"] for t in row["primary"]] == [
            t["node_id"] for t in row["alternate"]], row["chart"]
        assert [t["resolved_element"] for t in row["primary"]] == [
            t["resolved_element"] for t in row["alternate"]], row["chart"]

    changed = [
        row["chart"] for row in pairs
        if [t["canonical_role"] for t in row["primary"]]
        != [t["canonical_role"] for t in row["alternate"]]
    ]
    assert changed, "역할 배정이 하나도 안 바뀌면 대안 비교 자체가 성립하지 않는다"


def test_p2_divergence_is_not_a_discriminator(pairs) -> None:
    """전건에서 역할 배정이 갈린다 — near-tie 를 가려내는 성질이 아니다.

    감사 스크립트가 13건 전체에서 13/13 `P2_DECISION_DIVERGENCE` 를 관측했다. 여기서는
    대표 4건으로 같은 성질을 고정한다. 이 조건으로 임계값을 정당화하면 role-map 차이와
    똑같이 항상 참인 조건을 근거로 쓰게 된다.
    """
    diverging = [
        row["chart"] for row in pairs
        if [t["canonical_role"] for t in row["primary"]]
        != [t["canonical_role"] for t in row["alternate"]]
    ]
    assert len(diverging) == len(pairs)

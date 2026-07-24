"""P2-1C-2 harness 회귀 — weight OAT × 구조 anchor 불변식 + factor routing.

감사 전용·production delta 0. weight 하나만 변경 시 비대상 축 불변, factor routing
cross-check(stability OAT ⊥ activation 구조·activation OAT ⊥ pressure 구조).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_1c2" / "oat_harness.py")
    spec = importlib.util.spec_from_file_location("_p2_1c2", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_invariants_pass():
    h = _load()
    inv = h.invariant_checks(h.build_lattice())
    assert inv["passed"], inv["violations"][:10]


def test_factor_routing_cross_checks():
    """stability OAT ⊥ activation 구조(S0=S1) · activation OAT ⊥ pressure 구조(S0=S2)."""
    h = _load()
    act = h.activation_bonus_oat()
    stab = h.weight_oat(h._STAB_PARAMS, "stability")
    cross = h.structure_cross_check(act, stab)
    assert cross["stability_oat_invariant_to_activation_structure"] is True
    assert cross["activation_oat_invariant_to_pressure_structure"] is True


def test_chung_bonus_most_sensitive():
    """activation kind OAT: CHUNG bonus가 CHUNG 있는 사례에서 최대 민감(선형 local≈wide)."""
    h = _load()
    act = h.activation_bonus_oat()
    s = act["S0"]["single_CHUNG:CHUNG"]
    assert s["local"] > 0
    assert abs(s["local"] - s["wide"]) < 0.01     # 선형


def test_separation_ordering_admissibility_present():
    """separation OAT에 ordering 검사 존재(위반 시 NOT_ADMISSIBLE 기록·미보정)."""
    h = _load()
    sep = h.weight_oat(h._SEP_PARAMS, "separation")
    # baseline ±20% 범위에선 CHUNG 1.0 ≥ 나머지 유지 → 위반 0(검사 자체는 동작).
    assert "inadmissible" in sep
    assert isinstance(sep["inadmissible"], list)


def test_run_writes_outputs(tmp_path):
    h = _load()
    md = tmp_path / "r.md"
    js = tmp_path / "i.json"
    r = h.run(md, js)
    assert r["invariants_passed"]
    assert md.exists() and js.exists()

"""P2-1C-1 harness 회귀 — C0/C1 factor 구조 비교 불변식.

감사 전용·production delta 0. C0 baseline identity·C1 축간 분리(activation factor는
activation만·pressure factor는 pressure만)·cross-root 무영향이 유지됨을 확인한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_1c1" / "factor_structure_harness.py")
    spec = importlib.util.spec_from_file_location("_p2_1c1", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_invariants_pass():
    h = _load()
    inv = h.invariant_checks(h.build_lattice())
    assert inv["passed"], inv["violations"][:10]


def test_c1_activation_decoupled_from_pressure():
    """same-root 사례: activation factor는 stability/separation 미변동(dStab/dA=dSep/dA=0)."""
    h = _load()
    sens = h.axis_factor_sensitivity(h.c1_grid())
    s = sens["same_CHUNG_HYEONG"]
    assert s["d_activation_by_activation_factor"] != 0      # activation은 반응
    assert s["d_stability_by_activation_factor"] == 0       # stability 무반응
    assert s["d_separation_by_activation_factor"] == 0      # separation 무반응
    assert s["d_activation_by_pressure_factor"] == 0        # activation은 pressure 무반응
    assert s["d_stability_by_pressure_factor"] != 0         # stability는 pressure 반응


def test_cross_root_factor_insensitive():
    """cross-root는 서로 다른 root라 factor 전 변경에 불변."""
    h = _load()
    sens = h.axis_factor_sensitivity(h.c1_grid())
    s = sens["cross_CHUNG_HYEONG"]
    assert all(v == 0 for v in s.values())


def test_c0_diagonal_matches_baseline():
    """C0 대각 A=P=0.3이 production BASELINE과 동일(회귀 앵커)."""
    h = _load()
    from saju_engines.relationship_effect_vector import (
        synthesize_relationship_effect_vector,
    )
    for c in h.build_lattice():
        base = synthesize_relationship_effect_vector(c.evidences)
        c0 = h._axes(c, 0.3, 0.3)
        assert base.axes.model_dump() == c0.model_dump()


def test_run_writes_outputs(tmp_path):
    h = _load()
    md = tmp_path / "r.md"
    js = tmp_path / "i.json"
    r = h.run(md, js)
    assert r["invariants_passed"]
    assert md.exists() and js.exists()

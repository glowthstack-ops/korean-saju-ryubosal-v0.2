"""P2-1A 민감도 harness 회귀 — 불변식 게이트 + 계약 (RELATIONSHIP_VECTOR_CALIBRATION).

harness가 계속 돌아가고, 핵심 불변식(baseline byte-identity·SF single-kind 불변·
band 보수화·same/cross increment 계약)이 유지됨을 확인한다. 감사 전용 — production
delta 0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_1a" / "sensitivity_harness.py")
    spec = importlib.util.spec_from_file_location("_p2_1a", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_invariants_all_pass():
    """baseline byte-identity·SF/band scope·root count — 위반 0."""
    h = _load()
    cases = h.build_lattice()
    inv = h.invariant_checks(cases)
    assert inv["passed"], inv["violations"][:10]


def test_same_root_increment_monotonic_and_bounded():
    """same_inc 비감소(SF↑)·cross_inc ≥ same_inc·SF00에서 same_inc=0(§4·§5)."""
    h = _load()
    raw = h.raw_sweep(h.build_lattice())
    for row in raw["increments"]:
        sf_ids = [sid for sid, _ in h._SF]
        same_seq = [row[sid]["same_inc"] for sid in sf_ids]
        # 비감소.
        assert same_seq == sorted(same_seq), (row["pair"], same_seq)
        assert same_seq[0] == 0.0                      # SF00 → same_inc 0
        for sid in sf_ids:
            d = row[sid]
            assert d["cross_inc"] >= d["same_inc"]     # cross ≥ same


def test_cross_root_increment_sf_invariant():
    """cross_inc는 SF에 불변(서로 다른 root — secondary_factor 미적용)."""
    h = _load()
    raw = h.raw_sweep(h.build_lattice())
    for row in raw["increments"]:
        cross_vals = {row[sid]["cross_inc"] for sid, _ in h._SF}
        assert len(cross_vals) == 1, (row["pair"], cross_vals)


def test_band_projection_conservative_only():
    """band 보수화 방향만(strong→moderate 등) — 역방향 위반 0(§11)."""
    h = _load()
    band = h.band_sweep(h.build_lattice())
    assert band["band_reverse_violations"] == 0


def test_root_strong_rate_denominator_is_evaluated():
    """root=N strong rate 분모 = root=N & EVALUATED(§5) — n>0이면 rate 정의됨."""
    h = _load()
    band = h.band_sweep(h.build_lattice())
    grid = band["strong_rate_grid"]["SF30"]["B0"]
    for _root, stat in grid.items():
        if stat["n"] > 0:
            assert stat["rate"] is not None
            assert 0.0 <= stat["rate"] <= 1.0


def test_run_writes_outputs(tmp_path):
    h = _load()
    md = tmp_path / "rep.md"
    js = tmp_path / "inv.json"
    r = h.run(md, js)
    assert r["invariants_passed"]
    assert md.exists() and js.exists()
    import json
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["experiment_spec_version"] == h.EXPERIMENT_SPEC_VERSION
    assert payload["invariants"]["passed"]

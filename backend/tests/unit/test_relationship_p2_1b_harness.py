"""P2-1B 민감도 harness 회귀 — jaenghap 불변식 게이트 + 계약.

감사 전용·production delta 0. 핵심 불변식(JW↑ support 비증가·비대상 root 격리·
missing/multi-root 미적용·boundary sign flip)이 유지됨을 확인한다. 중복 modifier
비멱등은 synthesizer 발견으로 별도 관측(gate 실패 아님).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_1b" / "jaenghap_harness.py")
    spec = importlib.util.spec_from_file_location("_p2_1b", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_calibration_invariants_pass():
    """JW↑ support/net 비증가·비대상 격리·missing/multi-root 미적용·support≥0."""
    h = _load()
    cases = h.build_cases()
    grid = h.measure(cases)
    inv = h.invariant_checks(cases, grid)
    assert inv["passed"], inv["violations"][:10]


def test_target_support_monotone_decrease():
    """JW↑ → target support 비증가(pure_support 0.3→0.165)."""
    h = _load()
    cases = h.build_cases()
    grid = h.measure(cases)
    pure = next(c for c in cases if c.case_id == "pure_support")
    seq = [grid[pure.case_id][f"SF30_{jw}"]["target_support"]
           for jw in ("JW00", "JW25", "JW50", "JW75")]
    assert seq == sorted(seq, reverse=True)
    assert seq[0] == 0.3 and seq[-1] < seq[0]


def test_nontarget_root_isolated():
    """비대상 root support는 JW에 불변(scope 안전성)."""
    h = _load()
    cases = h.build_cases()
    grid = h.measure(cases)
    c = next(c for c in cases if c.case_id == "target_vs_nontarget")
    nts = {grid[c.case_id][f"SF30_{jw}"]["nontarget_support"]
           for jw in ("JW00", "JW25", "JW50", "JW75")}
    assert len(nts) == 1


def test_missing_and_multiroot_not_applied():
    """wrong_target·multi_root_target은 JW 전 support 불변(미적용)."""
    h = _load()
    cases = h.build_cases()
    grid = h.measure(cases)
    for cid in ("wrong_target", "multi_root_target"):
        sups = {grid[cid][f"SF30_{jw}"]["total_support"]
                for jw in ("JW00", "JW25", "JW50", "JW75")}
        assert len(sups) == 1


def test_boundary_sign_flip_by_jw():
    """boundary 사례: JW00 zero → JW25+ neg(JW 구동 sign flip)."""
    h = _load()
    cases = h.build_cases()
    grid = h.measure(cases)
    signs = [grid["boundary_sign_flip"][f"SF30_{jw}"]["stability_sign"]
             for jw in ("JW00", "JW25", "JW50", "JW75")]
    assert signs[0] == "zero"
    assert all(s == "neg" for s in signs[1:])


def test_duplicate_finding_surfaced():
    """중복 modifier 비멱등이 synthesizer 발견으로 관측됨(gate 실패 아님)."""
    h = _load()
    cases = h.build_cases()
    synth = h.synthesizer_findings(cases)
    # 현행 합성기는 transit modifier를 dedup하지 않음 → 비멱등.
    assert synth["duplicate_derived_modifier_idempotent"] is False
    assert synth["example"] is not None


def test_run_writes_outputs(tmp_path):
    h = _load()
    md = tmp_path / "r.md"
    js = tmp_path / "i.json"
    r = h.run(md, js)
    assert r["invariants_passed"]
    assert md.exists() and js.exists()

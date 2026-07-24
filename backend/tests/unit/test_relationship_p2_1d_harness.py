"""P2-1D shortlist harness 회귀 — profile 분포·review flag·경계 사례·production 불변.

감사 전용·production delta 0. D0=BASELINE, 사전 등록 임계값 적용, C1 activation
conservative(D1)만 activation 분포 이동(routing), review flag는 자동 탈락 아님.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_1d" / "shortlist_harness.py")
    spec = importlib.util.spec_from_file_location("_p2_1d", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_profiles_c0_c1_no_c2():
    """shortlist은 C0·C1만·C2 없음(§6)."""
    h = _load()
    profiles = h.build_profiles()
    structures = {p.factor_structure.value for p in profiles.values()}
    assert "c2_axis_split" not in structures
    assert "c0_shared" in structures and "c1_activation_pressure" in structures
    assert "D0_baseline" in profiles


def test_d0_is_production_baseline():
    """D0 = production BASELINE(0.3 공유)."""
    h = _load()
    from saju_engines.relationship_effect_vector import BASELINE_CALIBRATION
    d0 = h.build_profiles()["D0_baseline"]
    assert d0.same_root_factors.model_dump() == \
        BASELINE_CALIBRATION.same_root_factors.model_dump()


def test_d1_shifts_activation_others_do_not():
    """C1 activation conservative(D1)만 activation 분포 이동 — 나머지는 D0와 동일 activation."""
    h = _load()
    pis = h.build_period_inputs()
    profiles = h.build_profiles()
    grid = h.measure(pis, profiles)

    def _act_dist(name):
        from collections import Counter
        return Counter(r["act_band"] for r in grid[name] if r["act_band"])
    d0 = _act_dist("D0_baseline")
    # D2(pressure)·D4/D5/D6(weight)는 activation 불변.
    for name in ("D2_C1_prs_conservative", "D4_stab_CHUNG_conservative",
                 "D5_sep_conservative", "D6_HAP_support_up"):
        assert _act_dist(name) == d0, name
    # D1은 activation 이동(strong 감소).
    assert _act_dist("D1_C1_act_conservative") != d0


def test_review_flags_do_not_auto_fail():
    """review flag는 자동 탈락 아님 — PASS/REVIEW_* 상태만 부여(중첩 가능)."""
    h = _load()
    pis = h.build_period_inputs()
    profiles = h.build_profiles()
    grid = h.measure(pis, profiles)
    flags = h.review_flags(grid)
    valid = {"PASS", "REVIEW_COLLAPSE", "REVIEW_OVERACTIVATION",
             "REVIEW_UNDERACTIVATION"}
    for _name, r in flags["per_profile"].items():
        parts = set(r["status"].split("+"))
        assert parts <= valid


def test_thresholds_prefixed(tmp_path):
    """사전 등록 임계값이 payload에 기록(결과 관찰 전 고정 증빙)."""
    h = _load()
    r = h.run(tmp_path / "r.md", tmp_path / "i.json")
    import json
    payload = json.loads((tmp_path / "i.json").read_text(encoding="utf-8"))
    assert payload["thresholds"]["collapse_share"] == 0.85
    assert payload["thresholds"]["overact_abs"] == 0.10
    assert r["boundary_cases"] >= 0

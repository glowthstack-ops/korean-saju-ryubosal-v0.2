"""P2-3 블라인드 감수 표본 생성 회귀 — 블라인딩·분리·게이트 (§9).

profile 실명·baseline·legacy 비노출, disagreement/control 카운트, dedup, D1≠D3 포함,
answer key 분리. 생성은 읽기 전용(production delta 0).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parents[1].parent / "scripts" / "audits"
            / "relationship_p2_3" / "generate_blind_review.py")
    spec = importlib.util.spec_from_file_location("_p2_3", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gen(mod, tmp_path):
    mod.OUT_SHEET = tmp_path / "sheet.csv"
    mod.OUT_KEY = tmp_path / "key.csv"
    mod.OUT_MANIFEST = tmp_path / "manifest.json"
    mod.OUT_SELECT = tmp_path / "select.md"
    return mod.generate()


def test_counts_within_spec(tmp_path):
    """unique 24~30(disagreement 15 + control 9~15)."""
    h = _load()
    r = _gen(h, tmp_path)
    assert r["disagreement"] == 15
    assert 9 <= r["control"] <= 15
    assert 24 <= r["unique_cases"] <= 30


def test_sheet_no_real_profile_names(tmp_path):
    """감수지에 profile 실명·baseline 미노출(블라인드)."""
    h = _load()
    _gen(h, tmp_path)
    text = (tmp_path / "sheet.csv").read_text(encoding="utf-8")
    for leak in ("D0_baseline", "D1_C1", "D2_C1", "D3_CHUNG", "D4_stab",
                 "D5_sep", "D6_HAP", "baseline", "c0_shared", "c1_activation"):
        assert leak not in text, leak
    # profile_label은 A~G만.
    with (tmp_path / "sheet.csv").open(encoding="utf-8") as f:
        labels = {row["profile_label"] for row in csv.DictReader(f)}
    assert labels <= set("ABCDEFG")


def test_sheet_no_legacy_columns(tmp_path):
    """legacy delta·후보 순위 미노출(§4)."""
    h = _load()
    _gen(h, tmp_path)
    with (tmp_path / "sheet.csv").open(encoding="utf-8") as f:
        cols = next(csv.reader(f))
    for c in cols:
        assert "legacy" not in c.lower()
    # 응답란·"차이 없음" 존재(§5).
    assert "no_meaningful_difference" in cols
    assert "activation_judgment" in cols


def test_key_separated_and_complete(tmp_path):
    """answer key는 별도 파일이고 7 profile 전체 매핑."""
    h = _load()
    _gen(h, tmp_path)
    with (tmp_path / "key.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 7
    assert {r["blind_label"] for r in rows} == set("ABCDEFG")
    assert {r["actual_profile_id"] for r in rows} == {
        "D0_baseline", "D1_C1_act_conservative", "D2_C1_prs_conservative",
        "D3_CHUNG_bonus_conservative", "D4_stab_CHUNG_conservative",
        "D5_sep_conservative", "D6_HAP_support_up"}


def test_d1_ne_d3_cases_present(tmp_path):
    """D1(구조)≠D3(CHUNG bonus) 구별 사례 포함(§1·§9)."""
    h = _load()
    r = _gen(h, tmp_path)
    assert r["d1_ne_d3"] >= 1


def test_unevaluated_not_shown_as_zero(tmp_path):
    """미평가 축은 'insufficient'로 표시(0 아님, §9)."""
    h = _load()
    _gen(h, tmp_path)
    with (tmp_path / "sheet.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # insufficient가 나타나면 band 값이 아니라 문자열로.
    bands = {r["activation_band"] for r in rows}
    assert bands <= {"low", "weak", "moderate", "strong", "insufficient"}


def test_manifest_hidden_has_groups(tmp_path):
    """manifest(숨김)에 군·reason·repeat 매핑."""
    h = _load()
    _gen(h, tmp_path)
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    groups = {c["group"] for c in m["cases"]}
    assert "disagreement" in groups and "control" in groups
    assert "hidden_repeat" in groups
    assert m["counts"]["hidden_repeat"] == 2

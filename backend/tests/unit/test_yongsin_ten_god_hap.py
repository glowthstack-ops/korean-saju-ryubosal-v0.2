"""官 외 십성 합 맥락 확장 (#7) — 財/印/食傷/比劫 operational 주석.

라벨·세력·final 불변. 官殺은 Phase 3 officer_hap 유지(중복 방지). 배치는 role class 별
(favorable=neg, unfavorable=pos, conditional=note 중심, neutral=note). 합화 confirmed=note only.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.candidates import _ten_god_hap_placement

from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
_D = "財(재물·계약)"


def _by_el(make_pillars, args):
    y = analyze_chart(make_pillars(*args)).yongsin
    return y, {r.element: r for r in y.operational_roles}


def _acc():
    return {"pos": [], "neg": [], "note": []}


# ── 배치 로직 (role class × mode) — fixture 무관 직접 단언 ──
def test_placement_favorable() -> None:
    a = _acc()
    for m in ("bind", "contend", "away"):
        _ten_god_hap_placement(a, _D, m, "favorable")
    assert len(a["neg"]) == 3 and not a["pos"]  # 유익 작용 묶임/지연 → negative
    n = _acc()
    _ten_god_hap_placement(n, _D, "transform", "favorable")
    assert n["note"] and not n["neg"]  # 合化 confirmed=note only


def test_placement_unfavorable() -> None:
    a = _acc()
    _ten_god_hap_placement(a, _D, "bind", "unfavorable")
    _ten_god_hap_placement(a, _D, "away", "unfavorable")
    assert len(a["pos"]) == 2 and not a["neg"]  # 병/부담 묶여 완화 → positive
    c = _acc()
    _ten_god_hap_placement(c, _D, "contend", "unfavorable")
    assert c["neg"] and not c["pos"]  # 쟁합은 negative


def test_placement_conditional_note_centric() -> None:
    # ★ conditional 은 unfavorable 과 다르게 — 단순 길흉화 금지, note 중심.
    a = _acc()
    _ten_god_hap_placement(a, _D, "bind", "conditional")
    assert a["note"] and not a["pos"] and not a["neg"]  # bind → note만
    c = _acc()
    _ten_god_hap_placement(c, _D, "contend", "conditional")
    assert c["note"] and c["neg"] and not c["pos"]  # 쟁합만 negative 병기
    aw = _acc()
    _ten_god_hap_placement(aw, _D, "away", "conditional")
    assert aw["note"] and not aw["pos"] and not aw["neg"]


def test_placement_neutral_note_only() -> None:
    a = _acc()
    for m in ("bind", "away", "transform"):
        _ten_god_hap_placement(a, _D, m, "neutral")
    assert a["note"] and not a["pos"] and not a["neg"]


# ── 통합: 표준사례 火(比劫)·水(官殺) ──
def test_standard_bigeop_enriched_officer_unchanged(make_pillars) -> None:
    y, by = _by_el(make_pillars, _STD)
    # 火(比劫, 조후보조신=favorable): 丁壬合(bind+contend) → ten_god_hap negative.
    fire = by["火"]
    assert fire.operational_role == "조후보조신"  # 라벨 불변
    assert any("比劫" in s for s in fire.negative_when)
    assert "ten_god_hap" in (fire.note or "")
    # 水(官殺): officer_hap 만, ten_god_hap 미적용(중복 방지).
    water = by["水"]
    assert "officer_hap" in (water.note or "")
    assert "ten_god_hap" not in (water.note or "")


def test_invariance_final_operability(make_pillars) -> None:
    y, by = _by_el(make_pillars, _STD)
    assert y.final["yongsin"] == "木" and y.final["heesin"] == "火"  # final 불변
    assert by["木"].operability == 0.595  # operability 불변
    assert y.canonical_roles == {
        k: y.final[k] for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
    }


def test_fallback_no_ten_god_hap(make_pillars) -> None:
    # bridge/disease/support(model_map 미채택): ten_god_hap 미누출.
    for args in (
        ((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
         (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG),
        ((Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
         (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG),
    ):
        y = analyze_chart(make_pillars(*args)).yongsin
        assert all("ten_god_hap" not in (r.note or "") for r in y.operational_roles)

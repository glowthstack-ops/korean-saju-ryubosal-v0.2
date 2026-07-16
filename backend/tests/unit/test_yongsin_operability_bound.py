"""용신 작동성 — 합반 (#6b-2). 용신 투출 천간이 bind/contend로 묶일 때만 penalty.

合化 confirmed(transform)·합거(away)·distribution 차감 제외. favorability=canonical. operability만.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-4
"""

from __future__ import annotations

import saju_manse_analysis.yongsin.candidates as C
from saju_manse_analysis import analyze_chart
from saju_manse_analysis.relations.hap_modes import AffectedGod, StemHapResolution
from saju_manse_analysis.yongsin.candidates import _yongsin_bound_factor
from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_FACTOR_SHORT,
    OPERABILITY_PENALTY,
)

from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
# 용신 金 투출(庚)·乙庚合 bind → yongsin_bound (0.85)
_BOUND = ((Stem.EUL, Branch.CHUK), (Stem.GAP, Branch.JA),
          (Stem.GAP, Branch.JA), (Stem.GYEONG, Branch.O), Stem.GAP)
_CANON: dict[str, str | None] = {
    "yongsin": "金", "heesin": "土", "gisin": "火", "gusin": "木", "hansin": "水",
}


def _yongsin(make_pillars, *args):
    y = analyze_chart(make_pillars(*args)).yongsin
    return next(r for r in y.operational_roles if r.element == y.final["yongsin"])


def _res(hap_mode: str, *, contend: bool = False, direction: str | None = None,
         element: str = "金") -> StemHapResolution:
    return StemHapResolution(
        pair=("乙", "庚"), positions=("year", "hour"), transform_element="金",
        transform_tier="none", hap_mode=hap_mode, direction=direction, contend=contend,
        affected=[AffectedGod(stem="庚", ten_god="", element=element, role="", effect="neutral")],
    )


def test_standard_no_bound(make_pillars) -> None:
    # 표준: 木 미투출 → yongsin_bound 미적용, 0.595.
    er = _yongsin(make_pillars, *_STD)
    assert "yongsin_bound" not in er.operability_factors
    assert er.operability == 0.595


def test_bound_applies_on_bind(make_pillars) -> None:
    er = _yongsin(make_pillars, *_BOUND)
    assert "yongsin_bound" in er.operability_factors
    assert er.operability == round(1.0 * (1 - OPERABILITY_PENALTY["yongsin_bound"]), 4)
    assert OPERABILITY_FACTOR_SHORT["yongsin_bound"] == "합반"
    assert any("합반" in s for s in er.negative_when)


def test_helper_excludes_transform_and_away(make_pillars, monkeypatch) -> None:
    pillars = make_pillars(*_BOUND)  # 金 투출
    monkeypatch.setattr(C, "resolve_stem_hap", lambda p, fav: [_res("transform")])
    assert _yongsin_bound_factor("金", pillars, _CANON) is False     # 合化 confirmed 제외
    monkeypatch.setattr(C, "resolve_stem_hap", lambda p, fav: [_res("bind", direction="away")])
    assert _yongsin_bound_factor("金", pillars, _CANON) is False     # 합거 제외
    monkeypatch.setattr(C, "resolve_stem_hap", lambda p, fav: [_res("bind")])
    assert _yongsin_bound_factor("金", pillars, _CANON) is True      # 합반
    monkeypatch.setattr(C, "resolve_stem_hap",
                        lambda p, fav: [_res("combine_self", contend=True)])
    assert _yongsin_bound_factor("金", pillars, _CANON) is True      # 쟁합


def test_no_transmit_excludes_bound(make_pillars, monkeypatch) -> None:
    # 용신 미투출이면 hap 이 있어도 bound 아님(no_transmit 영역).
    std_pillars = make_pillars(*_STD)  # 木 미투출
    monkeypatch.setattr(C, "resolve_stem_hap",
                        lambda p, fav: [_res("bind", element="木")])
    assert _yongsin_bound_factor("木", std_pillars,
                                 {"yongsin": "木", "heesin": "水"}) is False


def test_invariance_final_canonical(make_pillars) -> None:
    y = analyze_chart(make_pillars(*_BOUND)).yongsin
    assert y.canonical_roles == {
        k: y.final[k] for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
    }
    assert y.final["selected_model"]

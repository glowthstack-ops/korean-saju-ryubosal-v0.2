"""용신 작동성 — 고립 (#6b-1). 보수적 4조건 AND — 과발동 방지.

①present ②생조부재(生용신 오행 부재) ③단일출처(용신 출처 정확히 1) ④손상동반(clash/void/gyeokgak).
전부 충족할 때만 yongsin_isolation. operability 전용 — final/groups/strength/scoring/relations 불변.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-4
"""

from __future__ import annotations

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.candidates import _yongsin_isolation_applies
from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_FACTOR_SHORT,
    OPERABILITY_PENALTY,
)

from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
# 용신 金: 투간無·통근 1개(酉)·생조(土) 부재·酉가 卯酉 충 → 4조건 충족 → 고립.
_ISO = ((Stem.JEONG, Branch.MYO), (Stem.GAP, Branch.JA),
        (Stem.GAP, Branch.JA), (Stem.EUL, Branch.YU), Stem.GAP)


def _yongsin(make_pillars, *args):
    y = analyze_chart(make_pillars(*args)).yongsin
    return next(r for r in y.operational_roles if r.element == y.final["yongsin"])


def test_standard_no_isolation(make_pillars) -> None:
    # 표준: 木 통근 2개(卯·未)·생조 水 충분 → 단일출처/생조부재 불충족 → 고립 미적용, 0.595.
    er = _yongsin(make_pillars, *_STD)
    assert "yongsin_isolation" not in er.operability_factors
    assert er.operability == 0.595


def test_isolation_applies_compound(make_pillars) -> None:
    er = _yongsin(make_pillars, *_ISO)
    assert "yongsin_isolation" in er.operability_factors
    assert er.operability_factors[-1] == "yongsin_isolation"  # 순서: 손상 뒤
    assert OPERABILITY_FACTOR_SHORT["yongsin_isolation"] == "고립"
    assert any("고립" in s for s in er.negative_when)
    # 손상(clash)·no_transmit과 곱연산.
    expected = round(
        (1 - OPERABILITY_PENALTY["no_transmit"])
        * (1 - OPERABILITY_PENALTY["yongsin_clash"])
        * (1 - OPERABILITY_PENALTY["yongsin_isolation"]), 4,
    )
    assert er.operability == expected


def test_isolation_requires_damage_overlap(make_pillars) -> None:
    # 손상 factor 없으면 고립 미적용(④ 조건).
    iso_pillars = make_pillars(*_ISO)
    assert _yongsin_isolation_applies("金", iso_pillars, []) is False
    assert _yongsin_isolation_applies("金", iso_pillars, ["yongsin_clash"]) is True


def test_isolation_not_when_multi_source_or_saengjo(make_pillars) -> None:
    # 표준 木: 통근 2개 + 생조 水 → 손상 주입해도 고립 아님(②③ 불충족).
    std_pillars = make_pillars(*_STD)
    assert _yongsin_isolation_applies("木", std_pillars, ["gyeokgak_zimao"]) is False


def test_invariance_final_canonical(make_pillars) -> None:
    y = analyze_chart(make_pillars(*_ISO)).yongsin
    assert y.canonical_roles == {
        k: y.final[k] for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
    }
    assert y.final["selected_model"]

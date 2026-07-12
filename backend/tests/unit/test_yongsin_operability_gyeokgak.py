"""용신 작동성 — 子卯刑 격각 통관손상 (Phase 4b).

비인접 子卯 격각만 operability penalty(allowlist 1건, 용신 木만). 이벤트/관계 판정 불변(인접
子卯刑은 이벤트 레이어). 계수는 operational_role_config(experimental).
규격: YONGSIN_OPERATIONAL_ROLE_SPEC §5-5
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.candidates import _gyeokgak_operability_factors
from saju_manse_analysis.yongsin.operational_role_config import OPERABILITY_PENALTY

from saju_engines.event_scoring import favorability_map
from saju_manse_core.relations import detect
from saju_shared_types.enums import Branch, Stem

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")


def _yongsin_role(y):
    return next(r for r in y.operational_roles if r.element == y.final["yongsin"])


def _std_pillars(make_pillars):
    # 표준사례: 子(월지)·卯(시지) 비인접 격각, 용신 木.
    return make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )


def test_standard_gyeokgak_penalty(make_pillars) -> None:
    y = analyze_chart(_std_pillars(make_pillars)).yongsin
    er = _yongsin_role(y)
    expected = round(
        1.0 * (1 - OPERABILITY_PENALTY["no_transmit"]) * (1 - 0.30), 4
    )
    assert er.operability == expected == 0.595
    assert er.operability_factors == ["no_transmit", "gyeokgak_zimao"]
    assert any("子卯 격각" in s for s in er.negative_when)


def test_event_layer_unchanged_gyeokgak_not_eventized(make_pillars) -> None:
    # 표준사례의 비인접 子卯 는 관계/이벤트로 잡히지 않는다(relations 불변).
    rels = detect(_std_pillars(make_pillars))
    assert not any("punish" in str(r.rel_type) for r in rels)


def test_adjacent_zimao_is_event_not_operability(make_pillars) -> None:
    # 인접 子卯(月子·日卯): 이벤트(형)로는 검출, operability 에는 gyeokgak_zimao 미적용.
    pillars = make_pillars(
        (Stem.BYEONG, Branch.IN), (Stem.GAP, Branch.JA),
        (Stem.JEONG, Branch.MYO), (Stem.GAP, Branch.JA), Stem.JEONG,
    )
    assert any("punish" in str(r.rel_type) for r in detect(pillars))   # 이벤트는 잡힘
    er = _yongsin_role(analyze_chart(pillars).yongsin)
    assert "gyeokgak_zimao" not in er.operability_factors              # operability 미반영
    assert er.operability == 1.0


def test_gyeokgak_gated_by_yongsin_element(make_pillars) -> None:
    # 같은 격각 子卯 라도 용신 오행이 allowlist(木) 와 다르면 미적용(DP-b1).
    pillars = _std_pillars(make_pillars)
    assert _gyeokgak_operability_factors("木", pillars)        # 木 → 적용
    assert _gyeokgak_operability_factors("火", pillars) == []  # 火 → 미적용
    assert _gyeokgak_operability_factors("水", pillars) == []


def test_no_zimao_no_gyeokgak(make_pillars) -> None:
    # 子卯 없는 차트(용신 木이어도): 격각 factor 없음.
    pillars = make_pillars(
        (Stem.GYE, Branch.HAE), (Stem.EUL, Branch.HAE),
        (Stem.JEONG, Branch.CHUK), (Stem.EUL, Branch.MI), Stem.JEONG,
    )
    assert _gyeokgak_operability_factors("木", pillars) == []
    er = _yongsin_role(analyze_chart(pillars).yongsin)
    assert "gyeokgak_zimao" not in er.operability_factors


def test_single_factor_no_duplicate(make_pillars) -> None:
    # 중복 子/卯 있어도 gyeokgak_zimao 는 1회만.
    factors = _gyeokgak_operability_factors("木", _std_pillars(make_pillars))
    keys = [f for f, _w, _r in factors]
    assert keys.count("gyeokgak_zimao") == 1


def test_final_groups_strength_favorability_unchanged(make_pillars) -> None:
    chart = analyze_chart(_std_pillars(make_pillars))
    y, force = chart.yongsin, chart.force
    assert force.strength.band == "신약"
    assert round(force.ten_gods.groups["officer"]) == 45
    assert y.final["heesin"] == "火" and y.final["hansin"] == "水"
    assert y.final["confidence"] == 0.8822          # final.confidence 불변
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}
    fav = favorability_map(SimpleNamespace(yongsin_analysis=y))  # type: ignore[arg-type]
    for key, ko in (("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
                    ("gusin", "구신"), ("hansin", "한신")):
        assert fav.get(y.final[key]) == ko

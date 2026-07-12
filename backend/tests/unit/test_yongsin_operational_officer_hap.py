"""용신 작동역할 — 官殺 합 맥락 주석 (Phase 3, Option B).

합반/쟁합/합거/합화 + 관살혼잡을 官殺 ElementRole 에 note·조건으로 보강. operational_role 라벨은
불변(DP2), 세력·분포·final 불변(scoring-0). model_map 채택만. resolve_stem_hap·관살혼잡 재사용.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-3
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_engines.event_scoring import favorability_map
from saju_shared_types.enums import Branch, Stem

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")


def _by_element(y) -> dict:
    return {r.element: r for r in y.operational_roles}


def _std(make_pillars):
    # 표준사례: 丁壬合(쟁합, 化木 미성립=합반) + 관살혼잡(壬정관+癸칠살). 官殺=水.
    return analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin


def test_officer_hap_enriches_water_without_changing_label(make_pillars) -> None:
    er = _by_element(_std(make_pillars))["水"]
    assert er.operational_role == "조건부 한신/병"          # ★ 라벨 불변(희신 과다 교정 후)
    # 합반 → positive_when, 쟁합·관살혼잡 → negative_when
    assert any("합반" in s for s in er.positive_when)
    assert any("쟁합" in s for s in er.negative_when)
    assert any("관살혼잡" in s or "官殺混雜" in s for s in er.negative_when)
    # 출처 병합 순서 고정
    assert er.note is not None
    assert "synthesized_by=overload_condition+climate_harmful+officer_hap" in er.note


def test_no_dup_in_condition_lists(make_pillars) -> None:
    er = _by_element(_std(make_pillars))["水"]
    assert len(er.positive_when) == len(set(er.positive_when))
    assert len(er.negative_when) == len(set(er.negative_when))


def test_no_officer_hap_when_no_hap(make_pillars) -> None:
    # 1980 신약 己(官=木, 천간에 木 없음 → 官 합 없음): officer_hap 미부착.
    y = analyze_chart(make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )).yongsin
    assert all(not (r.note and "officer_hap" in r.note) for r in y.operational_roles)


def test_fallback_no_officer_hap_leak(make_pillars) -> None:
    # bridge/disease/support 특수분기(model_map 미채택): officer_hap 미누출.
    for args in (
        ((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
         (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG),
        ((Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
         (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU),
        ((Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
         (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG),
    ):
        y = analyze_chart(make_pillars(*args)).yongsin
        assert all(not (r.note and "officer_hap" in r.note) for r in y.operational_roles)
        canon = {r.element: r.canonical_role for r in y.operational_roles}
        oper = {r.element: r.operational_role for r in y.operational_roles}
        assert canon == oper


def test_final_groups_strength_favorability_unchanged(make_pillars) -> None:
    # Phase 3 는 operational 만 보강 — 엔진 산출(final/groups/strength/favorability) 불변.
    chart = analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    ))
    y, force = chart.yongsin, chart.force
    assert force.strength.band == "신약"
    assert round(force.ten_gods.groups["officer"]) == 45      # 官殺 세력 불변(차감 없음)
    assert y.final["heesin"] == "火" and y.final["hansin"] == "水"
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}
    fav = favorability_map(SimpleNamespace(yongsin_analysis=y))  # type: ignore[arg-type]
    for key, ko in (("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
                    ("gusin", "구신"), ("hansin", "한신")):
        assert fav.get(y.final[key]) == ko


def test_roundtrip_with_officer_hap(make_pillars) -> None:
    from saju_shared_types.yongsin import AggregatedYongsinResult

    y = _std(make_pillars)
    restored = AggregatedYongsinResult.model_validate(y.model_dump())
    assert [r.model_dump() for r in restored.operational_roles] == \
        [r.model_dump() for r in y.operational_roles]

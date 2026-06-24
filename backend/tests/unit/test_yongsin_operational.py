"""용신 2계층 역할(canonical/operational) — Phase 0.

정적 역할(final/canonical)은 불변, operational 만 선택 모델의 자체 역할맵으로 정상화.
부분맵·특수분기 모델은 canonical 폴백(None 역할 미발생). event_scoring 미연결(final 만 소비).
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_engines.event_scoring import favorability_map
from saju_shared_types.enums import Branch, Stem

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")


def _canon(y) -> dict[str, str]:
    return {r.element: r.canonical_role for r in y.operational_roles}


def _oper(y) -> dict[str, str]:
    return {r.element: r.operational_role for r in y.operational_roles}


def test_standard_killing_resource_operational_normalizes(make_pillars) -> None:
    # 표준사례 丁巳/壬子/丁未/癸卯 (丁火 신약·水 60%대, 살인상생형 resource_as_yongsin):
    # final/canonical 은 정적 순환대로 희신=水·한신=火 이지만, operational 은 선택 모델
    # 자체맵(비겁 방조=희신)으로 정상화되어 火=희신·水=한신.
    pillars = make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )
    y = analyze_chart(pillars).yongsin
    assert y.final["selected_model"] == "resource_as_yongsin"

    # final 불변 (정적 순환)
    assert y.final["yongsin"] == "木"
    assert y.final["heesin"] == "水"
    assert y.final["hansin"] == "火"
    # canonical_roles 는 final 5역할의 미러
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}

    canon, oper = _canon(y), _oper(y)
    assert canon["水"] == "희신" and canon["火"] == "한신"   # 정적
    # 木 용신·金 기신은 phase 안정. 火·水 의 작동역할 정밀화(조후보조신·조건부 희신/병)는
    # Phase 1~2 테스트가 검증한다. 여기서는 정적과 달라졌다는 점만 확인(단순 복제가 아님).
    assert oper["木"] == "용신" and oper["金"] == "기신"
    assert oper["火"] != "한신"   # 모델맵·조후로 canonical 한신에서 격상됨
    assert oper["水"] != canon["水"] and oper["火"] != canon["火"]


def test_operational_roles_cover_five_elements_no_none(make_pillars) -> None:
    # operational_roles 는 5오행 1:1, None/빈 역할이 없어야 한다.
    pillars = make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )
    y = analyze_chart(pillars).yongsin
    assert len(y.operational_roles) == 5
    assert {r.element for r in y.operational_roles} == {"木", "火", "土", "金", "水"}
    for r in y.operational_roles:
        assert r.canonical_role and r.operational_role  # None/빈 역할 없음


def test_bridge_tonggwan_falls_back_to_canonical(make_pillars) -> None:
    # 2015 통관용신(bridge_tonggwan, 부분맵): operational == canonical (특수분기 교정 보존).
    pillars = make_pillars(
        (Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
        (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG,
    )
    y = analyze_chart(pillars).yongsin
    assert _canon(y) == _oper(y)
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}


def test_disease_remedy_falls_back_to_canonical(make_pillars) -> None:
    # 1980 戊 신강(편인도식 병약, disease_remedy:pyeonin_dosik 부분맵): operational == canonical.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
        (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU,
    )
    y = analyze_chart(pillars).yongsin
    assert _canon(y) == _oper(y)


def test_support_special_branch_falls_back_to_canonical(make_pillars) -> None:
    # 1985 丁 태신약(부일간 무비겁 특수분기): _support_model 은 5역할 완비지만 final 이
    # 특수분기로 gisin/hansin 을 교정 → operational 은 그 교정(canonical)을 따라야 한다.
    pillars = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
        (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG,
    )
    y = analyze_chart(pillars).yongsin
    assert y.final["selected_model"] == "support_day_master"
    # 특수분기 교정값(기존 테스트와 동일): 한신=水, 기신=土
    assert y.final["hansin"] == "水" and y.final["gisin"] == "土"
    assert _canon(y) == _oper(y)  # 교정 보존 — 모델 원본맵(gisin=水)으로 되돌리지 않음


def test_final_and_favorability_unchanged_by_operational_layer(make_pillars) -> None:
    # operational 레이어 추가가 final(점수화 SSOT)과 favorability_map 을 바꾸지 않음을 보장.
    cases = [
        make_pillars((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
                     (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG),
        make_pillars((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
                     (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG),
        make_pillars((Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
                     (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU),
    ]
    for pillars in cases:
        chart = analyze_chart(pillars)
        y = chart.yongsin
        # final 은 용희기구한 + confidence/selected_model 만 (operational 키 누출 없음)
        assert set(y.final) == set(_ROLE_KEYS) | {"confidence", "selected_model"}
        # favorability_map 은 result.yongsin_analysis.final 만 참조 → 5역할이 그대로 매핑된다.
        fav = favorability_map(SimpleNamespace(yongsin_analysis=y))  # type: ignore[arg-type]
        for key, ko in (("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
                        ("gusin", "구신"), ("hansin", "한신")):
            assert fav.get(y.final[key]) == ko

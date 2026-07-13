"""용신 작동성(operability) — 투간/통근·정편인 (Phase 4a).

operability 는 ElementRole 신규 필드(용신만, 0~1, 감점형). final.confidence 불변·scoring-0.
격각/子卯刑 은 Phase 4b — 여기엔 없음. 계수는 operational_role_config(experimental).
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-4
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_PENALTY,
    OPERABILITY_REASON,
)

from saju_engines.event_scoring import favorability_map
from saju_shared_types.enums import Branch, Stem

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")
_ALLOWED_4A = {"no_transmit", "no_root", "pyeonin_only"}


def _yongsin_role(y):
    return next(r for r in y.operational_roles if r.element == y.final["yongsin"])


def _std(make_pillars):
    return analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin


def test_no_transmit_penalty_isolated(make_pillars) -> None:
    # 용신 투간無·통근O(solid·충無·공망無·子卯無) → no_transmit 단독.
    # 시간 丁: 子월 甲의 조후 천간(丁) 충족 — P4 조후 결핍 가산으로 johu(火)가
    # 주모델을 뺏지 않게 해 인수격 관성용신 金(丑中辛 통근·투간無)을 유지한다.
    er = _yongsin_role(analyze_chart(make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GAP, Branch.JA),
        (Stem.GAP, Branch.JA), (Stem.JEONG, Branch.CHUK), Stem.GAP,
    )).yongsin)
    assert er.operability == round(1.0 * (1 - OPERABILITY_PENALTY["no_transmit"]), 4)
    assert er.operability_factors == ["no_transmit"]
    assert set(er.operability_factors) <= _ALLOWED_4A     # 4a 범위(격각 factor 없음)
    assert OPERABILITY_REASON["no_transmit"] in er.negative_when


def test_healthy_yongsin_operability_is_one(make_pillars) -> None:
    # 정인(甲) 투출 + 통근: 감점 없음 → operability 1.0.
    y = analyze_chart(make_pillars(
        (Stem.BYEONG, Branch.IN), (Stem.GAP, Branch.JA),
        (Stem.JEONG, Branch.MYO), (Stem.GAP, Branch.JA), Stem.JEONG,
    )).yongsin
    er = _yongsin_role(y)
    assert er.operability == 1.0 and er.operability_factors == []


def test_pyeonin_only_lower_than_jeongin(make_pillars) -> None:
    # 편인(癸)만 투출(공망·충·子卯 무관): pyeonin_only 감점만 → 정인 케이스보다 낮다.
    pyeonin = _yongsin_role(analyze_chart(make_pillars(
        (Stem.BYEONG, Branch.IN), (Stem.GYE, Branch.CHUK),
        (Stem.EUL, Branch.CHUK), (Stem.BYEONG, Branch.O), Stem.EUL,
    )).yongsin)
    jeongin = _yongsin_role(analyze_chart(make_pillars(
        (Stem.BYEONG, Branch.IN), (Stem.GAP, Branch.JA),
        (Stem.JEONG, Branch.MYO), (Stem.GAP, Branch.JA), Stem.JEONG,
    )).yongsin)
    assert "pyeonin_only" in pyeonin.operability_factors
    assert pyeonin.operability == round(1.0 * (1 - OPERABILITY_PENALTY["pyeonin_only"]), 4)
    assert pyeonin.operability < jeongin.operability


def test_non_yongsin_operability_none(make_pillars) -> None:
    y = _std(make_pillars)
    for r in y.operational_roles:
        if r.element != y.final["yongsin"]:
            assert r.operability is None and r.operability_factors == []


def test_fallback_yongsin_operability_none(make_pillars) -> None:
    # bridge/disease/support 특수분기(model_map 미채택): 용신 operability 미산정.
    for args in (
        ((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
         (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG),
        ((Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
         (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU),
        ((Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
         (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG),
    ):
        y = analyze_chart(make_pillars(*args)).yongsin
        assert all(r.operability is None for r in y.operational_roles)


def test_final_groups_strength_favorability_unchanged(make_pillars) -> None:
    chart = analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    ))
    y, force = chart.yongsin, chart.force
    assert force.strength.band == "신약"
    assert round(force.ten_gods.groups["officer"]) == 45
    assert y.final["heesin"] == "火" and y.final["hansin"] == "水"
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}
    fav = favorability_map(SimpleNamespace(yongsin_analysis=y))  # type: ignore[arg-type]
    for key, ko in (("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
                    ("gusin", "구신"), ("hansin", "한신")):
        assert fav.get(y.final[key]) == ko


def test_roundtrip_with_operability(make_pillars) -> None:
    from saju_shared_types.yongsin import AggregatedYongsinResult

    y = _std(make_pillars)
    restored = AggregatedYongsinResult.model_validate(y.model_dump())
    assert [r.model_dump() for r in restored.operational_roles] == \
        [r.model_dump() for r in y.operational_roles]

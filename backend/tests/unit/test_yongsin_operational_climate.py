"""용신 작동역할 — 조후 가드 연결 (Phase 2).

_climate_harmful 을 operational 에 연결: climate_need 격상(조후보조신)·climate_harmful 강등.
중립월(辰戌)·조후 무문제면 no-op. operational 미소비(scoring 은 final 만). model_map 채택만.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §5-1
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_engines.event_scoring import favorability_map
from saju_shared_types.enums import Branch, Stem

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")
_CONDITIONAL = {"조건부 희신/병", "조건부 제살보조"}


def _by_element(y) -> dict:
    return {r.element: r for r in y.operational_roles}


def _standard(make_pillars):
    # 子월 丁火 신약(한습, 火 부족) — climate_harmful=水, climate_need=火.
    return analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin


def test_climate_need_fire_elevated_to_johu(make_pillars) -> None:
    er = _by_element(_standard(make_pillars))["火"]
    assert er.canonical_role == "한신"
    assert er.operational_role == "조후보조신"      # 한신 → 조후보조신 격상
    assert er.positive_when                        # 조후 조건문 채워짐
    assert er.note is not None
    assert "synthesized_by=climate_need" in er.note
    assert "base_model_role=희신" in er.note        # Phase 0 모델맵 역할
    assert "canonical_role=한신" in er.note


def test_climate_harmful_water_merges_with_overload(make_pillars) -> None:
    er = _by_element(_standard(make_pillars))["水"]
    assert er.operational_role == "조건부 희신/병"
    # 과다 + 한습 두 출처가 고정 순서로 병합된다.
    assert er.note is not None
    assert "synthesized_by=overload_condition+climate_harmful" in er.note
    # negative_when 에 과다 + 한습이 모두, 중복 없이.
    assert any("과다" in s for s in er.negative_when)
    assert any("한습" in s for s in er.negative_when)
    assert len(er.negative_when) == len(set(er.negative_when))


def test_neutral_month_no_johu_label(make_pillars) -> None:
    # 戊辰월(중립, _climate_harmful=None): 과다 라벨은 붙되 조후보조신은 안 붙는다(climate no-op).
    y = analyze_chart(make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.JIN),
        (Stem.GAP, Branch.JA), (Stem.SIN, Branch.YU), Stem.GAP,
    )).yongsin
    labels = {r.operational_role for r in y.operational_roles}
    assert "조후보조신" not in labels          # 중립월 → 조후 격상 없음
    assert labels & _CONDITIONAL              # 과다 조건부 라벨은 정상 부여(Phase 1 동작 유지)


def test_final_canonical_favorability_unchanged(make_pillars) -> None:
    y = _standard(make_pillars)
    assert y.final["heesin"] == "水" and y.final["hansin"] == "火"   # 정적 불변
    assert y.canonical_roles == {k: y.final[k] for k in _ROLE_KEYS}
    fav = favorability_map(SimpleNamespace(yongsin_analysis=y))  # type: ignore[arg-type]
    for key, ko in (("yongsin", "용신"), ("heesin", "희신"), ("gisin", "기신"),
                    ("gusin", "구신"), ("hansin", "한신")):
        assert fav.get(y.final[key]) == ko

"""성립 조건 SSOT — 합성 입력으로 고전 전제·검토 반례를 고정한다(2026-10-17).

반례 출처: 데굴님 검수(제살태과 '일주 의지처'는 필수 조건 아님·無印은 인극식 실질 방해로)
+ 외부 검토 2건.
"""

from __future__ import annotations

from saju_engines.pattern_conditions import (
    CONDITION_IDS,
    NATAL_CONDITION_IDS,
    ConditionInput,
    evaluate_condition,
)
from saju_engines.structure_patterns import load_structure_patterns


def _inp(band="신약", rooted=("木", "火", "土", "金", "水"), damaged=(), **tg):
    # 십성 세력(%)을 직접 지정. 미지정 십성은 0. 그룹 오행은 甲일간 기준.
    ten = {
        k: 0.0
        for k in ("비견", "겁재", "식신", "상관", "정재", "편재", "정관", "편관", "정인", "편인")
    }
    ten.update(tg)
    groups = {
        "peer": ten["비견"] + ten["겁재"],
        "resource": ten["정인"] + ten["편인"],
        "output": ten["식신"] + ten["상관"],
        "wealth": ten["정재"] + ten["편재"],
        "officer": ten["정관"] + ten["편관"],
    }
    el = {"peer": "木", "output": "火", "wealth": "土", "officer": "金", "resource": "水"}
    return ConditionInput(
        groups=groups,
        ten_gods=ten,
        band=band,
        element_of_group=el,
        damaged_groups=set(damaged),
        rooted_elements=set(rooted),
    )


def test_catalog_ids_exist_in_dictionary() -> None:
    ids = {e.pattern_id for e in load_structure_patterns().patterns}
    assert CONDITION_IDS <= ids
    assert set(NATAL_CONDITION_IDS) <= CONDITION_IDS


def test_siksin_jesal_requires_food_not_obstructed_by_yin() -> None:
    ok = evaluate_condition("SIKSIN_JESAL", _inp(편관=30, 식신=20, 정인=15))
    assert (
        ok.ok and "no_yin" not in ok.flags
    )  # 인성 15%는 식신(20%)을 압도하지 않음 → 성립(검토 사례 B)
    blocked = evaluate_condition("SIKSIN_JESAL", _inp(편관=30, 식신=20, 정인=25))
    assert not blocked.ok and "인극식 방해" in blocked.evidence[1]  # 인성이 식신을 압도(사례 C)
    small_yin = evaluate_condition("SIKSIN_JESAL", _inp(편관=30, 식신=6, 정인=8))
    assert not small_yin.ok  # 인성 8%라도 식신(6%)보다 강하면 방해(사례 D) — 10% 임계가 아님
    no_yin = evaluate_condition("SIKSIN_JESAL", _inp(편관=30, 식신=25, 정인=5))
    assert no_yin.ok and "no_yin" in no_yin.flags  # 無印은 표지일 뿐
    fed = evaluate_condition("SIKSIN_JESAL", _inp(편관=30, 식신=15, 정재=20))
    assert "wealth_feeds_killing" in fed.flags


def test_jesal_taegwa_core_is_excess_restraint_not_support_ratio() -> None:
    # 검토 사례 A: 비겁+인성 55 > 식상 30 이어도 약한 칠살(5)을 과하게 제하면 성립.
    a = evaluate_condition("JESAL_TAEGWA", _inp(비견=30, 정인=25, 식신=30, 편관=5))
    assert a.ok and "dm_lacks_support" not in a.flags
    # 검토 사례 B: 비겁+인성 10 < 식상 30 이어도 칠살 40 이 더 강하면 제살태과 아님.
    b = evaluate_condition("JESAL_TAEGWA", _inp(비견=5, 정인=5, 식신=30, 편관=40))
    assert not b.ok
    # 일주 의지처 없음은 독립 보조 표지: 무근·비겁 인성 미약일 때만.
    c = evaluate_condition(
        "JESAL_TAEGWA", _inp(비견=4, 정인=3, 식신=30, 편관=8, rooted=("火", "土", "金", "水"))
    )
    assert c.ok and "dm_lacks_support" in c.flags
    d = evaluate_condition("JESAL_TAEGWA", _inp(비견=4, 정인=20, 식신=30, 편관=8))
    assert d.ok and "dm_lacks_support" not in d.flags and "yin_restrains_output" in d.flags


def test_sanggwan_paein_needs_weak_dm_strong_sanggwan_and_unbroken_yin() -> None:
    ok = evaluate_condition("SANGGWAN_PAEIN", _inp(band="신약", 상관=25, 정인=15, 정재=5))
    assert ok.ok
    broken = evaluate_condition("SANGGWAN_PAEIN", _inp(band="신약", 상관=25, 정인=15, 정재=20))
    assert not broken.ok  # 재가 인을 깸(財壞印)
    strong = evaluate_condition("SANGGWAN_PAEIN", _inp(band="신강", 상관=25, 정인=15, 정재=5))
    assert not strong.ok  # 身稍弱 전제
    weak_sanggwan = evaluate_condition(
        "SANGGWAN_PAEIN", _inp(band="신약", 상관=12, 정인=15, 정재=5)
    )
    assert not weak_sanggwan.ok  # 상관왕 전제(20%)


def test_gwan_in_sangsaeng_blocked_by_output_or_wealth() -> None:
    ok = evaluate_condition("GWAN_IN_SANGSAENG", _inp(정관=15, 정인=20, 식신=5, 정재=5))
    assert ok.ok
    assert not evaluate_condition(
        "GWAN_IN_SANGSAENG", _inp(정관=15, 정인=20, 식신=20, 정재=5)
    ).ok  # 식상이 관을 상함
    assert not evaluate_condition(
        "GWAN_IN_SANGSAENG", _inp(정관=15, 정인=20, 식신=5, 정재=25)
    ).ok  # 재가 인을 깸


def test_jae_geugin_requires_wealth_over_resource_without_officer_bridge() -> None:
    assert evaluate_condition("JAE_GEUGIN", _inp(정재=30, 정인=15, 정관=5)).ok
    assert not evaluate_condition(
        "JAE_GEUGIN", _inp(정재=30, 정인=15, 정관=15)
    ).ok  # 관성 통관 → 재관인상생 쪽
    assert not evaluate_condition(
        "JAE_GEUGIN", _inp(정재=12, 정인=25)
    ).ok  # 재가 인보다 약하면 극 미성립


def test_saengjae_blocked_by_peer_or_resource() -> None:
    assert evaluate_condition("SANGGWAN_SAENGJAE", _inp(상관=20, 정재=25, 비견=10, 정인=10)).ok
    assert not evaluate_condition(
        "SANGGWAN_SAENGJAE", _inp(상관=20, 정재=25, 비견=30)
    ).ok  # 비겁 겁재
    assert not evaluate_condition(
        "SANGGWAN_SAENGJAE", _inp(상관=20, 정재=25, 정인=25)
    ).ok  # 인성이 상관을 누름

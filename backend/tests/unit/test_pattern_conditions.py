"""성립 조건 SSOT — 합성 입력으로 고전 전제·검토 반례를 고정한다(2026-10-17).

반례 출처: 데굴님 검수(제살태과 '일주 의지처'는 필수 조건 아님·無印은 인극식 실질 방해로)
+ 외부 검토 2건.
"""

from __future__ import annotations

from saju_engines.pattern_conditions import (
    CONDITION_IDS,
    DM_SPENDING_IDS,
    NATAL_CONDITION_IDS,
    ConditionInput,
    contribution_spec,
    dm_cannot_carry,
    evaluate_condition,
    evaluate_suhwa,
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


# ── 2026-11-13 데굴님 검수("재생관과 재생살이 관과는 무관한 대운에 의해 모두 성립") ──────────


def test_jae_saenggwan_and_saengsal_never_stand_together() -> None:
    # 정관·편관이 둘 다 10%+ 이면 강한 쪽 이름만 서고 관살혼잡 표지가 붙는다("不混七煞").
    gwan = evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=15, 편관=12))
    sal = evaluate_condition("JAE_SAENGSAL", _inp(정재=30, 정관=15, 편관=12))
    assert gwan.ok and "mixed_officer" in gwan.flags and not sal.ok
    gwan = evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=12, 편관=15))
    sal = evaluate_condition("JAE_SAENGSAL", _inp(정재=30, 정관=12, 편관=15))
    assert sal.ok and "mixed_officer" in sal.flags and not gwan.ok
    # 세력이 같으면 재생살 — 칠살이 섞인 재생관은 전제가 깨진다.
    assert not evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=12, 편관=12)).ok
    assert evaluate_condition("JAE_SAENGSAL", _inp(정재=30, 정관=12, 편관=12)).ok
    # 반례: 편관이 10% 미만이면 혼잡이 아니다 — 재생관이 표지 없이 선다.
    plain = evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=15, 편관=6))
    assert plain.ok and "mixed_officer" not in plain.flags
    # 재→정관 다리 자체(재관인상생 연쇄 판정용)는 배타 적용 전 조건으로 본다.
    leg = evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=12, 편관=15), exclusive=False)
    assert leg.ok


def test_jesal_taegwa_excludes_jesal_and_yuje() -> None:
    # 제어가 과하면 제살태과 한 줄만 — 식신제살·상관제살·관살유제를 함께 세우지 않는다.
    over = _inp(편관=12, 식신=30)
    assert evaluate_condition("JESAL_TAEGWA", over).ok
    assert not evaluate_condition("SIKSIN_JESAL", over).ok
    over2 = _inp(편관=20, 식신=25, 상관=20)
    assert evaluate_condition("JESAL_TAEGWA", over2).ok
    assert not evaluate_condition("SANGGWAN_JESAL", over2).ok
    assert not evaluate_condition("GWANSAL_YUJE", over2).ok
    # 반례: 식상이 편관의 2배 미만이면 제살태과가 아니고 식신제살이 선다.
    fit = _inp(편관=12, 식신=20)
    assert not evaluate_condition("JESAL_TAEGWA", fit).ok
    assert evaluate_condition("SIKSIN_JESAL", fit).ok


def test_gwansal_yuje_is_output_control_between_light_and_excess() -> None:
    # 制 = 식상. 관살 30% 에 식상 20%(절반 이상·2배 미만)이면 유제.
    assert evaluate_condition("GWANSAL_YUJE", _inp(정관=15, 편관=15, 식신=20)).ok
    # 종전에는 인성만 있어도 성립했다 — 인성은 化(살인상생·살중용인)라 유제가 아니다.
    assert not evaluate_condition("GWANSAL_YUJE", _inp(정관=15, 편관=15, 정인=20)).ok
    # 식상이 관살의 절반 미만이면 制輕 — 살중제경 쪽.
    light = _inp(정관=15, 편관=15, 식신=12)
    assert not evaluate_condition("GWANSAL_YUJE", light).ok
    assert evaluate_condition("SALJUNG_JEGYEONG", light).ok
    # 인성이 식상을 압도하면 제어 불성(인극식), 식상 무근이어도 불성.
    assert not evaluate_condition("GWANSAL_YUJE", _inp(정관=15, 편관=15, 식신=20, 정인=25)).ok
    rootless = _inp(정관=15, 편관=15, 식신=20, rooted=("木", "土", "金", "水"))
    assert not evaluate_condition("GWANSAL_YUJE", rootless).ok
    # 재가 식상보다 크면 표지("財能轉食生煞").
    fed = evaluate_condition("GWANSAL_YUJE", _inp(정관=15, 편관=15, 식신=20, 정재=25))
    assert fed.ok and "wealth_feeds_killing" in fed.flags


def test_transformed_strength_counts_for_group_legs_only() -> None:
    # 化 세력은 groups 에만 있다: 관성 그룹 25% 인데 실제 글자는 정관 5%·편관 0%.
    inp = _inp(정재=30, 정관=5)
    inp.groups["officer"] = 25.0
    assert inp.group(["정관", "편관"]) == 25.0  # 그룹 전체 다리 = 化 포함
    assert inp.group(["정관"]) == 5.0 and inp.group(["편관"]) == 0.0  # 정·편 지정 다리 = 글자만
    assert not evaluate_condition("JAE_SAENGGWAN", inp).ok
    assert not evaluate_condition("JAE_SAENGSAL", inp).ok
    # 반례: 같은 세력이 실제 정관 글자면 재생관이 선다.
    assert evaluate_condition("JAE_SAENGGWAN", _inp(정재=30, 정관=25)).ok


def test_evaluate_suhwa_shared_by_natal_and_transit() -> None:
    assert evaluate_suhwa(20.0, 25.0, set()) == (True, False)
    assert evaluate_suhwa(20.0, 12.0, set()) == (False, False)  # 기제도 미제도 아닌 구간
    assert evaluate_suhwa(45.0, 12.0, set()) == (False, True)  # 차 30 이상
    assert evaluate_suhwa(20.0, 6.0, {"火"}) == (False, True)  # 한쪽 결핍
    assert evaluate_suhwa(20.0, 0.0, {"火"}) == (False, False)  # 한쪽이 아예 없으면 대상 아님


def test_contribution_spec_legs_blockers_and_veto() -> None:
    gwan = contribution_spec("JAE_SAENGGWAN")
    assert ("정관",) in gwan.legs and gwan.blockers == {"peer", "output"}
    taegwa = contribution_spec("JESAL_TAEGWA")
    assert taegwa.veto == {"편관"}  # 살을 보태는 운은 제살태과의 신규 성립이 아니다
    assert contribution_spec("SANGGWAN_GYEONGWAN").blockers == frozenset()
    assert contribution_spec("SUHWA_GIJE") is None  # 조건 SSOT 범위 밖(운 판정 모듈이 정의)


# ── 2026-11-13 (2) 데굴님 검수("식상생재는 일간의 힘이 필요 … 내 경우에는 신약 사주") ─────────


def test_weak_dm_flag_marks_dm_spending_patterns_in_frail_charts() -> None:
    # 신약·태신약 원국: 구조(局)는 서되 '감당 부족' 표지가 항상 붙는다("身輕則喜幫身").
    frail = evaluate_condition("SIKSANG_SAENGJAE", _inp(band="신약", 식신=20, 정재=25))
    assert frail.ok and "weak_dm" in frail.flags
    assert dm_cannot_carry("SIKSANG_SAENGJAE", "태신약")
    # 조건부 `burden`(식상+재 50%+)과 겹치면 신약형 표지 하나만 남긴다.
    heavy = evaluate_condition("SIKSANG_SAENGJAE", _inp(band="신약", 식신=25, 정재=30))
    assert "weak_dm" in heavy.flags and "burden" not in heavy.flags
    # 반례 1: 중화신약은 받침이 있는 쪽 — 표지 없음(50%+ 이면 종전대로 burden).
    mid = evaluate_condition("SIKSANG_SAENGJAE", _inp(band="중화신약", 식신=25, 정재=30))
    assert "weak_dm" not in mid.flags and "burden" in mid.flags
    # 반례 2: 신강은 표지 없음.
    assert "weak_dm" not in evaluate_condition(
        "SIKSANG_SAENGJAE", _inp(band="신강", 식신=20, 정재=25)
    ).flags
    # 반례 3: 재생살은 신약이 본래 자리라 대상이 아니다. 제살 계열은 대상이다.
    assert "weak_dm" not in evaluate_condition(
        "JAE_SAENGSAL", _inp(band="신약", 정재=30, 편관=15)
    ).flags
    assert "weak_dm" in evaluate_condition(
        "SIKSIN_JESAL", _inp(band="신약", 편관=20, 식신=20)
    ).flags
    assert DM_SPENDING_IDS <= CONDITION_IDS

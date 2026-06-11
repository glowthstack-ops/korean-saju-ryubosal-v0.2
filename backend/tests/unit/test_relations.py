"""합충형파해 constant tables and relation detection."""

from __future__ import annotations

from saju_manse_core.relations import detect
from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_HARMS,
    SELF_PUNISHMENT,
    SIX_COMBINATIONS,
    THREE_HARMONY,
)
from saju_shared_types.enums import Branch, Stem


def test_relation_tables() -> None:
    assert frozenset({Branch.JA, Branch.O}) in BRANCH_CLASHES
    assert frozenset({Branch.SIN, Branch.HAE}) in BRANCH_HARMS
    assert frozenset({Branch.JA, Branch.CHUK}) in SIX_COMBINATIONS
    assert SIX_COMBINATIONS[frozenset({Branch.JIN, Branch.YU})].value == "金"  # 辰酉合金
    assert Branch.HAE in SELF_PUNISHMENT
    members, _element, royal = THREE_HARMONY[1]  # 寅午戌 → 火, 왕지 午
    assert {Branch.IN, Branch.O, Branch.SUL} == set(members)
    assert royal is Branch.O


def test_detect_clash_and_three_harmony(make_pillars) -> None:
    # 寅午戌 삼합(火) + 子午 충 between year(子) and day(午).
    pillars = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.BYEONG, Branch.IN),
        (Stem.BYEONG, Branch.O), (Stem.MU, Branch.SUL), Stem.BYEONG,
    )
    rels = detect(pillars)
    types = {(r.rel_type, frozenset(r.members)) for r in rels}
    assert ("clash", frozenset({"子", "午"})) in types
    assert any(r.rel_type == "three_harmony" and r.transform_element == "火" for r in rels)


def test_insashin_requires_day_branch(make_pillars) -> None:
    # 寅(년)·巳(월)·申(시)로 3글자가 모여도 일지가 子(인사신 글자 아님)면 삼형 미성립.
    no_day = make_pillars(
        (Stem.GAP, Branch.IN), (Stem.EUL, Branch.SA),
        (Stem.GAP, Branch.JA), (Stem.GAP, Branch.SIN), Stem.GAP,
    )
    assert not any("삼형" in r.notes for r in detect(no_day))

    # 일지를 申으로 옮기면(일지 포함) 인사신 삼형 성립.
    with_day = make_pillars(
        (Stem.GAP, Branch.IN), (Stem.EUL, Branch.SA),
        (Stem.GAP, Branch.SIN), (Stem.GAP, Branch.JA), Stem.GAP,
    )
    assert any("삼형" in r.notes for r in detect(with_day))


def test_jisejihyeong_position_independent(make_pillars) -> None:
    # 축술미는 위치 무관: 丑(년)·戌(월) 2글자만으로도(일지·시지 무관) 삼형 성립.
    pillars = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GAP, Branch.SUL),
        (Stem.GAP, Branch.JA), (Stem.GAP, Branch.O), Stem.GAP,
    )
    assert any("삼형" in r.notes for r in detect(pillars))


def test_murye_punishment_requires_adjacency(make_pillars) -> None:
    # 子卯가 연-월(인접) → 무례지형 성립.
    adj = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.EUL, Branch.MYO),
        (Stem.GAP, Branch.O), (Stem.GAP, Branch.SIN), Stem.GAP,
    )
    assert any("무례지형" in r.notes for r in detect(adj))

    # 子(연)·卯(일)로 격각(연-일, 가운데 글자) → 무례지형 미성립.
    apart = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.GAP, Branch.IN),
        (Stem.EUL, Branch.MYO), (Stem.GAP, Branch.SIN), Stem.EUL,
    )
    assert not any("무례지형" in r.notes for r in detect(apart))


def test_self_punishment_remains_position_independent(make_pillars) -> None:
    # 자형은 위치 무관: 亥(연)·亥(일)로 격각이어도 성립.
    pillars = make_pillars(
        (Stem.EUL, Branch.HAE), (Stem.GAP, Branch.JA),
        (Stem.EUL, Branch.HAE), (Stem.GAP, Branch.SIN), Stem.EUL,
    )
    assert any(r.rel_type == "self_punishment" for r in detect(pillars))


def test_detect_self_punishment_and_gan_yeo_ji_dong(make_pillars) -> None:
    # 亥亥 자형 + 庚申 간여지동(金).
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.GI, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.GAP, Branch.JA), Stem.GI,
    )
    rels = detect(pillars)
    assert any(r.rel_type == "self_punishment" and r.members == ["亥", "亥"] for r in rels)
    assert any(r.rel_type == "gan_yeo_ji_dong" and "庚" in r.members for r in rels)
    assert any(r.rel_type == "branch_duplication" for r in rels)


def test_detect_hidden_stem_combinations(make_pillars) -> None:
    # 戊 천간 + 子중癸 → 戊癸暗合(火), 지장간끼리도 보조 신호로 잡는다.
    pillars = make_pillars(
        (Stem.MU, Branch.JA), (Stem.GAP, Branch.IN),
        (Stem.BYEONG, Branch.SIN), (Stem.EUL, Branch.YU), Stem.BYEONG,
    )
    rels = detect(pillars)
    assert any(
        r.rel_type == "hidden_stem_combination"
        and "戊" in r.members
        and "子:癸" in r.members
        and r.transform_element == "火"
        for r in rels
    )
    assert any(r.rel_type == "hidden_hidden_combination" for r in rels)

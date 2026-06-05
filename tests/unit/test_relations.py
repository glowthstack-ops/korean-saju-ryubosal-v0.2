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

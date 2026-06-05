"""Constant-table invariants and ten-god / naeum / gongmang correctness."""

from __future__ import annotations

import pytest

from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_shared_types.constants import (
    BRANCHES,
    NAEUM,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, TenGod


@pytest.mark.parametrize("branch", BRANCHES)
def test_hidden_stem_weights_sum_to_one(branch: Branch) -> None:
    total = sum(w for _, _, w in hidden_stems_for(branch))
    assert total == pytest.approx(1.0)


def test_ten_god_against_gi_day_master() -> None:
    # 己土(음) day master, verified against codex §18 example.
    assert ten_god(Stem.GI, Stem.GYEONG) is TenGod.SANGGWAN  # 土生金, 음→양
    assert ten_god(Stem.GI, Stem.JEONG) is TenGod.PYEONIN  # 火生土, 음음
    assert ten_god(Stem.GI, Stem.GI) is TenGod.BIGYEON  # 동일 土 음음
    assert ten_god(Stem.GI, Stem.MU) is TenGod.GEOMJAE  # 동일 土 음양
    assert ten_god(Stem.GI, Stem.IM) is TenGod.JEONGJAE  # 土克水, 음양
    assert ten_god(Stem.GI, Stem.GAP) is TenGod.JEONGGWAN  # 木克土, 음양


def test_naeum_known_pairs() -> None:
    assert NAEUM[(Stem.GAP, Branch.JA)] == "해중금"
    assert NAEUM[(Stem.GYEONG, Branch.SIN)] == "석류목"  # 庚申
    assert NAEUM[(Stem.IM, Branch.SUL)] == "대해수"  # 壬戌


def test_gongmang_formula() -> None:
    # 甲子旬 → 戌亥 ; 己亥(甲午旬) → 辰巳
    assert gongmang_branches(Stem.GAP, Branch.JA) == [Branch.SUL, Branch.HAE]
    assert gongmang_branches(Stem.GI, Branch.HAE) == [Branch.JIN, Branch.SA]

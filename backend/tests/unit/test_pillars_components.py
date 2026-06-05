"""12운성 and 둔시법 hour-stem correctness."""

from __future__ import annotations

from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.enums import Branch, Stem


def test_twelve_unseong_gi() -> None:
    # 己(음토) 장생 at 酉, 역행: 巳 = 제왕, 亥 = 태
    assert twelve_unseong(Stem.GI, Branch.SA) == "제왕"
    assert twelve_unseong(Stem.GI, Branch.YU) == "장생"
    assert twelve_unseong(Stem.GI, Branch.HAE) == "태"


def test_twelve_unseong_gap() -> None:
    # 甲(양목) 장생 at 亥, 순행
    assert twelve_unseong(Stem.GAP, Branch.HAE) == "장생"
    assert twelve_unseong(Stem.GAP, Branch.O) == "사"


def test_hour_stem_dunsi() -> None:
    # 甲己日 → 甲子時 ; 己日 巳時 → 己巳
    assert hour_pillar_for_branch(Stem.GI, Branch.JA) == (Stem.GAP, Branch.JA)
    assert hour_pillar_for_branch(Stem.GI, Branch.SA) == (Stem.GI, Branch.SA)
    # 己日 辰時 → 戊辰 (true-solar case in the fixture)
    assert hour_pillar_for_branch(Stem.GI, Branch.JIN) == (Stem.MU, Branch.JIN)

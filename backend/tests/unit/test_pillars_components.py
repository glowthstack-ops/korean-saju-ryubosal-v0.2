"""12운성 and 둔시법 hour-stem correctness."""

from __future__ import annotations

from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import hidden_stems_for
from saju_shared_types.enums import Branch, Stem

# 지장간 글자 + 본/중/여 분배 비율(사용자 지정). 3지장간 0.2/0.2/0.6,
# 왕지(子卯酉) 0.3/0.7, 午 0.3/0.2/0.5. 합 = 1.0.
_EXPECTED_HIDDEN: dict[str, list[tuple[str, float]]] = {
    "子": [("壬", 0.30), ("癸", 0.70)],
    "丑": [("癸", 0.20), ("辛", 0.20), ("己", 0.60)],
    "寅": [("戊", 0.20), ("丙", 0.20), ("甲", 0.60)],
    "卯": [("甲", 0.30), ("乙", 0.70)],
    "辰": [("乙", 0.20), ("癸", 0.20), ("戊", 0.60)],
    "巳": [("戊", 0.20), ("庚", 0.20), ("丙", 0.60)],
    "午": [("丙", 0.30), ("己", 0.20), ("丁", 0.50)],
    "未": [("丁", 0.20), ("乙", 0.20), ("己", 0.60)],
    "申": [("戊", 0.20), ("壬", 0.20), ("庚", 0.60)],
    "酉": [("庚", 0.30), ("辛", 0.70)],
    "戌": [("辛", 0.20), ("丁", 0.20), ("戊", 0.60)],
    "亥": [("戊", 0.20), ("甲", 0.20), ("壬", 0.60)],
}


def test_hidden_stem_table_matches_standard() -> None:
    # 회귀 락: 지장간 글자 + 본/중/여 분배 비율을 고정. budget 합은 항상 1.0.
    for branch in Branch:
        hs = [(str(s), round(w, 2)) for s, _t, w in hidden_stems_for(branch)]
        assert hs == _EXPECTED_HIDDEN[str(branch)], str(branch)
        assert round(sum(w for _s, w in hs), 6) == 1.0, str(branch)


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

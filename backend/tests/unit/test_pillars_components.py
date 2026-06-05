"""12운성 and 둔시법 hour-stem correctness."""

from __future__ import annotations

from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import hidden_stems_for
from saju_shared_types.enums import Branch, Stem

# 표준 지장간 (여기→중기→정기 순). 왕지(子卯酉)는 여기+정기 2개, 나머지는 3개.
_EXPECTED_HIDDEN: dict[str, list[str]] = {
    "子": ["壬", "癸"], "丑": ["癸", "辛", "己"], "寅": ["戊", "丙", "甲"],
    "卯": ["甲", "乙"], "辰": ["乙", "癸", "戊"], "巳": ["戊", "庚", "丙"],
    "午": ["丙", "己", "丁"], "未": ["丁", "乙", "己"], "申": ["戊", "壬", "庚"],
    "酉": ["庚", "辛"], "戌": ["辛", "丁", "戊"], "亥": ["戊", "甲", "壬"],
}


def test_hidden_stem_table_matches_standard() -> None:
    # 회귀 락: 지장간 표 오류(예: 亥 여기 戊 누락) 재발 방지. budget 합은 항상 1.0.
    for branch in Branch:
        hs = hidden_stems_for(branch)
        assert [str(s) for s, _t, _w in hs] == _EXPECTED_HIDDEN[str(branch)], str(branch)
        assert round(sum(w for _s, _t, w in hs), 6) == 1.0, str(branch)


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

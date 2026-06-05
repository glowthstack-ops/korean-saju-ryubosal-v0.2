"""12운성 and 둔시법 hour-stem correctness."""

from __future__ import annotations

from saju_manse_core.pillars.hour_pillar import hour_pillar_for_branch
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import hidden_stem_days, hidden_stems_for
from saju_shared_types.enums import Branch, Stem

# 표준 지장간 + 월률분야 일수(여기→중기→정기, 합=30).
# 생지 寅申巳亥=7:7:16 / 고지 辰戌丑未=9:3:18 / 왕지 子卯酉=10:20 / 午(예외)=10:10:10.
_EXPECTED_DAYS: dict[str, list[tuple[str, int]]] = {
    "子": [("壬", 10), ("癸", 20)],
    "丑": [("癸", 9), ("辛", 3), ("己", 18)],
    "寅": [("戊", 7), ("丙", 7), ("甲", 16)],
    "卯": [("甲", 10), ("乙", 20)],
    "辰": [("乙", 9), ("癸", 3), ("戊", 18)],
    "巳": [("戊", 7), ("庚", 7), ("丙", 16)],
    "午": [("丙", 10), ("己", 10), ("丁", 10)],
    "未": [("丁", 9), ("乙", 3), ("己", 18)],
    "申": [("戊", 7), ("壬", 7), ("庚", 16)],
    "酉": [("庚", 10), ("辛", 20)],
    "戌": [("辛", 9), ("丁", 3), ("戊", 18)],
    "亥": [("戊", 7), ("甲", 7), ("壬", 16)],
}


def test_hidden_stem_table_matches_standard() -> None:
    # 회귀 락: 지장간 글자 구성 + 월률분야 일수(비율)까지 고정. budget 합은 항상 1.0.
    for branch in Branch:
        days = hidden_stem_days(branch)
        assert [(str(s), d) for s, _t, d in days] == _EXPECTED_DAYS[str(branch)], str(branch)
        assert sum(d for _s, _t, d in days) == 30, str(branch)
        # budget = 일수/30, 합 = 1.0.
        assert round(sum(w for _s, _t, w in hidden_stems_for(branch)), 6) == 1.0, str(branch)


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

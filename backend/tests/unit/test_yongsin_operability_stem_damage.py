"""용신 작동성 #6c — 투출 천간 자리 손상 (2026-10-08 데굴님 승인, shadow·기본 OFF).

중복 차단: 좌하 지지가 용신 통근이면 #6a 담당(③④ 미적용), 같은 인접 천간이 충이면 극은 미적용,
합반(#6b-2) 적용 시 천간 관계 인자 미적용. 복수 투출: penalty × (손상 자리/투출 자리).
규격: doc/v2_2/YONGSIN_STEM_DAMAGE_PROPOSAL.md §6
"""

from __future__ import annotations

import pytest
from saju_manse_analysis.yongsin import candidates as cand
from saju_manse_analysis.yongsin.candidates import (
    _compute_yongsin_operability,
    _yongsin_stem_damage_factors,
)
from saju_manse_analysis.yongsin.operational_role_config import (
    OPERABILITY_FACTOR_SHORT,
    OPERABILITY_PENALTY,
)

from saju_shared_types.enums import Branch, Stem

# 일간 甲·일주 甲子 → 공망 戌亥. 용신 火(丙/丁) 투출 자리를 바꿔 가며 검사한다(60갑자 음양 짝 준수).
_DM = Stem.GAP
_DAY = (Stem.GAP, Branch.JA)
_H = (Stem.GI, Branch.CHUK)  # 중립 시주(己丑: 土, 火 통근 없음)


def _factors(make_pillars, year, month, hour=_H, yongsin="火", bound=False):
    p = make_pillars(year, month, _DAY, hour, _DM)
    assert set(p.gongmang_branches) == {"戌", "亥"}
    return dict(_yongsin_stem_damage_factors(yongsin, p, bound)), p


def test_seat_void_only_when_seat_not_rooted(make_pillars) -> None:
    """丁亥(亥 공망·火 통근 없음) → 좌하공망. 丙戌(戌 공망이나 丁 통근) → #6a 담당, 미적용."""
    f, _ = _factors(make_pillars, (Stem.JEONG, Branch.HAE), (Stem.GI, Branch.CHUK))
    assert f.get("yongsin_seat_void") == OPERABILITY_PENALTY["yongsin_seat_void"]
    f2, _ = _factors(make_pillars, (Stem.BYEONG, Branch.SUL), (Stem.GI, Branch.CHUK))
    assert "yongsin_seat_void" not in f2


def test_seat_clash_only_when_seat_not_rooted(make_pillars) -> None:
    """丙申 + 寅(申寅 충, 申에 火 통근 없음) → 좌하충. 丙午(午子 충이나 丁 통근) → 미적용(#6a)."""
    f, _ = _factors(make_pillars, (Stem.BYEONG, Branch.SIN), (Stem.GYEONG, Branch.IN))
    assert f.get("yongsin_seat_clash") == OPERABILITY_PENALTY["yongsin_seat_clash"]
    f2, _ = _factors(make_pillars, (Stem.BYEONG, Branch.O), (Stem.GI, Branch.CHUK))
    assert "yongsin_seat_clash" not in f2


def test_stem_clash_suppresses_controlled_for_same_neighbor(make_pillars) -> None:
    """월간 丙 옆 년간 壬: 丙壬 충이자 水克火 → 천간충 1회만. 년간 癸면 극만."""
    f, _ = _factors(make_pillars, (Stem.IM, Branch.IN), (Stem.BYEONG, Branch.IN))
    assert "yongsin_stem_clash" in f and "yongsin_stem_controlled" not in f
    f2, _ = _factors(make_pillars, (Stem.GYE, Branch.MYO), (Stem.BYEONG, Branch.IN))
    assert "yongsin_stem_controlled" in f2 and "yongsin_stem_clash" not in f2


def test_bound_suppresses_stem_relation_factors(make_pillars) -> None:
    """합반(#6b-2) 적용 시 천간 관계 인자는 미적용(같은 층 1개만), 좌하 인자는 유지."""
    f, _ = _factors(make_pillars, (Stem.IM, Branch.IN), (Stem.JEONG, Branch.HAE), bound=True)
    assert "yongsin_stem_clash" not in f and "yongsin_stem_controlled" not in f
    assert "yongsin_seat_void" in f
    f2, _ = _factors(make_pillars, (Stem.IM, Branch.IN), (Stem.JEONG, Branch.HAE), bound=False)
    assert "yongsin_stem_controlled" in f2  # 壬(水)克丁(火), 丁壬은 충 쌍 아님


def test_multiple_seats_scale_by_damaged_ratio(make_pillars) -> None:
    """丁亥(공망 비통근) + 丙寅(寅 丙 통근, 정상) 두 자리 → 좌하공망 0.10 × 1/2."""
    f, _ = _factors(make_pillars, (Stem.JEONG, Branch.HAE), (Stem.GI, Branch.CHUK),
                    hour=(Stem.BYEONG, Branch.IN))
    assert f.get("yongsin_seat_void") == round(OPERABILITY_PENALTY["yongsin_seat_void"] / 2, 4)


def test_flag_off_keeps_bytes_and_flag_on_applies(make_pillars, monkeypatch) -> None:
    _, p = _factors(make_pillars, (Stem.JEONG, Branch.HAE), (Stem.GI, Branch.CHUK))
    assert cand.YONGSIN_STEM_DAMAGE_ENABLED is False
    off_op, off_f, _ = _compute_yongsin_operability("火", p, "水", {})
    assert not any(k.startswith(("yongsin_seat", "yongsin_stem")) for k in off_f)
    monkeypatch.setattr(cand, "YONGSIN_STEM_DAMAGE_ENABLED", True)
    on_op, on_f, reasons = _compute_yongsin_operability("火", p, "水", {})
    assert "yongsin_seat_void" in on_f and on_op < off_op
    assert on_op == round(off_op * (1 - OPERABILITY_PENALTY["yongsin_seat_void"]), 4)
    assert OPERABILITY_FACTOR_SHORT["yongsin_seat_void"] == "좌하공망"
    assert any("공망" in r for r in reasons)


@pytest.mark.parametrize("key", ["yongsin_stem_clash", "yongsin_stem_controlled",
                                 "yongsin_seat_void", "yongsin_seat_clash"])
def test_config_entries_present(key: str) -> None:
    assert OPERABILITY_PENALTY[key] == 0.10 and key in OPERABILITY_FACTOR_SHORT

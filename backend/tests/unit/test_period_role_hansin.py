"""시점 극성(_period_role)과 한신 생(生) 간접 길흉(_han_gen_role) 검증.

길흉은 용신/기신 오행이 우선이며(직접 역할, 천간>지지), 직접 역할이 없을 때만 한신이 생(生)하는
대상으로 약한 길/흉을 판정한다(사용자 확정 규칙). 직접 신호를 간접 신호가 덮지 않는다.
"""

from __future__ import annotations

from saju_engines.event_engine_v2 import _han_gen_role, _period_role
from saju_shared_types.event_engine import PolarityRole
from saju_shared_types.luck import LuckPillar


def _lp(stem: str, branch: str) -> LuckPillar:
    return LuckPillar(
        label="2026", period_type="year", ganji=stem + branch,
        stem=stem, branch=branch, stem_ten_god="비견", branch_ten_god="비견",
    )


# ── _han_gen_role: 한신 오행 → 생하는 대상의 역할로 약한 길/흉 ──────────────


def test_han_gen_good() -> None:
    """木(한신)이 생하는 火가 용신이면 약한 길(HAN_GOOD)."""
    assert _han_gen_role("木", {"木": "한신", "火": "용신"}) is PolarityRole.HAN_GOOD


def test_han_gen_good_when_generated_heesin() -> None:
    assert _han_gen_role("木", {"木": "한신", "火": "희신"}) is PolarityRole.HAN_GOOD


def test_han_gen_bad() -> None:
    """木(한신)이 생하는 火가 기신이면 약한 흉(HAN_BAD)."""
    assert _han_gen_role("木", {"木": "한신", "火": "기신"}) is PolarityRole.HAN_BAD


def test_han_gen_bad_when_generated_gusin() -> None:
    """구신은 기신과 같은 흉 계열(GI) — 한신이 구신을 생해도 약한 흉."""
    assert _han_gen_role("木", {"木": "한신", "火": "구신"}) is PolarityRole.HAN_BAD


def test_han_gen_none_when_not_hansin() -> None:
    """대상 오행이 한신이 아니면 간접 판정 안 함(None)."""
    assert _han_gen_role("木", {"木": "용신", "火": "기신"}) is None


def test_han_gen_none_when_generated_neutral() -> None:
    """한신이 생하는 대상도 한신/무관이면 중립(None)."""
    assert _han_gen_role("木", {"木": "한신", "火": "한신"}) is None


# ── _period_role: 직접(용·희·기·구, 천간>지지) 우선, 한신 생은 보조 ──────────


def test_direct_role_wins_over_indirect() -> None:
    """천간 木(한신→火 용신, 약길)이라도 지지 水(기신, 직접)가 있으면 직접 흉이 우선."""
    fav = {"木": "한신", "火": "용신", "水": "기신"}
    assert _period_role(_lp("甲", "子"), fav) is PolarityRole.GI


def test_indirect_good_when_no_direct() -> None:
    """천간·지지 모두 한신(직접 역할 없음)일 때만 생(生) 관계로 약한 길."""
    fav = {"木": "한신", "火": "용신"}
    assert _period_role(_lp("甲", "寅"), fav) is PolarityRole.HAN_GOOD


def test_indirect_bad_when_no_direct() -> None:
    fav = {"木": "한신", "火": "기신"}
    assert _period_role(_lp("甲", "寅"), fav) is PolarityRole.HAN_BAD


def test_stem_priority_for_indirect() -> None:
    """간접끼리도 천간 우선 — 천간 木(→火 용신, 길) vs 지지 金(→水 기신, 흉) → 길."""
    fav = {"木": "한신", "火": "용신", "金": "한신", "水": "기신"}
    assert _period_role(_lp("甲", "申"), fav) is PolarityRole.HAN_GOOD


def test_neutral_when_no_signal() -> None:
    """직접·간접 모두 해당 없음 → 중립."""
    assert _period_role(_lp("甲", "寅"), {}) is PolarityRole.NEUTRAL

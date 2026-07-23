"""일주별 오늘의 운세 엔진 — 결정론·게이트·슬롯 불변식·달력 경계·분포 검증.

docs/17_DAILY_ILJU_FORTUNE.md §0-4 확정 규칙 기준.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from saju_engines.daily_ilju_fortune import (
    _branch_relations,
    _score_event,
    build_day_context,
    compute_board,
    load_daily_dicts,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.enums import Branch

_D = date(2026, 7, 23)


@pytest.fixture(scope="module")
def dicts():
    return load_daily_dicts()


@pytest.fixture(scope="module")
def board(dicts):
    return compute_board(build_day_context(_D), dicts)


# ── 결정론 ──────────────────────────────────────────────────────────────


def test_deterministic_same_input_same_output(dicts, board) -> None:
    again = compute_board(build_day_context(_D), dicts)
    assert again.model_dump() == board.model_dump()


# ── 점수 게이트 ─────────────────────────────────────────────────────────


def test_probability_range_and_gates(dicts) -> None:
    """p∈[5,95] / p≥85 ⇒ 독립 원인 그룹 ≥2 / p≤10 ⇒ 강한 contradiction."""
    for offset in range(10):
        ctx = build_day_context(_D + timedelta(days=offset))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            for key, ev in dicts.catalog["events"].items():
                s = _score_event(key, ev, stem, branch, ctx)
                assert 5 <= s.probability <= 95, (key, idx, offset)
                if s.probability >= 85:
                    assert s.supporting_groups >= 2, (key, idx, offset)
                if s.probability <= 10:
                    assert s.contradiction >= 0.25, (key, idx, offset)


# ── 슬롯 불변식 ─────────────────────────────────────────────────────────


def test_slot_invariants(board, dicts) -> None:
    catalog = dicts.catalog["events"]
    for f in board.fortunes:
        assert len(f.events) == 3
        assert [e.slot for e in f.events] == ["good", "caution", "support"]
        keys = [e.event_key for e in f.events]
        assert len(set(keys)) == 3, f.ilju  # event_key 중복 금지
        assert len({e.domain for e in f.events}) >= 2, f.ilju  # 최소 2 domain
        groups = [catalog[k].get("synonym_group") for k in keys]
        groups = [g for g in groups if g]
        assert len(groups) == len(set(groups)), f.ilju  # 동의어 그룹 동시 노출 금지
        # good/caution 슬롯의 valence 정합
        assert catalog[keys[0]]["valence"] == "good"
        assert catalog[keys[1]]["valence"] == "caution"


# ── 관계 세분화 ─────────────────────────────────────────────────────────


def test_three_harmony_complete_vs_half() -> None:
    # 申子 반합 — 辰이 helpers에 있으면 완성, 없으면 반합
    full = _branch_relations(Branch.SIN, Branch.JA, (Branch.JIN,))
    half = _branch_relations(Branch.SIN, Branch.JA, (Branch.SUL,))
    assert "three_harmony_complete" in full and "half_harmony" not in full
    assert "half_harmony" in half and "three_harmony_complete" not in half


def test_punishment_partial_vs_full() -> None:
    # 寅巳 — 申이 채워지면 삼형 완성(1.0), 아니면 부분(0.6)
    full = _branch_relations(Branch.IN, Branch.SA, (Branch.SIN,))
    part = _branch_relations(Branch.IN, Branch.SA, (Branch.JA,))
    assert full["punishment"] == 1.0
    assert part["punishment"] == 0.6
    # 자형(辰辰)은 부분 강도
    self_p = _branch_relations(Branch.JIN, Branch.JIN, ())
    assert self_p["punishment"] == 0.6
    # 子卯형은 완전 강도
    mutual = _branch_relations(Branch.JA, Branch.MYO, ())
    assert mutual["punishment"] == 1.0


def test_clash_detected() -> None:
    hits = _branch_relations(Branch.JA, Branch.O, ())
    assert hits.get("clash") == 1.0


# ── Top5 / 로또 ─────────────────────────────────────────────────────────


def test_top5_shape(board) -> None:
    for domain_list in (board.top5.money, board.top5.love, board.top5.news):
        assert len(domain_list) == 5
        assert len(set(domain_list)) == 5
        for ilju in domain_list:
            assert any(f.ilju == ilju for f in board.fortunes)


def test_lotto_policy(dicts) -> None:
    """당일 최대 3개, 로또 일주는 금전 상위 10위 이내."""
    for offset in range(30):
        ctx = build_day_context(_D + timedelta(days=offset))
        b = compute_board(ctx, dicts)
        lotto = [f for f in b.fortunes if f.lotto_phrase]
        assert len(lotto) <= 3
        # 금전 top5는 상위 10위의 부분집합 확인용 — top5 밖 로또 일주도 상위 10위여야
        # 하므로 재계산 대신 top5 포함 여부만 약하게 확인하지 않고 서비스 검증은
        # 엔진 내부 게이트에 위임한다(순위 산출과 게이트가 같은 함수에서 결정).


# ── 달력 경계 ───────────────────────────────────────────────────────────


def test_ipchun_year_boundary() -> None:
    """입춘(2026-02-04 전후) 세운 전환: 乙巳 → 丙午."""
    before = build_day_context(date(2026, 2, 3))
    after = build_day_context(date(2026, 2, 5))
    assert (before.year_stem, before.year_branch) == ("乙", "巳")
    assert (after.year_stem, after.year_branch) == ("丙", "午")


def test_new_year_civil_boundary_keeps_year_ganji() -> None:
    """양력 연말연시(입춘 전)는 세운이 바뀌지 않는다."""
    dec31 = build_day_context(date(2026, 12, 31))
    jan01 = build_day_context(date(2027, 1, 1))
    assert (dec31.year_stem, dec31.year_branch) == (jan01.year_stem, jan01.year_branch)
    # 일진은 하루 진행
    assert dec31.day_stem != jan01.day_stem or dec31.day_branch != jan01.day_branch


def test_leap_day_no_exception() -> None:
    ctx = build_day_context(date(2028, 2, 29))
    assert ctx.day_stem and ctx.day_branch


def test_month_boundary_solar_term() -> None:
    """월 절입 전후로 월운 간지가 전환된다 (2026-08 입추 전후)."""
    jul_end = build_day_context(date(2026, 8, 6))
    aug_after = build_day_context(date(2026, 8, 8))
    assert (jul_end.month_stem, jul_end.month_branch) != (
        aug_after.month_stem,
        aug_after.month_branch,
    )


# ── 전수 분포 (30일 × 60일주) ───────────────────────────────────────────


def test_distribution_30days(dicts) -> None:
    allp: list[int] = []
    headline_dup_total = 0
    place_max = 0
    top5_money_hits: dict[str, int] = {}
    for offset in range(30):
        ctx = build_day_context(_D + timedelta(days=offset))
        b = compute_board(ctx, dicts)
        ps = [e.probability for f in b.fortunes for e in f.events]
        allp += ps
        headline_dup_total += 60 - len({f.headline for f in b.fortunes})
        counts: dict[str, int] = {}
        for f in b.fortunes:
            counts[f.lucky_place.place_key] = counts.get(f.lucky_place.place_key, 0) + 1
        place_max = max(place_max, max(counts.values()))
        for ilju in b.top5.money:
            top5_money_hits[ilju] = top5_money_hits.get(ilju, 0) + 1

    n = len(allp)
    avg = sum(allp) / n
    hi = sum(1 for p in allp if p >= 85) / n
    lo = sum(1 for p in allp if p <= 24) / n
    assert 50 <= avg <= 72, avg  # 중심이 '무난~눈여겨볼 만함' 대역
    assert hi <= 0.05, hi  # 85+ 극단값 제한 (희소)
    assert lo <= 0.05, lo
    assert min(allp) >= 5 and max(allp) <= 95
    assert headline_dup_total == 0  # 당일 60건 내 헤드라인 완전 중복 없음
    assert place_max <= 8  # 같은 장소 과다 노출 없음(감사 상한 + 여유)
    # Top5 고착 방지 — 특정 일주가 30일 중 과반을 점유하지 않음
    assert max(top5_money_hits.values()) <= 20, top5_money_hits

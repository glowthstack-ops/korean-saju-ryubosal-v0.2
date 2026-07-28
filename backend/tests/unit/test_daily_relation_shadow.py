"""relation_affinity 배수 shadow의 계산 불변식.

R1~R3는 다양성 보정이 아니라 **명리 점수 계약 변경**이므로, 배수가 관계 기여에만
작동하고 다른 축을 건드리지 않는다는 것을 강하게 검사한다.
"""

from __future__ import annotations

import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_relation_shadow import (
    RELATION_VARIANTS,
    score_event_with_relation,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

_DAYS = 3
_START = dt.date(2026, 7, 1)


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


def _cards(dicts, days: int = _DAYS):
    for i in range(days):
        ctx = M.build_day_context(_START + dt.timedelta(days=i))
        for idx in range(0, 60, 3):
            stem, branch = ganzi_from_index(idx)
            for key, ev in dicts.catalog["events"].items():
                yield ctx, stem, branch, key, ev


# ── R0 = 라이브 ────────────────────────────────────────────────────────────


def test_r0_reproduces_live_scoring_exactly(dicts) -> None:
    """배수 1.0이 라이브와 다르면 shadow 전체를 신뢰할 수 없다."""
    for ctx, stem, branch, key, ev in _cards(dicts):
        live = M._score_event(key, ev, stem, branch, ctx)
        shadow = score_event_with_relation(key, ev, stem, branch, ctx, multiplier=1.0)
        assert (live.probability, live.supporting_groups) == (
            shadow.probability, shadow.supporting_groups
        ), key


# ── 계산 불변식 ────────────────────────────────────────────────────────────


def test_zero_relation_affinity_events_are_unchanged(dicts) -> None:
    """`relation_affinity`가 전부 0인 사건은 배수와 무관하게 점수가 같다."""
    zero_events = {
        k: e for k, e in dicts.catalog["events"].items()
        if not any((e.get("relation_affinity") or {}).values())
    }
    if not zero_events:
        pytest.skip("relation_affinity가 0인 사건이 없다")

    ctx = M.build_day_context(_START)
    for idx in range(0, 60, 5):
        stem, branch = ganzi_from_index(idx)
        for key, ev in zero_events.items():
            base = score_event_with_relation(key, ev, stem, branch, ctx, multiplier=1.0)
            for mult in (1.25, 1.5, 1.75):
                assert score_event_with_relation(
                    key, ev, stem, branch, ctx, multiplier=mult
                ).probability == base.probability, f"{key} @ x{mult}"


def test_probability_stays_in_clamp_range(dicts) -> None:
    """배수를 올려도 기존 clamp(5~95) 밖의 값을 만들지 않는다."""
    for ctx, stem, branch, key, ev in _cards(dicts, 2):
        for mult in RELATION_VARIANTS.values():
            p = score_event_with_relation(
                key, ev, stem, branch, ctx, multiplier=mult
            ).probability
            assert 5 <= p <= 95, f"{key} @ x{mult} → {p}"


def test_same_relation_state_yields_same_delta(dicts) -> None:
    """같은 관계 상태·같은 사건이면 같은 delta — 결정론."""
    ctx = M.build_day_context(_START)
    stem, branch = ganzi_from_index(7)
    key = next(iter(dicts.catalog["events"]))
    ev = dicts.catalog["events"][key]

    a = score_event_with_relation(key, ev, stem, branch, ctx, multiplier=1.5)
    b = score_event_with_relation(key, ev, stem, branch, ctx, multiplier=1.5)

    assert a.probability == b.probability


def test_multiplier_is_monotonic_for_positive_relation(dicts) -> None:
    """양의 관계 기여는 배수를 올릴수록 낮아지지 않는다."""
    ctx = M.build_day_context(_START)
    checked = 0
    for idx in range(0, 60, 4):
        stem, branch = ganzi_from_index(idx)
        for key, ev in dicts.catalog["events"].items():
            rel = ev.get("relation_affinity") or {}
            if not any(v > 0 for v in rel.values()) or any(v < 0 for v in rel.values()):
                continue
            ps = [
                score_event_with_relation(
                    key, ev, stem, branch, ctx, multiplier=m
                ).probability
                for m in (1.0, 1.25, 1.5, 1.75)
            ]
            assert ps == sorted(ps), f"{key}: {ps}"
            checked += 1
    assert checked > 0, "검증 대상 사건이 없다"


# ── 라이브 불변 ────────────────────────────────────────────────────────────


def test_shadow_does_not_change_live_board(dicts) -> None:
    """shadow 채점을 돌려도 라이브 보드가 그대로다."""
    ctx = M.build_day_context(dt.date(2026, 7, 28))
    before = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]

    for idx in range(0, 60, 10):
        stem, branch = ganzi_from_index(idx)
        for key, ev in dicts.catalog["events"].items():
            score_event_with_relation(key, ev, stem, branch, ctx, multiplier=1.75)

    after = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]
    assert before == after

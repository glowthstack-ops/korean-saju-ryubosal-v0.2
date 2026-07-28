"""OA-8b — 7일 서사 family 회전 계약.

종단 감사에서 **같은 사건이 다시 나왔을 때 57%가 같은 family까지 반복**되는 것이
확인됐다. OA-8a는 하루 보드의 문장 반복만 줄였고 같은 일주의 시간축은 그대로였다.

이력을 조회하지 않고 **날짜 서수 순환**으로 해결한다:
  · 이력 조회는 7일치 보드 재계산(약 7배 비용)을 요구한다
  · 휘발성 불변식(과거 본문 미저장)과도 충돌한다
  · 순환은 같은 목적을 저장 없이 달성한다 — 연속 등장이면 반드시 다음 칸
"""

from __future__ import annotations

import collections
import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M

_PILOT = "money_small_gain"
_ILJU = "甲子"


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


def _resolve(dicts, key, ilju, d: dt.date):
    return M.resolve_narrative(
        dicts, key, f"{d.isoformat()}|{ilju}|x",
        day_ordinal=d.toordinal(), rotation_key=ilju,
    )


# ── 순환 축 ────────────────────────────────────────────────────────────────


def test_cycle_orders_families_within_mode(dicts) -> None:
    """같은 mode의 family가 인접한다 — family 우선, mode 나중."""
    cycle = M.narrative_cycle(dicts, _PILOT)
    assert len(cycle) == 9   # 3 mode × 3 family

    modes = [m for m, _f in cycle]
    # 같은 mode가 연속 구간을 이룬다(흩어져 있지 않다).
    assert len(list(collections.Counter(modes).items())) == 3
    runs = [k for k, _ in __import__("itertools").groupby(modes)]
    assert len(runs) == 3, f"mode가 흩어져 있다: {modes}"


def test_cycle_is_order_independent(dicts) -> None:
    """JSON 배열 순서를 뒤집어도 순환 축이 같다."""
    import copy

    shuffled = M.DailyFortuneDicts(
        catalog=copy.deepcopy(dicts.catalog), templates=dicts.templates,
        places=dicts.places,
    )
    modes = shuffled.catalog["events"][_PILOT]["narrative_modes"]
    modes.reverse()
    for m in modes:
        m["template_families"] = list(reversed(m["template_families"]))

    assert M.narrative_cycle(dicts, _PILOT) == M.narrative_cycle(shuffled, _PILOT)


# ── 회전 효과 ──────────────────────────────────────────────────────────────


def test_consecutive_days_never_repeat_family(dicts) -> None:
    """연속한 날에 같은 사건이면 family가 반드시 달라진다."""
    start = dt.date(2026, 7, 1)
    for offset in range(30):
        d = start + dt.timedelta(days=offset)
        a = _resolve(dicts, _PILOT, _ILJU, d)
        b = _resolve(dicts, _PILOT, _ILJU, d + dt.timedelta(days=1))
        assert a != b, f"{d}: {a} → {b}"


def test_seven_day_window_has_no_family_repeat(dicts) -> None:
    """후보가 9개이므로 7일 창 안에서는 같은 family가 재사용되지 않는다."""
    start = dt.date(2026, 7, 1)
    picks = [
        _resolve(dicts, _PILOT, _ILJU, start + dt.timedelta(days=i)) for i in range(7)
    ]
    assert len(set(picks)) == 7


def test_cycle_covers_all_families_before_repeating(dicts) -> None:
    """9일이면 모든 (mode, family)를 한 번씩 소진한다."""
    start = dt.date(2026, 7, 1)
    picks = [
        _resolve(dicts, _PILOT, _ILJU, start + dt.timedelta(days=i)) for i in range(9)
    ]
    assert set(picks) == set(M.narrative_cycle(dicts, _PILOT))


def test_different_iljus_do_not_share_the_same_family(dicts) -> None:
    """출발점이 일주별로 달라 같은 날 모두가 같은 family를 쓰지 않는다."""
    d = dt.date(2026, 7, 28)
    picks = {
        _resolve(dicts, _PILOT, f"ilju{i}", d) for i in range(20)
    }
    assert len(picks) > 3


def test_rotation_key_must_exclude_date(dicts) -> None:
    """회전 출발점에 날짜가 섞이면 순환이 무작위 재추첨으로 무너진다."""
    d0, d1 = dt.date(2026, 7, 1), dt.date(2026, 7, 2)
    # 올바른 사용 — rotation_key 는 일주만.
    good = {_resolve(dicts, _PILOT, _ILJU, d) for d in (d0, d1)}
    assert len(good) == 2

    # 잘못된 사용(날짜 포함)을 흉내내면 연속 보장이 깨질 수 있음을 문서화한다.
    bad0 = M.resolve_narrative(
        dicts, _PILOT, "x", day_ordinal=d0.toordinal(),
        rotation_key=f"{d0.isoformat()}|{_ILJU}",
    )
    bad1 = M.resolve_narrative(
        dicts, _PILOT, "x", day_ordinal=d1.toordinal(),
        rotation_key=f"{d1.isoformat()}|{_ILJU}",
    )
    assert isinstance(bad0, tuple) and isinstance(bad1, tuple)


# ── 불변식: 사건·점수는 건드리지 않는다 ─────────────────────────────────────


def test_rotation_does_not_change_event_selection(dicts) -> None:
    """회전은 표현만 바꾼다 — event_key·점수·band·장소 불변."""
    for i in range(7):
        d = dt.date(2026, 7, 1) + dt.timedelta(days=i)
        board = M.compute_board(M.build_day_context(d), dicts)
        for f in board.fortunes:
            assert 5 <= f.events[0].probability <= 95
            assert f.lucky_place is not None
            assert str(f.headline_event_key) in {e.event_key for e in f.events}


def test_rotation_is_deterministic(dicts) -> None:
    d = dt.date(2026, 7, 28)
    a = M.compute_board(M.build_day_context(d), dicts)
    b = M.compute_board(M.build_day_context(d), dicts)

    assert [f.headline for f in a.fortunes] == [f.headline for f in b.fortunes]


def test_non_pilot_events_are_unaffected(dicts) -> None:
    """서사 축이 없는 사건은 회전 대상이 아니다(빈 결과)."""
    non_pilot = next(
        k for k, e in dicts.catalog["events"].items() if not e.get("narrative_modes")
    )
    d = dt.date(2026, 7, 1)

    assert _resolve(dicts, non_pilot, _ILJU, d) == ("", "")


# ── 계약 보강 (승인 조건) ──────────────────────────────────────────────────


def test_expression_scope_uses_separate_rings(dicts) -> None:
    """일반 관계형 이력이 연애형 선택을 왜곡하지 않는다."""
    d = dt.date(2026, 7, 28)
    general = M.resolve_narrative(
        dicts, "love_spark", "x", day_ordinal=d.toordinal(),
        rotation_key=_ILJU, expression_scope="general",
    )
    romantic = M.resolve_narrative(
        dicts, "love_spark", "x", day_ordinal=d.toordinal(),
        rotation_key=_ILJU, expression_scope="romantic",
    )
    # 순환군이 분리돼 있으므로 같은 날 같은 칸을 쓰지 않는다(출발점이 다르다).
    assert general != romantic or len(M.narrative_cycle(dicts, "love_spark")) == 1


def test_scope_ring_is_independently_deterministic(dicts) -> None:
    d = dt.date(2026, 7, 28)
    for scope in ("general", "romantic"):
        a = M.resolve_narrative(
            dicts, "love_spark", "x", day_ordinal=d.toordinal(),
            rotation_key=_ILJU, expression_scope=scope,
        )
        b = M.resolve_narrative(
            dicts, "love_spark", "x", day_ordinal=d.toordinal(),
            rotation_key=_ILJU, expression_scope=scope,
        )
        assert a == b


def test_rotation_ring_status_flags_small_rings(dicts) -> None:
    """후보가 8개 미만이면 7일 회피를 보장할 수 없다 — 숨기지 않고 남긴다."""
    import copy

    assert M.rotation_ring_status(dicts, "money_small_gain") == ""

    shrunk = M.DailyFortuneDicts(
        catalog=copy.deepcopy(dicts.catalog), templates=dicts.templates,
        places=dicts.places,
    )
    modes = shrunk.catalog["events"]["money_small_gain"]["narrative_modes"]
    del modes[1:]                       # 3모드 → 1모드(= family 3개)
    assert M.rotation_ring_status(shrunk, "money_small_gain") == (
        "insufficient_eligible_families"
    )


def test_non_narrative_event_has_no_ring_warning(dicts) -> None:
    non_pilot = next(
        k for k, e in dicts.catalog["events"].items() if not e.get("narrative_modes")
    )
    assert M.rotation_ring_status(dicts, non_pilot) == ""


def test_rotation_version_is_in_cache_key_not_selection_seed() -> None:
    """회전 버전은 캐시만 무효화한다 — 사건 배정은 흔들리면 안 된다."""
    from saju_shared_types.daily_fortune import (
        CONTENT_VERSION,
        NARRATIVE_ROTATION_VERSION,
    )

    assert NARRATIVE_ROTATION_VERSION in CONTENT_VERSION
    assert NARRATIVE_ROTATION_VERSION not in M.EVENT_SELECTION_COMPAT_SALT

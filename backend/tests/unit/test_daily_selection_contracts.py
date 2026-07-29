"""OA-10a — 선택 원장 계약의 불변식.

세 가지를 지킨다.

  · 호환성은 **코드**에만 있다 — DB 데이터로 과거 이력의 해석을 바꿀 수 없다.
  · `UNKNOWN` 은 호환이 아니다(fail-closed). 모르는 계약을 읽으면 결과가 조용히
    달라진다.
  · 지문은 **결과를 바꾸는 모든 입력**을 포함한다. 하나라도 빠지면 다른 결과를
    같은 것으로 오인해 재사용한다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines.daily_selection_contracts import (
    DISPLAY_SELECTION_POLICY_C10_V1,
    DISPLAY_SELECTION_POLICY_LEGACY_V0,
    HISTORY_CONTRACT_COMPATIBILITY,
    HISTORY_CONTRACT_LOOKBACK_DAYS,
    HISTORY_CONTRACT_VERSION,
    TAXONOMY_COMPATIBILITY,
    USABLE_COMPATIBILITY,
    HistoryCompatibility,
    HistoryDay,
    advisory_lock_key,
    board_cache_key,
    board_result_fingerprint,
    classify_history_compatibility,
    engine_input_fingerprint,
    history_set_fingerprint,
    row_result_fingerprint,
)

_D = dt.date(2026, 8, 1)


def _engine_kwargs(**over):
    base = dict(
        fortune_date=_D, active_dict_version="dict.v1.11",
        content_version="engine.v1|dict.v1.11|polish.v1|narrative-rotation.v1",
        event_selection_contract="engine.v1|dict.v1.9|polish.v1",
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
        taxonomy_version="taxonomy.v1",
        board_rebalance_version="oa6b_board_domain_cap_v1",
        history_lookback_days=90,
    )
    base.update(over)
    return base


def _day(n: int, **over) -> HistoryDay:
    base = dict(
        fortune_date=_D - dt.timedelta(days=n), active_generation_id=f"g{n}",
        board_result_fingerprint=f"b{n}",
        history_contract_version=HISTORY_CONTRACT_VERSION,
        taxonomy_version="taxonomy.v1",
    )
    base.update(over)
    return HistoryDay(**base)


# ── 호환성은 코드 상수다 ───────────────────────────────────────────────────


def test_registries_are_code_constants() -> None:
    """registry 가 코드에 있고, 현재 계약이 자기 자신을 포함한다."""
    assert HISTORY_CONTRACT_VERSION in HISTORY_CONTRACT_COMPATIBILITY
    assert HISTORY_CONTRACT_VERSION in HISTORY_CONTRACT_COMPATIBILITY[
        HISTORY_CONTRACT_VERSION
    ]
    assert "taxonomy.v1" in TAXONOMY_COMPATIBILITY["taxonomy.v1"]


def test_exact_match() -> None:
    assert classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v1",
        target_history_contract=HISTORY_CONTRACT_VERSION,
        target_taxonomy_version="taxonomy.v1",
    ) is HistoryCompatibility.EXACT


def test_unknown_target_is_not_compatible() -> None:
    """registry 에 없는 계약은 **호환으로 간주하지 않는다**."""
    v = classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v1",
        target_history_contract="daily-selection-history.v9",
        target_taxonomy_version="taxonomy.v1",
    )
    assert v is HistoryCompatibility.UNKNOWN
    assert v not in USABLE_COMPATIBILITY


def test_unknown_taxonomy_is_not_compatible() -> None:
    v = classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v1",
        target_history_contract=HISTORY_CONTRACT_VERSION,
        target_taxonomy_version="taxonomy.v9",
    )
    assert v not in USABLE_COMPATIBILITY


def test_taxonomy_mismatch_is_incompatible() -> None:
    """이력 계약이 같아도 taxonomy 가 다르면 같은 event_key 가 다른 의미가 된다."""
    v = classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v0",
        target_history_contract=HISTORY_CONTRACT_VERSION,
        target_taxonomy_version="taxonomy.v1",
    )
    assert v is HistoryCompatibility.INCOMPATIBLE
    assert v not in USABLE_COMPATIBILITY


def test_policy_versions_are_distinct_axes() -> None:
    """정책 버전과 이력 계약은 다른 축이다 — 정책이 바뀌어도 이력은 이어진다."""
    assert DISPLAY_SELECTION_POLICY_LEGACY_V0 != DISPLAY_SELECTION_POLICY_C10_V1
    assert HISTORY_CONTRACT_VERSION not in (
        DISPLAY_SELECTION_POLICY_LEGACY_V0, DISPLAY_SELECTION_POLICY_C10_V1
    )


# ── history 지문 ──────────────────────────────────────────────────────────


def test_history_fingerprint_is_order_independent() -> None:
    days = [_day(i) for i in range(1, 6)]
    fp = history_set_fingerprint(days, lookback_days=90)
    assert fp == history_set_fingerprint(list(reversed(days)), lookback_days=90)


def test_history_fingerprint_changes_when_active_pointer_moves() -> None:
    """어느 하루의 active generation 이 바뀌면 지문도 반드시 달라진다."""
    base = [_day(i) for i in range(1, 6)]
    moved = [*base[:2], _day(3, active_generation_id="g3b"), *base[3:]]
    assert history_set_fingerprint(base, lookback_days=90) != history_set_fingerprint(
        moved, lookback_days=90
    )


def test_history_fingerprint_changes_when_result_changes() -> None:
    base = [_day(i) for i in range(1, 6)]
    changed = [*base[:4], _day(5, board_result_fingerprint="b5b")]
    assert history_set_fingerprint(base, lookback_days=90) != history_set_fingerprint(
        changed, lookback_days=90
    )


def test_history_fingerprint_covers_contract_versions() -> None:
    base = [_day(1)]
    assert history_set_fingerprint(base, lookback_days=90) != history_set_fingerprint(
        [_day(1, taxonomy_version="taxonomy.v2")]
    , lookback_days=90)


# ── engine 입력 지문 ──────────────────────────────────────────────────────


@pytest.mark.parametrize("field,value", [
    ("active_dict_version", "dict.v1.10"),
    ("content_version", "engine.v1|dict.v1.10|polish.v1|narrative-rotation.v1"),
    ("event_selection_contract", "engine.v1|dict.v1.10|polish.v1"),
    ("display_selection_policy_version", DISPLAY_SELECTION_POLICY_LEGACY_V0),
    ("taxonomy_version", "taxonomy.v2"),
    ("board_rebalance_version", "other"),
    ("fortune_date", dt.date(2026, 8, 2)),
    ("history_lookback_days", 89),
])
def test_engine_fingerprint_covers_every_result_changing_input(field, value) -> None:
    """결과를 바꾸는 입력이 하나라도 빠지면 다른 결과를 같은 것으로 재사용한다."""
    assert engine_input_fingerprint(**_engine_kwargs()) != engine_input_fingerprint(
        **_engine_kwargs(**{field: value})
    )


def test_engine_fingerprint_covers_feature_flags() -> None:
    a = engine_input_fingerprint(**_engine_kwargs())
    b = engine_input_fingerprint(**_engine_kwargs(feature_flags={"g0": "on"}))
    assert a != b
    # 플래그 순서는 결과에 영향을 주지 않는다.
    assert engine_input_fingerprint(
        **_engine_kwargs(feature_flags={"g0": "on", "a": "1"})
    ) == engine_input_fingerprint(
        **_engine_kwargs(feature_flags={"a": "1", "g0": "on"})
    )


def test_engine_fingerprint_is_stable() -> None:
    assert engine_input_fingerprint(**_engine_kwargs()) == engine_input_fingerprint(
        **_engine_kwargs()
    )


# ── 결과 지문 ─────────────────────────────────────────────────────────────


def _row(**over):
    base = dict(
        ilju="甲子", display_good_representative="money_small_gain",
        support_event="tidy_luck", caution_event="argument_caution",
        final_headline="money_small_gain",
        good_selection_reason="RAW_GOOD_WINNER_SELECTED",
        display_displacement_loss=0,
    )
    base.update(over)
    return base


def test_row_fingerprint_detects_any_selection_change() -> None:
    base = row_result_fingerprint(**_row())
    for field, value in (
        ("display_good_representative", "treat_received"),
        ("support_event", "rest_recharge"),
        ("caution_event", "fatigue_caution"),
        ("final_headline", "tidy_luck"),
        ("good_selection_reason", "LONGITUDINAL_ALTERNATIVE_SELECTED"),
        ("display_displacement_loss", 3),
    ):
        assert base != row_result_fingerprint(**_row(**{field: value})), field


def test_board_fingerprint_is_row_order_independent() -> None:
    rows = [row_result_fingerprint(**_row(ilju=f"i{i}")) for i in range(5)]
    assert board_result_fingerprint(rows) == board_result_fingerprint(
        list(reversed(rows))
    )


# ── 캐시·락 키 ────────────────────────────────────────────────────────────


def test_cache_key_pins_the_ledger_result() -> None:
    """캐시 키가 결과 지문을 포함해 어느 원장 결과인지 확정한다."""
    a = board_cache_key(
        fortune_date=_D, content_version="cv",
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
        board_result_fingerprint_="fp1",
    )
    b = board_cache_key(
        fortune_date=_D, content_version="cv",
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
        board_result_fingerprint_="fp2",
    )
    assert a != b
    assert "fp1" in a


def test_cache_key_separates_policy_versions() -> None:
    common = dict(fortune_date=_D, content_version="cv", board_result_fingerprint_="fp")
    assert board_cache_key(
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1, **common
    ) != board_cache_key(
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_LEGACY_V0, **common
    )


def test_advisory_lock_key_is_stable_and_bigint() -> None:
    k = advisory_lock_key(
        fortune_date=_D, display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1
    )
    assert k == advisory_lock_key(
        fortune_date=_D, display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1
    )
    assert -(2**63) <= k < 2**63


def test_advisory_lock_key_separates_date_and_policy() -> None:
    a = advisory_lock_key(
        fortune_date=_D, display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1
    )
    assert a != advisory_lock_key(
        fortune_date=_D + dt.timedelta(days=1),
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
    )
    assert a != advisory_lock_key(
        fortune_date=_D,
        display_selection_policy_version=DISPLAY_SELECTION_POLICY_LEGACY_V0,
    )


# ── lookback 계약 (89 → 90 정정) ──────────────────────────────────────────


def test_lookback_contract_is_ninety_days() -> None:
    """D-90 ~ D-1 양끝 포함 = 90일. 초안의 89 는 산술 오류였다."""
    from saju_engines.daily_selection_contracts import required_lookback_days
    from saju_engines.daily_selection_policy_shadow import (
        LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    )

    assert LONGITUDINAL_HISTORY_LOOKBACK_DAYS == 90
    assert required_lookback_days(HISTORY_CONTRACT_VERSION) == 90
    assert HISTORY_CONTRACT_LOOKBACK_DAYS[HISTORY_CONTRACT_VERSION] == 90


def test_history_range_is_inclusive_of_both_ends() -> None:
    """start = D-90 · end = D-1 이면 포함 일수가 정확히 90이다."""
    d = dt.date(2026, 8, 1)
    start, end = d - dt.timedelta(days=90), d - dt.timedelta(days=1)
    assert (end - start).days + 1 == 90


def test_lookback_length_is_in_the_history_fingerprint() -> None:
    """89일 이력과 90일 이력이 같은 지문이면 계약 정정이 드러나지 않는다."""
    days = [_day(i) for i in range(1, 6)]
    assert history_set_fingerprint(days, lookback_days=90) != history_set_fingerprint(
        days, lookback_days=89
    )


def test_wrong_lookback_source_is_incompatible() -> None:
    """89일로 만든 이력을 90일 계약으로 읽을 수 없다."""
    v = classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v1",
        target_history_contract=HISTORY_CONTRACT_VERSION,
        target_taxonomy_version="taxonomy.v1",
        source_lookback_days=89,
    )
    assert v is HistoryCompatibility.INCOMPATIBLE
    assert v not in USABLE_COMPATIBILITY


def test_matching_lookback_source_is_exact() -> None:
    assert classify_history_compatibility(
        source_history_contract=HISTORY_CONTRACT_VERSION,
        source_taxonomy_version="taxonomy.v1",
        target_history_contract=HISTORY_CONTRACT_VERSION,
        target_taxonomy_version="taxonomy.v1",
        source_lookback_days=90,
    ) is HistoryCompatibility.EXACT

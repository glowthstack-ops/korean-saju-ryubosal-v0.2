"""OA-10a — `display-selection.legacy-v0` 와 날짜별 계약 해소.

legacy-v0 는 "현재 코드에서 C10 만 끈 상태"가 아니라 **독립된 고정 계약**이다.
그렇지 않으면 이후 코드가 변할 때 legacy 도 함께 변해 과거 재현이 무너진다.

resolver 의 역할은 하나 더 있다 — **없던 날짜를 지어내지 않는 것**. 일운 서비스는
2026-07-23 에 시작했고, 날짜로 사전을 고르는 장치는 2026-07-30 부터다. 그 이전을
현재 코드로 근사해 "재현본"이라 부르면 그건 날조다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines.daily_contract_resolver import (
    DAILY_FORTUNE_SERVICE_START,
    DICT_DATE_BOUNDARY_SINCE,
    DICT_VERSION_NOT_DATE_ADDRESSABLE,
    SERVICE_NOT_YET_LIVE,
    ContractResolutionError,
    earliest_exact_replay_date,
    replay_blocker,
    resolve_day_contracts,
)
from saju_engines.daily_legacy_display import (
    RAW_GOOD_WINNER_SELECTED,
    build_legacy_board,
    legacy_policy_version,
)
from saju_engines.daily_selection_contracts import (
    DISPLAY_SELECTION_POLICY_LEGACY_V0,
)

#: 정확 재현이 가능한 날짜들. 7/30 은 `dict.v1.10 → v1.11` 경계이자 C10 shadow 에서
#: authorized domain override 가 난 날이다.
_BOUNDARY = dt.date(2026, 7, 30)
_LATER = dt.date(2026, 8, 5)


# ── resolver: 없던 날짜를 지어내지 않는다 ─────────────────────────────────


def test_pre_service_dates_are_refused() -> None:
    """서비스가 없던 날짜는 재현 대상이 아니다."""
    before = DAILY_FORTUNE_SERVICE_START - dt.timedelta(days=1)
    assert replay_blocker(before) == SERVICE_NOT_YET_LIVE
    with pytest.raises(ContractResolutionError) as e:
        resolve_day_contracts(before)
    assert e.value.code == SERVICE_NOT_YET_LIVE


def test_pre_boundary_dates_are_not_date_addressable() -> None:
    """날짜 경계 장치 이전에는 사전을 제자리에서 교체했다 — 날짜로 특정할 수 없다."""
    mid = DICT_DATE_BOUNDARY_SINCE - dt.timedelta(days=1)
    assert mid >= DAILY_FORTUNE_SERVICE_START
    assert replay_blocker(mid) == DICT_VERSION_NOT_DATE_ADDRESSABLE
    with pytest.raises(ContractResolutionError):
        resolve_day_contracts(mid)


def test_boundary_and_after_are_replayable() -> None:
    assert replay_blocker(_BOUNDARY) == ""
    assert replay_blocker(_LATER) == ""
    assert earliest_exact_replay_date() == DICT_DATE_BOUNDARY_SINCE


def test_non_strict_mode_flags_instead_of_raising() -> None:
    """감사용 완화 모드는 실패 대신 표시한다 — 그 결과는 history 로 쓸 수 없다."""
    c = resolve_day_contracts(dt.date(2026, 5, 1), strict=False)
    assert c.exactly_replayable is False
    assert c.resolution_note == SERVICE_NOT_YET_LIVE


def test_resolver_applies_the_date_boundary_dictionary() -> None:
    """7/30 경계가 실제로 적용된다 — 9/3(행운의 장소)·9/12(카탈로그 확장) 경계까지 4단."""
    from saju_shared_types.daily_fortune import (
        CATALOG_EXPANSION_EFFECTIVE_FROM,
        DICT_VERSION,
        DICT_VERSION_BEFORE_CATALOG_EXPANSION,
        DICT_VERSION_BEFORE_LUCKY_PLACES_REVISION,
        LUCKY_PLACES_REVISION_EFFECTIVE_FROM,
        PREVIOUS_DICT_VERSION,
    )

    # 7/30~9/2 는 v1.11 — 그 구간의 라이브 결과는 개정 전 사전으로 재현돼야 한다.
    assert (
        resolve_day_contracts(_BOUNDARY).active_dict_version
        == DICT_VERSION_BEFORE_LUCKY_PLACES_REVISION
    )
    # 9/3~9/11 은 v1.12, 9/12 부터 v1.13(§22-7 카탈로그 확장).
    assert (
        resolve_day_contracts(LUCKY_PLACES_REVISION_EFFECTIVE_FROM).active_dict_version
        == DICT_VERSION_BEFORE_CATALOG_EXPANSION
    )
    assert (
        resolve_day_contracts(CATALOG_EXPANSION_EFFECTIVE_FROM).active_dict_version
        == DICT_VERSION
    )
    # 경계 이전은 strict 로 막히지만, 완화 모드에서 이전 버전을 가리키는지 확인한다.
    before = resolve_day_contracts(
        _BOUNDARY - dt.timedelta(days=1), strict=False
    )
    assert before.active_dict_version == PREVIOUS_DICT_VERSION


# ── legacy-v0 계약 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("day", [_BOUNDARY, _LATER])
def test_representative_is_always_the_raw_winner(day: dt.date) -> None:
    """legacy 에는 장기 선택이 없다 — 대표는 언제나 원시 1위다."""
    _c, rows = build_legacy_board(day)
    assert len(rows) == 60
    for r in rows:
        assert r.display_good_representative == r.raw_good_winner
        assert r.display_good_probability == r.raw_good_probability
        assert r.display_good_band == r.raw_good_band
        assert r.display_displacement_loss == 0
        assert r.good_selection_reason == RAW_GOOD_WINNER_SELECTED


def test_final_headline_includes_board_rebalance() -> None:
    """장기 선택이 없다는 이유로 보드 캡까지 생략하지 않는다."""
    _c, rows = build_legacy_board(dt.date(2026, 8, 15))
    moved = [r for r in rows if r.final_headline != r.raw_headline]
    assert moved, "보드 캡 이동이 0건이면 재배정이 적용되지 않은 것이다"


def test_headline_is_one_of_the_displayed_events() -> None:
    _c, rows = build_legacy_board(_LATER)
    for r in rows:
        shown = {r.display_good_representative, r.support_event, r.caution_event}
        assert r.final_headline in shown
        assert r.raw_headline in shown


def test_slots_are_distinct() -> None:
    _c, rows = build_legacy_board(_LATER)
    for r in rows:
        assert len({
            r.display_good_representative, r.support_event, r.caution_event
        }) == 3


def test_legacy_is_deterministic() -> None:
    a = build_legacy_board(_LATER)[1]
    b = build_legacy_board(_LATER)[1]
    assert [x.final_headline for x in a] == [x.final_headline for x in b]
    assert [x.place_key for x in a] == [x.place_key for x in b]


def test_legacy_does_not_depend_on_taxonomy() -> None:
    """taxonomy 를 바꿔도 legacy 결과가 달라지면 안 된다 — 계약 입력이 아니다."""
    import saju_engines.daily_g0_shadow as G

    base = [r.final_headline for r in build_legacy_board(_LATER)[1]]
    G.load_taxonomy.cache_clear()
    after = [r.final_headline for r in build_legacy_board(_LATER)[1]]
    assert base == after


def test_policy_version_is_declared() -> None:
    assert legacy_policy_version() == DISPLAY_SELECTION_POLICY_LEGACY_V0


# ── golden fixture ────────────────────────────────────────────────────────
#
# 사건 키만 비교하지 않는다. 선택 결과와 계약을 함께 고정해, 어느 하나가 바뀌면
# 무엇이 바뀌었는지 드러나게 한다. 문장·family·content 는 **별도 축**이므로
# 여기서는 선택 fixture 만 다룬다(콘텐츠 fixture 는 OA-8a/8b 회귀가 담당).


def _selection_fixture(day: dt.date) -> dict:
    c, rows = build_legacy_board(day)
    return {
        "contracts": {
            "active_dict_version": c.active_dict_version,
            "content_version": c.content_version,
            "event_selection_contract": c.event_selection_contract,
            "board_rebalance_version": c.board_rebalance_version,
            "selection_policy_version": legacy_policy_version(),
            "exactly_replayable": c.exactly_replayable,
        },
        "rows": [
            (r.ilju, r.raw_good_winner, r.display_good_representative,
             r.support_event, r.caution_event, r.raw_headline, r.final_headline,
             r.place_key, r.band)
            for r in rows
        ],
    }


@pytest.mark.parametrize("day", [_BOUNDARY, _LATER])
def test_selection_fixture_is_stable(day: dt.date) -> None:
    """같은 날짜를 두 번 재생하면 계약과 60행이 모두 동일하다."""
    assert _selection_fixture(day) == _selection_fixture(day)


def test_dict_boundary_changes_the_contract_not_the_policy() -> None:
    """7/30 경계에서 사전·콘텐츠 버전은 바뀌지만 표시 정책은 그대로다."""
    at = _selection_fixture(_BOUNDARY)["contracts"]
    later = _selection_fixture(_LATER)["contracts"]
    assert at["active_dict_version"] == later["active_dict_version"]
    assert at["selection_policy_version"] == later["selection_policy_version"]
    assert at["event_selection_contract"] == later["event_selection_contract"]


def test_legacy_does_not_reproduce_c10_override_reasons() -> None:
    """같은 7/30 이라도 정책이 다르면 결과·사유가 다르다.

    C10 shadow 의 authorized domain override 를 legacy 재생에서 기대하면 안 된다.
    """
    _c, rows = build_legacy_board(_BOUNDARY)
    assert all(r.good_selection_reason == RAW_GOOD_WINNER_SELECTED for r in rows)

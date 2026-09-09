"""docs/17 §22-7 — 사건 카탈로그 48→64종 확장(2026-09-10 사용자 승인) 회귀.

검증 축:
1. 4개 사전(v1·v2 카탈로그·taxonomy·문구 템플릿)이 신규 16종을 빠짐없이 담는다.
2. 날짜 경계 — 9/11 보드까지는 48종(model.v2.0·dict.v1.12), 9/12 부터 64종. 이미
   생성·교정된 보드가 재생성되지 않도록 캐시 namespace 도 날짜가 고른다.
3. 신규 사건이 실제로 노출된다(사전에만 있고 선발에 닿지 않는 '유령 사건' 방지).
4. 12운성 채널이 good 슬롯 출전권에 들어갔다(확장의 목적 — §22-7 발단).
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines import daily_ilju_fortune as v1
from saju_engines.daily_fortune_v2 import (
    compute_board_v2,
    content_version_v2_for,
    load_catalog_v2,
    load_catalog_v2_for,
)
from saju_shared_types.daily_fortune import (
    CATALOG_EXPANSION_EFFECTIVE_FROM,
    DICT_VERSION,
    DICT_VERSION_BEFORE_CATALOG_EXPANSION,
    active_dict_version,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    PREVIOUS_MODEL_V2_VERSION,
    active_model_v2_version,
)

NEW_GOOD = (
    "work_smooth", "opinion_accepted", "smooth_trip", "errand_done", "body_light",
    "appetite_joy", "answer_arrives", "unexpected_offer", "learning_click",
    "forgotten_money", "give_care",
)
NEW_CAUTION = (
    "emotion_rush_caution", "overconfidence_caution", "close_person_expense_caution",
    "procrastination_caution", "rumination_caution",
)
NEW_KEYS = frozenset(NEW_GOOD + NEW_CAUTION)
STAGE_CHANNELS = (
    "activity_up", "overdrive", "stamina_down", "pace_down", "disengage", "closure",
    "renewal",
)

_BEFORE = CATALOG_EXPANSION_EFFECTIVE_FROM - dt.timedelta(days=1)
_AFTER = CATALOG_EXPANSION_EFFECTIVE_FROM


def _slot_keys(fortune) -> dict[str, str]:
    return {e.slot: e.event_key for e in fortune.events}


# ── 1. 사전 4종 정합 ──────────────────────────────────────────────────────────


def test_all_dictionaries_carry_the_16_new_events() -> None:
    dicts = v1.load_daily_dicts()
    catalog_v2 = load_catalog_v2()
    assert NEW_KEYS <= set(dicts.catalog["events"])
    assert NEW_KEYS <= set(dicts.templates["events"])
    assert NEW_KEYS <= set(catalog_v2.events)
    assert len(catalog_v2.events) == 64
    for key in NEW_GOOD:
        assert catalog_v2.events[key].valence == "good", key
    for key in NEW_CAUTION:
        assert catalog_v2.events[key].valence == "caution", key
        assert catalog_v2.events[key].slots == ["caution"], key


def test_new_support_only_events_keep_headline_eligibility() -> None:
    """support 전용 신규 사건은 OA-6a 공통 노출 정책대로 헤드라인 자격(good)을 갖는다."""
    catalog_v2 = load_catalog_v2()
    for key in NEW_GOOD:
        model = catalog_v2.events[key]
        if model.slots == ["support"]:
            assert model.headline_slots == ["good"], key


def test_synonym_groups_pair_contradicting_events() -> None:
    """상충 사건은 같은 그룹 — 동시 노출 금지 불변식이 새 사건에도 걸린다."""
    events = load_catalog_v2().events
    assert events["work_smooth"].synonym_group == events["procrastination_caution"].synonym_group
    assert events["smooth_trip"].synonym_group == events["traffic_delay_caution"].synonym_group
    assert events["body_light"].synonym_group == events["fatigue_caution"].synonym_group
    assert (
        events["close_person_expense_caution"].synonym_group
        == events["lend_money_caution"].synonym_group
    )
    assert events["forgotten_money"].synonym_group == events["small_find"].synonym_group
    assert events["emotion_rush_caution"].synonym_group == events["argument_caution"].synonym_group


# ── 2. 날짜 경계 ──────────────────────────────────────────────────────────────


def test_version_boundary_is_shared_by_v1_and_v2() -> None:
    assert active_dict_version(_BEFORE) == DICT_VERSION_BEFORE_CATALOG_EXPANSION
    assert active_dict_version(_AFTER) == DICT_VERSION
    assert active_model_v2_version(_BEFORE) == PREVIOUS_MODEL_V2_VERSION
    assert active_model_v2_version(_AFTER) == MODEL_V2_VERSION
    assert content_version_v2_for(_BEFORE).endswith(PREVIOUS_MODEL_V2_VERSION)
    assert content_version_v2_for(_AFTER).endswith(MODEL_V2_VERSION)


def test_past_dates_load_the_48_event_snapshot() -> None:
    """과거 날짜는 커밋된 model.v2.0 스냅샷의 카탈로그로 재생된다."""
    before = load_catalog_v2_for(_BEFORE)
    after = load_catalog_v2_for(_AFTER)
    assert len(before.events) == 48 and NEW_KEYS.isdisjoint(before.events)
    assert len(after.events) == 64


def test_board_before_boundary_never_exposes_new_events() -> None:
    d = _BEFORE
    board = compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
    assert board.content_version.endswith(PREVIOUS_MODEL_V2_VERSION)
    for f in board.fortunes:
        assert NEW_KEYS.isdisjoint(_slot_keys(f).values()), f.ilju
        assert f.headline_event_key not in NEW_KEYS


# ── 3. 신규 사건 실노출 ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def boards_after():
    days = [_AFTER + dt.timedelta(days=i) for i in range(14)]
    return {
        d: compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
        for d in days
    }


def test_new_events_actually_reach_cards(boards_after) -> None:
    """14일 × 60일주에서 신규 good·caution 이 각각 슬롯에 실제로 오른다."""
    exposed_good: set[str] = set()
    exposed_caution: set[str] = set()
    headline: set[str] = set()
    for board in boards_after.values():
        assert board.content_version.endswith(MODEL_V2_VERSION)
        for f in board.fortunes:
            keys = _slot_keys(f)
            if keys["good"] in NEW_KEYS:
                exposed_good.add(keys["good"])
            if keys["support"] in NEW_KEYS:
                exposed_good.add(keys["support"])
            if keys["caution"] in NEW_KEYS:
                exposed_caution.add(keys["caution"])
            if f.headline_event_key in NEW_KEYS:
                headline.add(f.headline_event_key)
    assert len(exposed_good) >= 6, sorted(exposed_good)
    assert len(exposed_caution) >= 3, sorted(exposed_caution)
    assert len(headline) >= 4, sorted(headline)


# ── 4. 12운성이 good 출전권에 들어갔다 ────────────────────────────────────────


def test_stage_channels_gate_good_events_now() -> None:
    """확장 전에는 12운성 signature 사건 10종 중 good 2종뿐이었다 — 확장 후 good ≥ 6."""
    events = load_catalog_v2().events
    gated_good = [
        k for k, m in events.items()
        if m.valence == "good" and m.required_signature is not None
        and any(ch in str(m.required_signature) for ch in STAGE_CHANNELS)
    ]
    assert len(gated_good) >= 6, gated_good

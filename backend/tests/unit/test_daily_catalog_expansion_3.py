"""docs/17 §22-7 — 사건 카탈로그 3차 확장 64→82종(2026-09-18 데굴님 승인, 참고 기준 대조) 회귀.

1. 4개 사전(v1·v2 카탈로그·taxonomy·문구 템플릿)이 신규 18종을 빠짐없이 담는다.
2. 날짜 경계 — 9/19 보드까지는 64종(model.v2.1·dict.v1.13), 9/20 부터 82종(model.v2.2·dict.v1.14).
3. 경계 이후 보드에서 신규 good·caution 이 실제로 슬롯에 오른다.
4. 동의어 그룹 재배정(6건)이 상충 사건 동시 노출 금지에 걸린다.
게이트 리프 양의 evidence·감점 12운성 성립 가능성·signature 연 전수 성립은 기존 전 사건 회귀가
현재 원본(82종)을 그대로 검사한다.
"""

from __future__ import annotations

import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as v1
from saju_engines.daily_fortune_v2 import (
    compute_board_v2,
    content_version_v2_for,
    load_catalog_v2,
    load_catalog_v2_for,
)
from saju_shared_types.daily_fortune import (
    CATALOG_EXPANSION_3_EFFECTIVE_FROM,
    DICT_VERSION,
    DICT_VERSION_BEFORE_CATALOG_EXPANSION_3,
    active_dict_version,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    MODEL_V2_VERSION_BEFORE_EXPANSION_3,
    active_model_v2_version,
)

NEW_GOOD = {
    "approval_resumes", "misunderstanding_cleared", "burden_settled", "early_catch",
    "referral_received", "trust_restored", "relief_news", "autonomy_day", "demand_up",
}
NEW_CAUTION = {
    "settlement_dispute_caution", "decision_deferred_caution", "tangled_requests_caution",
    "repeat_mistake_caution", "credit_overlooked_caution", "payment_delay_caution",
    "family_duty_caution", "complaint_caution", "device_glitch_caution",
}
NEW_KEYS = NEW_GOOD | NEW_CAUTION
_BEFORE = CATALOG_EXPANSION_3_EFFECTIVE_FROM - dt.timedelta(days=1)
_AFTER = CATALOG_EXPANSION_3_EFFECTIVE_FROM
_REASSIGNED = {
    "love_cooldown": "love_bond_group", "teamwork_flow": "cooperation_group",
    "overconfidence_caution": "attention_group", "praise_recognition": "recognition_group",
    "family_talk": "family_group", "opinion_accepted": "feedback_group",
}


def test_all_dictionaries_carry_the_18_new_events() -> None:
    dicts = v1.load_daily_dicts()
    catalog_v2 = load_catalog_v2()
    assert NEW_KEYS <= set(dicts.catalog["events"])
    assert NEW_KEYS <= set(dicts.templates["events"])
    assert NEW_KEYS <= set(catalog_v2.events)
    assert len(catalog_v2.events) == 82 and len(NEW_KEYS) == 18
    for key in NEW_GOOD:
        assert catalog_v2.events[key].valence == "good", key
    for key in NEW_CAUTION:
        assert catalog_v2.events[key].valence == "caution", key
        assert catalog_v2.events[key].slots == ["caution"], key
    # support 전용 신규 2종은 헤드라인 자격(good)을 갖는다(OA-6a 공통 정책).
    for key in ("burden_settled", "early_catch"):
        assert catalog_v2.events[key].slots == ["support"]
        assert catalog_v2.events[key].headline_slots == ["good"]
    for key, tpl in dicts.templates["events"].items():
        if key in NEW_KEYS:
            assert len(tpl["fragments"]) == 5 and len(tpl["actions"]) == 3
            assert len(tpl["sipseong_actions"]) == 10


def test_synonym_groups_pair_new_and_reassigned_events() -> None:
    """상충 사건은 같은 그룹 — 재배정 6건과 신설 그룹이 카탈로그에 반영돼 있다."""
    events = load_catalog_v2().events
    for key, group in _REASSIGNED.items():
        assert events[key].synonym_group == group, key
    pairs = [
        ("burden_settled", "settlement_dispute_caution"), ("early_catch", "repeat_mistake_caution"),
        ("trust_restored", "love_cooldown"), ("credit_overlooked_caution", "praise_recognition"),
        ("complaint_caution", "opinion_accepted"), ("family_duty_caution", "family_talk"),
        ("tangled_requests_caution", "teamwork_flow"),
    ]
    for a, b in pairs:
        assert events[a].synonym_group == events[b].synonym_group, (a, b)


def test_third_boundary_is_shared_by_v1_and_v2() -> None:
    assert active_dict_version(_BEFORE) == DICT_VERSION_BEFORE_CATALOG_EXPANSION_3 == "dict.v1.13"
    assert active_dict_version(_AFTER) == DICT_VERSION == "dict.v1.14"
    assert active_model_v2_version(_BEFORE) == MODEL_V2_VERSION_BEFORE_EXPANSION_3 == "model.v2.1"
    assert active_model_v2_version(_AFTER) == MODEL_V2_VERSION == "model.v2.2"
    assert content_version_v2_for(_BEFORE).endswith("model.v2.1")
    assert content_version_v2_for(_AFTER).endswith("model.v2.2")


def test_dates_before_third_boundary_load_the_64_event_snapshot() -> None:
    before = load_catalog_v2_for(_BEFORE)
    after = load_catalog_v2_for(_AFTER)
    assert len(before.events) == 64 and NEW_KEYS.isdisjoint(before.events)
    assert len(after.events) == 82 and NEW_KEYS <= set(after.events)


@pytest.fixture(scope="module")
def boards_after():
    return [
        compute_board_v2(v1.build_day_context(d), v1.load_daily_dicts_for(d))
        for d in (_AFTER + dt.timedelta(days=i) for i in range(14))
    ]


def test_board_before_boundary_never_exposes_new_events() -> None:
    board = compute_board_v2(v1.build_day_context(_BEFORE), v1.load_daily_dicts_for(_BEFORE))
    assert board.content_version.endswith("model.v2.1")
    for f in board.fortunes:
        assert NEW_KEYS.isdisjoint(e.event_key for e in f.events)
        assert f.headline_event_key not in NEW_KEYS


def test_new_events_actually_reach_cards(boards_after) -> None:
    """14일 × 60일주에서 신규 good·caution 이 각각 슬롯에 실제로 오른다."""
    seen_good: set[str] = set()
    seen_caution: set[str] = set()
    for board in boards_after:
        assert board.content_version.endswith("model.v2.2")
        for f in board.fortunes:
            for e in f.events:
                if e.event_key in NEW_GOOD:
                    seen_good.add(e.event_key)
                if e.event_key in NEW_CAUTION:
                    seen_caution.add(e.event_key)
    assert len(seen_good) >= 5, sorted(seen_good)
    assert len(seen_caution) >= 5, sorted(seen_caution)

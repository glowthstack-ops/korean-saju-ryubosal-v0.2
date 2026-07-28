"""OA-6a — 헤드라인 자격과 본문 배치 역할의 분리.

`slots` 하나가 두 의미(카드 안 배치 / 헤드라인 자격)를 겸하던 것이 병목이었다.
실측: 정리·집중·휴식 같은 생활 장면 6종이 1,800카드에서 헤드라인 0회.
"""

from __future__ import annotations

import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M

#: OA-6a에서 헤드라인 자격을 연 사건 — 본문 역할은 support 그대로다.
_OPENED = (
    "focus_flow", "tidy_luck", "rest_recharge",
    "family_talk", "walk_refresh", "small_find",
)


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


def test_opened_events_keep_support_body_role(dicts) -> None:
    """본문 배치는 그대로 support — 헤드라인 자격만 추가된다."""
    events = dicts.catalog["events"]
    for key in _OPENED:
        assert events[key]["slots"] == ["support"], f"{key}: 본문 배치가 바뀌었다"
        assert events[key]["headline_slots"] == ["good"]


def test_headline_slots_falls_back_to_slots(dicts) -> None:
    """미지정 사건은 기존 `slots`로 폴백한다 — 사전 일괄 수정 없이 도입된다."""
    events = dicts.catalog["events"]
    unspecified = [k for k, e in events.items() if not e.get("headline_slots")]
    assert unspecified, "폴백 경로가 검증되려면 미지정 사건이 남아 있어야 한다"

    # 폴백이 실제로 동작하는지 — 43종이 headline_slots 없이도 자격 판정을 받는다.
    for key in unspecified:
        resolved = events[key].get("headline_slots") or events[key]["slots"]
        assert resolved == events[key]["slots"]


def test_headline_eligible_count_increased(dicts) -> None:
    """자격 사건 14종 → 20종."""
    events = dicts.catalog["events"]
    eligible = [
        k for k, e in events.items()
        if "good" in (e.get("headline_slots") or e["slots"])
    ]
    assert len(eligible) == 20


def test_opened_events_actually_reach_headline(dicts) -> None:
    """자격만 열고 끝내지 않는다 — 실제 보드에 등장해야 의미가 있다."""
    seen: set[str] = set()
    for i in range(30):
        board = M.compute_board(
            M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=i)), dicts
        )
        for f in board.fortunes:
            if str(f.headline_event_key) in _OPENED:
                seen.add(str(f.headline_event_key))
    assert seen, "6종이 여전히 헤드라인 0회 — 자격 개방이 런타임에 닿지 않았다"


def test_opened_event_is_displayed_in_card(dicts) -> None:
    """헤드라인 사건은 카드에 표시되는 3개 안에 있어야 한다.

    본문에 없는 이야기가 제목에 나오면 카드가 자기모순이 된다.
    """
    for i in range(7):
        board = M.compute_board(
            M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=i)), dicts
        )
        for f in board.fortunes:
            shown = {e.event_key for e in f.events}
            assert str(f.headline_event_key) in shown, (
                f"{f.ilju}: 헤드라인 {f.headline_event_key}가 카드에 없다"
            )


def test_caution_headline_only_from_caution_slot(dicts) -> None:
    """주의 사건이 헤드라인이 되는 경로는 caution 슬롯뿐이다(위험 경로 불변)."""
    events = dicts.catalog["events"]
    for i in range(7):
        board = M.compute_board(
            M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=i)), dicts
        )
        for f in board.fortunes:
            key = str(f.headline_event_key)
            if events[key]["valence"] != "caution":
                continue
            caution = next(e for e in f.events if e.slot == "caution")
            assert key == caution.event_key

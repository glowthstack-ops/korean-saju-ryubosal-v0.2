"""OA-6b·OA-7a — 보드 단위 도메인 캡과 전후 감사.

캡은 **균등화가 아니라 조건부 제약**이다. 유효한 대안이 있을 때만 독점을 완화하고,
대안이 없으면 초과를 허용한다. 다양성을 위해 근거가 약한 사건을 억지로 올리지 않는다.
"""

from __future__ import annotations

import collections
import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M

_DAYS = 14
_START = dt.date(2026, 7, 1)


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


@pytest.fixture(scope="module")
def boards(dicts):
    return [
        M.compute_board(M.build_day_context(_START + dt.timedelta(days=i)), dicts)
        for i in range(_DAYS)
    ]


# ── 결정론·순서 무관 ────────────────────────────────────────────────────────


def test_board_is_deterministic(dicts) -> None:
    """같은 날짜는 항상 같은 결과 — 캡이 결정론을 깨지 않는다."""
    a = M.compute_board(M.build_day_context(_START), dicts)
    b = M.compute_board(M.build_day_context(_START), dicts)

    assert [f.headline_event_key for f in a.fortunes] == [
        f.headline_event_key for f in b.fortunes
    ]
    assert [f.headline for f in a.fortunes] == [f.headline for f in b.fortunes]


def test_no_ilju_order_bias(dicts) -> None:
    """일주 처리 순서가 결과를 바꾸지 않는다.

    순차로 훑으며 상한에 도달하면 막는 방식이면 갑자·을축처럼 앞선 일주가 좋은 후보를
    선점한다. 보드 전체를 본 뒤 재배정하므로 입력 순서를 뒤집어도 결과가 같아야 한다.
    """
    board = M.compute_board(M.build_day_context(_START), dicts)
    # `_headline_audit` 는 object.__setattr__ 로 붙는 감사 sidecar 다(모델 필드가
    # 아니다 — 선언하면 production 직렬화가 바뀐다). 상수 getattr 는 ruff B009 가 막고
    # 직접 접근은 mypy 가 막으므로, 사유를 적은 targeted ignore 로 동적임을 드러낸다.
    headline_audit = board._headline_audit  # type: ignore[attr-defined]
    order = [a.ilju for a in headline_audit]
    # 재배정 입력을 그대로 재구성한다(후보 목록은 카드의 표시 사건에서 복원).
    decisions = {
        a.ilju: [
            e for e in (
                M._ScoredEvent(
                    event_key=a.raw_event_key, domain=a.raw_domain, valence="good",
                    slots=("good",), headline_slots=("good",), synonym_group=None,
                    activation=0.0, probability=a.raw_score,
                    supporting_groups=0, contradiction=0.0,
                ),
            )
        ]
        for a in headline_audit
    }
    forward, _, _ = M._rebalance_headlines(decisions, order, M._DOMAIN_HEADLINE_CAP)
    reverse, _, _ = M._rebalance_headlines(
        decisions, list(reversed(order)), M._DOMAIN_HEADLINE_CAP
    )

    assert {k: v.event_key for k, v in forward.items()} == {
        k: v.event_key for k, v in reverse.items()
    }


# ── 조건부 제약 ────────────────────────────────────────────────────────────


def test_cap_reduces_domain_monopoly(boards) -> None:
    """캡 적용 후 도메인 점유가 낮아진다."""
    raw_share, final_share = [], []
    for board in boards:
        raw = collections.Counter(a.raw_domain for a in board._headline_audit)
        fin = collections.Counter(a.selected_domain for a in board._headline_audit)
        raw_share.append(max(raw.values()) / 60)
        final_share.append(max(fin.values()) / 60)

    assert sum(final_share) < sum(raw_share), "캡이 독점을 전혀 줄이지 못했다"


def test_cap_allows_overflow_when_no_alternative(boards) -> None:
    """유효 대안이 없으면 상한 초과를 허용한다 — 억지 교체 금지."""
    unresolved = [b for b in boards if b._cap_unresolved > 0]
    for board in unresolved:
        # 초과가 남았다면, 초과 도메인 카드 중 교차 도메인 후보가 있는 카드가 없어야 한다.
        fin = collections.Counter(a.selected_domain for a in board._headline_audit)
        over_domain = max(fin, key=lambda d: fin[d])
        movable = [
            a for a in board._headline_audit
            if a.selected_domain == over_domain and a.eligible_cross_domain_count > 0
        ]
        assert not movable, "옮길 수 있는 카드가 남았는데 초과를 방치했다"


def test_displacement_cost_is_small(boards) -> None:
    """교체는 거의 동점 후보에서만 일어나야 한다(해석 적합성 보존)."""
    costs = [
        a.displacement_cost
        for b in boards
        for a in b._headline_audit
        if a.selection_reason == "board_domain_cap"
    ]
    if not costs:
        pytest.skip("교체 없음")
    assert max(costs) <= 15, f"점수 손실이 과도하다: 최대 {max(costs)}p"
    assert sum(costs) / len(costs) <= 6


def test_replacement_never_lowers_below_alternative(boards) -> None:
    """교체 결과는 항상 그 카드의 실제 후보 중 하나다 — 없는 사건을 만들지 않는다."""
    for board in boards:
        for f, a in zip(board.fortunes, board._headline_audit, strict=True):
            shown = {e.event_key for e in f.events}
            assert a.selected_event_key in shown


# ── 불변식: 점수·band·caution ───────────────────────────────────────────────


def test_scores_and_events_unchanged_by_cap(boards) -> None:
    """캡은 노출만 바꾼다 — 사건 점수·후보 구성은 건드리지 않는다."""
    for board in boards:
        for f in board.fortunes:
            assert len(f.events) == 3
            assert {e.slot for e in f.events} == {"good", "caution", "support"}
            for e in f.events:
                assert 5 <= e.probability <= 95


def test_caution_band_headline_is_untouched(boards) -> None:
    """s1(주의 우세) 밴드는 이번 슬라이스에서 건드리지 않는다."""
    for board in boards:
        for f, a in zip(board.fortunes, board._headline_audit, strict=True):
            if a.band != "s1":
                continue
            caution = next(e for e in f.events if e.slot == "caution")
            assert a.selected_event_key == caution.event_key
            assert a.selection_reason == "raw_top", "s1 은 캡 대상이 아니다"


# ── 감사 기록(OA-7a) ───────────────────────────────────────────────────────


def test_audit_records_raw_and_final(boards) -> None:
    """원시 선택과 최종 선택을 모두 남긴다 — 3번 감수 범위를 정하는 근거다."""
    for board in boards:
        assert len(board._headline_audit) == 60
        for a in board._headline_audit:
            assert a.raw_event_key and a.selected_event_key
            assert a.eligible_good_count >= 1
            assert a.selection_reason in ("raw_top", "board_domain_cap")
            if a.selection_reason == "raw_top":
                assert a.selected_event_key == a.raw_event_key


def test_audit_does_not_change_api_payload(boards) -> None:
    """감사는 응답 모델 밖에 있다 — 캐시·API 계약 불변."""
    board = boards[0]
    payload = board.model_dump()

    assert "_headline_audit" not in payload
    assert "_cap_unresolved" not in payload

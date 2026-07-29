"""일별 보드의 **선택 단계 추적** — 감사 공용 (측정 전용, 라이브 불변).

OA-9a 에서 감사가 `cautions[0]`(점수순 주의 1위)을 "주의 슬롯 승자"로 셌다. 실제
라이브 선택기는 주의를 good 과 **다른 도메인**에서 뽑으므로, 편재 카드(good 이 money)
에서는 money 주의가 표시되지 않는다. 실측 421건에서 원시 1위는 100% 였으나 **표시는
0건**이었다. 감사가 선택 로직을 흉내 내면 이런 드리프트가 반복된다.

그래서 이 모듈은 **라이브 순수 함수를 그대로 호출**하고 결과에 단계 표시만 붙인다.
자체 구현은 seed 생성 한 줄도 두지 않는다.

    raw_rank1 / raw_top3          점수만으로 매긴 순위
    slot_*_selected               카드에 실제 표시되는 3개
    raw_headline                  보드 캡 **이전** 헤드라인 후보 1위
    final_headline                보드 캡 이후 최종 헤드라인
    board_cap_*                   캡이 옮겼는가

`top1`·`winner`·`selected` 처럼 단계가 불명확한 이름은 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from saju_engines.daily_ilju_fortune import (
    _DOMAIN_HEADLINE_CAP,
    EVENT_SELECTION_COMPAT_SALT,
    _band,
    _headline_candidates,
    _rebalance_headlines,
    _ScoredEvent,
    _select_slots,
)

#: 감사 지표 이름에 허용되는 선택 단계 — 새 지표는 반드시 이 중 하나를 접두어로 쓴다.
STAGES: tuple[str, ...] = (
    "raw_rank1",
    "raw_top3",
    "slot_good_selected",
    "slot_caution_selected",
    "slot_support_selected",
    "raw_headline",
    "final_headline",
    "board_cap_displaced",
    "board_cap_promoted",
)

#: 단계가 불명확해 금지하는 이름 — OA-9a 정정의 재발 방지.
AMBIGUOUS_METRIC_NAMES: frozenset[str] = frozenset({
    "top1", "top3", "winner", "winners", "selected", "caution_slot_wins", "rank1",
})


@dataclass(frozen=True)
class CardTrace:
    """카드 1장이 각 선택 단계에서 무엇을 골랐는가."""

    ilju: str
    band: str
    raw_rank1: str
    raw_top3: tuple[str, ...]
    raw_top3_domains: tuple[str, ...]
    slot_good_selected: str
    slot_caution_selected: str
    slot_support_selected: str
    slot_good_domain: str
    slot_caution_domain: str
    slot_support_domain: str
    raw_headline: str
    raw_headline_domain: str
    final_headline: str
    final_headline_domain: str
    final_headline_probability: int
    board_cap_displaced: bool
    board_cap_reason: str


def trace_board(
    scored_by_ilju: dict[str, list[_ScoredEvent]], day: date,
    cap: float = _DOMAIN_HEADLINE_CAP,
) -> dict[str, CardTrace]:
    """보드 1장을 라이브 경로 그대로 흘려보내고 단계별 선택을 기록한다.

    `compute_board` 의 2패스(슬롯 선발 60건 확정 → 보드 캡 재배정)와 동일한 순서를
    지킨다. 순서가 바뀌면 일주 순번 편향이 생긴다.

    Args:
        scored_by_ilju: 일주별 사건 점수 목록. 후보를 빼고 넣으면 그대로 반사실이 된다.
        day: 대상 날짜(선택 seed 의 일부).
        cap: 도메인 헤드라인 상한. 기본은 라이브 값.

    Returns:
        일주 → 단계별 선택 기록.
    """
    slot_rows: dict[str, tuple[_ScoredEvent, _ScoredEvent, _ScoredEvent, str]] = {}
    candidates: dict[str, list[_ScoredEvent]] = {}
    order: list[str] = []

    for ilju, scored in scored_by_ilju.items():
        seed_base = f"{day.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        good, caution, support = _select_slots(scored, seed_base)
        band = _band(good, caution)
        slot_rows[ilju] = (good, caution, support, band)
        candidates[ilju] = _headline_candidates(good, support, caution, band)
        order.append(ilju)

    headline_pick, cap_reasons, _unresolved = _rebalance_headlines(candidates, order, cap)

    traces: dict[str, CardTrace] = {}
    for ilju, scored in scored_by_ilju.items():
        good, caution, support, band = slot_rows[ilju]
        ranked = sorted(scored, key=lambda s: -s.probability)
        raw_head = candidates[ilju][0]
        final = headline_pick[ilju]
        traces[ilju] = CardTrace(
            ilju=ilju,
            band=band,
            raw_rank1=ranked[0].event_key,
            raw_top3=tuple(s.event_key for s in ranked[:3]),
            raw_top3_domains=tuple(s.domain for s in ranked[:3]),
            slot_good_selected=good.event_key,
            slot_caution_selected=caution.event_key,
            slot_support_selected=support.event_key,
            slot_good_domain=good.domain,
            slot_caution_domain=caution.domain,
            slot_support_domain=support.domain,
            raw_headline=raw_head.event_key,
            raw_headline_domain=raw_head.domain,
            final_headline=final.event_key,
            final_headline_domain=final.domain,
            final_headline_probability=final.probability,
            board_cap_displaced=final.event_key != raw_head.event_key,
            board_cap_reason=cap_reasons.get(ilju, "raw_top"),
        )
    return traces

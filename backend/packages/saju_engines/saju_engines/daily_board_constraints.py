"""OA-6c — domain·event cap 통합 보드 재배정 (**shadow 전용**).

2단계 후처리(domain cap → event cap)는 쓰지 않는다. event cap 교체가 domain 초과를
다시 만들 수 있어 A·B·C 수치를 실제 적용 알고리즘의 결과로 볼 수 없게 된다.

    domain cap AND event_key cap AND 유효 대체 후보
    AND 허용 손실 AND 카드 재이동 금지 AND 결정론

제약 우선순위
    절대(불가침)  같은 슬롯 · headline_slots 자격 · 원래 후보 집합 밖 생성 금지 ·
                 카드당 최대 1회 이동 · 낮은 probability 임의 생성 금지
    조건부       domain cap → event cap → 최대 허용 손실
조건부 제약을 동시에 만족할 수 없으면 초과를 허용하고 사유를 남긴다.
"""

from __future__ import annotations

import collections
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .daily_ilju_fortune import BOARD_REBALANCE_SHADOW_VERSION, _stable_hash


@dataclass(frozen=True)
class HeadlineCandidate:
    """재배정기가 보는 최소 후보 — 점수·판정을 다시 계산하지 않는다."""

    event_key: str
    domain: str
    probability: int


@dataclass(frozen=True)
class Move:
    """카드 1건의 대체 이동 후보."""

    ilju: str
    source_event: str
    source_domain: str
    destination_event: str
    destination_domain: str
    displacement_cost: int
    constraint_relief: int


@dataclass
class RebalanceResult:
    """재배정 결과 + 감사."""

    selections: dict[str, HeadlineCandidate] = field(default_factory=dict)
    moves: list[Move] = field(default_factory=list)
    domain_cap_count: int = 0
    event_cap_count: int = 0
    domain_overflow: int = 0
    event_overflow: int = 0
    overrides: dict[str, int] = field(default_factory=dict)
    contract: str = BOARD_REBALANCE_SHADOW_VERSION

    @property
    def moved_iljus(self) -> set[str]:
        return {m.ilju for m in self.moves}


def cap_count(board_size: int, ratio: float) -> int:
    """비율 → 정수 상한. 감사에는 비율이 아니라 이 값을 기록한다.

    `ceil` 이므로 60일주 기준 20%→12, 18%→11, 15%→9, 30%→18이다.
    """
    return max(1, math.ceil(board_size * ratio))


def _counts(selections: Mapping[str, HeadlineCandidate]):
    events = collections.Counter(c.event_key for c in selections.values())
    domains = collections.Counter(c.domain for c in selections.values())
    return events, domains


def rebalance_headlines_with_constraints(
    raw_selections: Mapping[str, HeadlineCandidate],
    candidate_map: Mapping[str, Sequence[HeadlineCandidate]],
    *,
    domain_cap: int,
    event_cap: int,
    max_displacement_cost: int | None = None,
    contract: str = BOARD_REBALANCE_SHADOW_VERSION,
) -> RebalanceResult:
    """두 제약을 한 루프에서 함께 만족시킨다.

    "가장 초과한 항목 하나를 골라 옮긴다"만으로는 부족하다 — 가능한 이동을 **전역으로**
    평가해 제약 완화량이 큰 것부터 고른다. 그래야 두 축을 동시에 푸는 이동
    (`money_small_gain → teamwork_flow`)이 한 축만 푸는 이동
    (`money_small_gain → money_good_deal`)보다 먼저 선택된다.

    Args:
        raw_selections: 일주 → 원시 승자.
        candidate_map: 일주 → 허용 후보 목록(이 밖의 사건을 만들지 않는다).
        domain_cap: 도메인 정수 상한.
        event_cap: 사건 정수 상한.
        max_displacement_cost: 허용 점수 손실 상한(None이면 무제한).
        contract: 계약 문자열(결정론 tie-break 성분).

    Returns:
        최종 선택·이동 내역·초과 잔량·override 사유.
    """
    selections = dict(raw_selections)
    result = RebalanceResult(
        domain_cap_count=domain_cap, event_cap_count=event_cap, contract=contract
    )
    moved: set[str] = set()

    for _ in range(len(selections)):
        events, domains = _counts(selections)
        over_event = {k for k, n in events.items() if n > event_cap}
        over_domain = {k for k, n in domains.items() if n > domain_cap}
        if not over_event and not over_domain:
            break

        moves: list[Move] = []
        blocked: collections.Counter[str] = collections.Counter()
        for ilju, cur in selections.items():
            if ilju in moved:
                continue
            if cur.event_key not in over_event and cur.domain not in over_domain:
                continue
            alts = [c for c in candidate_map.get(ilju, ()) if c.event_key != cur.event_key]
            if not alts:
                blocked["no_cross_event_alternative"] += 1
                continue
            for alt in alts:
                cost = cur.probability - alt.probability
                if max_displacement_cost is not None and cost > max_displacement_cost:
                    # 다양성을 위해 해석 적합성을 예산 밖까지 희생하지 않는다.
                    blocked["cost_budget_exceeded"] += 1
                    continue
                # 목적지 여유는 **두 축 모두** 본다. 같은 도메인 안 이동이면 도메인
                # 총량은 그대로이므로 event 여유만 확인하면 된다.
                if events.get(alt.event_key, 0) + 1 > event_cap:
                    blocked["destination_event_full"] += 1
                    continue
                if alt.domain != cur.domain and domains.get(alt.domain, 0) + 1 > domain_cap:
                    blocked["destination_domain_full"] += 1
                    continue
                relief = int(cur.event_key in over_event) + int(
                    cur.domain in over_domain and alt.domain != cur.domain
                )
                if relief <= 0:
                    continue
                moves.append(
                    Move(
                        ilju=ilju, source_event=cur.event_key, source_domain=cur.domain,
                        destination_event=alt.event_key, destination_domain=alt.domain,
                        displacement_cost=cost, constraint_relief=relief,
                    )
                )
        if not moves:
            # 유효 해 없음 — 초과를 허용하고 **왜** 못 옮겼는지 사유를 남긴다.
            for reason, n in blocked.items():
                result.overrides[reason] = result.overrides.get(reason, 0) + n
            break

        events_now, domains_now = events, domains
        best = min(
            moves,
            key=lambda m: (
                -m.constraint_relief,
                m.displacement_cost,
                events_now.get(m.destination_event, 0),
                domains_now.get(m.destination_domain, 0),
                _stable_hash(f"{contract}|{m.ilju}|{m.destination_event}"),
                m.ilju,
                m.destination_event,
            ),
        )
        alt = next(
            c for c in candidate_map[best.ilju] if c.event_key == best.destination_event
        )
        selections[best.ilju] = alt
        moved.add(best.ilju)
        result.moves.append(best)

    events, domains = _counts(selections)
    result.selections = selections
    result.event_overflow = sum(max(0, n - event_cap) for n in events.values())
    result.domain_overflow = sum(max(0, n - domain_cap) for n in domains.values())
    if result.event_overflow and result.domain_overflow:
        result.overrides["combined_constraints_infeasible"] = 1
    return result


__all__ = [
    "HeadlineCandidate",
    "Move",
    "RebalanceResult",
    "cap_count",
    "rebalance_headlines_with_constraints",
]

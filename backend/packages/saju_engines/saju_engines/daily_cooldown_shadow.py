"""OA-6f — 일주별 종단 반복 cooldown (**shadow 전용**, 라이브 불변).

OA-9r 이 문제의 위치를 옮겼다. 하루 보드 단면에서는 선택기가 편중을 거의 상쇄한다
(final headline: money 29.0% · work 27.7%). 남는 것은 **같은 일주가 시간축에서 같은
사건을 반복해서 보는 것**이다 — money 후보를 통째로 빼면 종단 최빈 점유 p90 이
36.7% → 22.2%, 7일 내 3회 반복이 24.4% → 15.0% 로 떨어진다.

cooldown 은 점수를 감점하지 않는다. 원래 점수·band·원래 순위를 그대로 두고
**대체 선택**만 한다. 사건을 무조건 금지하면 값싼 filler 가 올라오므로,
hard block 이 아니라 **손실 예산 안에서의 대체**로 설계한다.

세 제약을 한 루프에서 함께 만족시킨다 — 두 패스로 나누면
`board cap 이 A→B` → `cooldown 이 B→C` → `board cap 이 다시 C 를 이동` 하는
ping-pong 이 생긴다(OA-6b 에서 실제로 겪었다).

    domain cap AND event cap AND 종단 cooldown
    AND 유효 대체 후보 AND 허용 손실 AND 카드당 1회 이동 AND 결정론
"""

from __future__ import annotations

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .daily_board_constraints import HeadlineCandidate, Move
from .daily_ilju_fortune import _stable_hash

#: cooldown 계약 버전 — shadow 산출물에 찍어 비교 대상을 특정한다.
COOLDOWN_CONTRACT_VERSION = "cooldown.v1-event-key"

#: 회전 창(오늘 포함). 7일 안에 같은 사건이 3회 이상이면 위반이다.
COOLDOWN_WINDOW = 7
COOLDOWN_MAX_IN_WINDOW = 2  # 오늘 것을 더해 3회가 되면 위반

# ── 위반 코드 ──────────────────────────────────────────────────────────────

#: 직전 날짜와 같은 event_key.
CONSECUTIVE_EVENT_REPEAT = "CONSECUTIVE_EVENT_REPEAT"
#: 오늘 선택되면 최근 7일 중 세 번째 이상.
ROLLING_7D_THIRD_OCCURRENCE = "ROLLING_7D_THIRD_OCCURRENCE"

# ── 처리 코드 ──────────────────────────────────────────────────────────────
#
# 분모를 섞지 않는다. cooldown 지표는 **cooldown 이 트리거된 카드**만 분모로 삼고,
# 캡(도메인·사건) 때문에 이동한/막힌 카드는 별도로 센다. 두 축을 한 코드 집합에
# 담으면 "미해소 8.9%"와 "미해소 21.4%"가 동시에 나오는 일이 생긴다(실제로 겪었다).

COOLDOWN_ALTERNATIVE_SELECTED = "COOLDOWN_ALTERNATIVE_SELECTED"
#: 캡만으로 이동한 카드 — cooldown 트리거가 아니었다.
CAP_ALTERNATIVE_SELECTED = "CAP_ALTERNATIVE_SELECTED"

#: 미해소 사유 — "사건이 없다"와 "제약으로 막혔다"와 "예산 밖이다"를 분리한다.
NO_ELIGIBLE_HEADLINE_EVENT = "NO_ELIGIBLE_HEADLINE_EVENT"
ALL_CANDIDATES_COOLDOWN_BLOCKED = "ALL_CANDIDATES_COOLDOWN_BLOCKED"
ALL_CANDIDATES_DOMAIN_CAP_BLOCKED = "ALL_CANDIDATES_DOMAIN_CAP_BLOCKED"
ALL_CANDIDATES_EVENT_CAP_BLOCKED = "ALL_CANDIDATES_EVENT_CAP_BLOCKED"
ONLY_CAUTION_CANDIDATES = "ONLY_CAUTION_CANDIDATES"
LOSS_BUDGET_EXCEEDED = "LOSS_BUDGET_EXCEEDED"

#: 사건 자체가 없어서 못 바꾼 사유(신규 사건 설계의 근거).
_ABSENCE_REASONS = (NO_ELIGIBLE_HEADLINE_EVENT, ONLY_CAUTION_CANDIDATES)
#: 선택 제약으로 막힌 사유(정책 조정의 대상).
_CONSTRAINT_REASONS = (
    ALL_CANDIDATES_COOLDOWN_BLOCKED,
    ALL_CANDIDATES_DOMAIN_CAP_BLOCKED,
    ALL_CANDIDATES_EVENT_CAP_BLOCKED,
)


@dataclass(frozen=True)
class UnresolvedCard:
    """대체하지 못한 카드 1건 — G2 가 무엇을 회복해야 하는지의 원자료."""

    ilju: str
    reason: str
    original_event_key: str
    original_domain: str
    original_probability: int
    #: 예산만 아니면 쓸 수 있었던 최선 대안(없으면 None).
    best_alternative_event_key: str | None = None
    best_alternative_domain: str | None = None
    #: 현재 승자와의 점수 차(양수 = 대안이 낮다).
    probability_gap: int | None = None
    #: 이 대안이 예산 안으로 들어오려면 몇 점을 더 받아야 하는가.
    required_uplift_to_fit: int | None = None


def cooldown_violation(history: Sequence[str], event_key: str) -> tuple[str, ...]:
    """이 사건을 오늘 고르면 어떤 반복 규칙을 어기는가.

    Args:
        history: 그 일주의 과거 선택(오래된 순). 오늘 것은 포함하지 않는다.
        event_key: 오늘 고르려는 사건.

    Returns:
        위반 코드들. 비어 있으면 위반 없음.
    """
    codes: list[str] = []
    if history and history[-1] == event_key:
        codes.append(CONSECUTIVE_EVENT_REPEAT)
    window = list(history[-(COOLDOWN_WINDOW - 1):])
    if window.count(event_key) >= COOLDOWN_MAX_IN_WINDOW:
        codes.append(ROLLING_7D_THIRD_OCCURRENCE)
    return tuple(codes)


@dataclass
class CooldownResult:
    """재배정 결과 + 감사.

    카드 분할은 **상호 배타적**이다:

        cooldown_triggered = cooldown_moved + unresolved(전 사유)
        total_cards        = cooldown_triggered + not_triggered
    """

    selections: dict[str, HeadlineCandidate] = field(default_factory=dict)
    moves: list[Move] = field(default_factory=list)
    #: 일주 → 처리 코드(대체 성공/미해소 사유)
    codes: dict[str, str] = field(default_factory=dict)
    #: 일주 → 원래 승자가 어긴 반복 규칙(트리거된 카드)
    violations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: cooldown 이 트리거됐으나 대체하지 못한 카드의 원자료
    unresolved_cards: list[UnresolvedCard] = field(default_factory=list)
    #: 캡만으로 이동한 카드(cooldown 분모에 넣지 않는다)
    cap_only_moves: int = 0
    domain_cap_count: int = 0
    event_cap_count: int = 0
    domain_overflow: int = 0
    event_overflow: int = 0
    contract: str = COOLDOWN_CONTRACT_VERSION

    @property
    def moved_iljus(self) -> set[str]:
        return {m.ilju for m in self.moves}

    @property
    def cooldown_triggered(self) -> int:
        """원시 승자가 반복 규칙을 어긴 카드 수 — cooldown 지표의 유일한 분모."""
        return len(self.violations)

    @property
    def cooldown_moved(self) -> int:
        return sum(
            1 for ilju in self.violations
            if self.codes.get(ilju) == COOLDOWN_ALTERNATIVE_SELECTED
        )

    @property
    def cooldown_unresolved(self) -> int:
        return len(self.unresolved_cards)

    @property
    def unresolved_by_absence(self) -> int:
        return sum(1 for u in self.unresolved_cards if u.reason in _ABSENCE_REASONS)

    @property
    def unresolved_by_constraint(self) -> int:
        return sum(1 for u in self.unresolved_cards if u.reason in _CONSTRAINT_REASONS)

    @property
    def unresolved_by_budget(self) -> int:
        return sum(1 for u in self.unresolved_cards if u.reason == LOSS_BUDGET_EXCEEDED)


def _counts(selections: Mapping[str, HeadlineCandidate]):
    events = collections.Counter(c.event_key for c in selections.values())
    domains = collections.Counter(c.domain for c in selections.values())
    return events, domains



def _diagnose(
    ilju: str, cur: HeadlineCandidate, alts: Sequence[HeadlineCandidate],
    blocked: Mapping[str, int], budget_best: tuple[int, HeadlineCandidate] | None,
    budget: int | None,
) -> UnresolvedCard:
    """대체 실패 사유를 하나로 확정한다.

    우선순위는 **처방이 갈리는 순서**다 — 사건이 아예 없다(신규 설계) > 점수만
    모자라다(조건부 라우팅) > 선택 제약(정책 조정). 예산만 모자란 경우에는 최선
    대안과 필요한 추가 점수를 함께 남겨, G2 가 회복 가능 규모를 셀 수 있게 한다.

    Args:
        ilju: 일주.
        cur: 현재 승자.
        alts: 현재 승자를 제외한 카드 내 후보.
        blocked: 사유별 차단 횟수.
        budget_best: 예산만 아니면 쓸 수 있던 최선 대안 (비용, 후보).
        budget: 허용 손실 상한.

    Returns:
        미해소 카드 1건.
    """
    if not alts:
        reason = NO_ELIGIBLE_HEADLINE_EVENT
    elif budget_best is not None:
        cost, alt = budget_best
        return UnresolvedCard(
            ilju=ilju, reason=LOSS_BUDGET_EXCEEDED,
            original_event_key=cur.event_key, original_domain=cur.domain,
            original_probability=cur.probability,
            best_alternative_event_key=alt.event_key,
            best_alternative_domain=alt.domain,
            probability_gap=cost,
            required_uplift_to_fit=cost - (budget if budget is not None else cost),
        )
    elif blocked:
        reason = blocked.most_common(1)[0][0] if isinstance(
            blocked, collections.Counter
        ) else next(iter(blocked))
    else:
        reason = NO_ELIGIBLE_HEADLINE_EVENT
    return UnresolvedCard(
        ilju=ilju, reason=reason, original_event_key=cur.event_key,
        original_domain=cur.domain, original_probability=cur.probability,
    )


def rebalance_with_cooldown(
    raw_selections: Mapping[str, HeadlineCandidate],
    candidate_map: Mapping[str, Sequence[HeadlineCandidate]],
    history: Mapping[str, Sequence[str]],
    *,
    domain_cap: int,
    event_cap: int | None = None,
    max_displacement_cost: int | None = None,
    contract: str = COOLDOWN_CONTRACT_VERSION,
) -> CooldownResult:
    """domain·event·종단 세 축을 한 루프에서 함께 푼다.

    대체 후보는 **그 카드에 실제 표시되는 사건**(`_headline_candidates` 결과)뿐이다.
    본문에 없는 이야기를 제목으로 올리면 카드가 자기모순이 되기 때문이다. 그래서
    대체하지 못한 카드는 사유를 나눠 남긴다 — "사건이 아예 없다"(신규 설계 근거)와
    "선택 제약으로 막혔다"(정책 조정 대상)와 "예산 밖이다"(조건부 라우팅 대상)는
    서로 다른 처방을 요구하기 때문이다.

    Args:
        raw_selections: 일주 → 원시 승자(보드 캡 이전).
        candidate_map: 일주 → 허용 후보(이 밖의 사건을 만들지 않는다).
        history: 일주 → 과거 선택 이력(오래된 순).
        domain_cap: 도메인 정수 상한.
        event_cap: 사건 정수 상한. None 이면 사건 캡 없음(F3 처럼 cooldown 만).
        max_displacement_cost: 허용 점수 손실 상한. None 이면 무제한.
        contract: 결정론 tie-break 성분.

    Returns:
        최종 선택·이동 내역·처리 코드·잔여 초과.
    """
    selections = dict(raw_selections)
    result = CooldownResult(
        domain_cap_count=domain_cap, event_cap_count=event_cap or 0, contract=contract
    )
    moved: set[str] = set()
    last_pending: dict[str, UnresolvedCard] = {}
    effective_event_cap = event_cap if event_cap is not None else len(selections)

    for ilju, cur in selections.items():
        codes = cooldown_violation(history.get(ilju, ()), cur.event_key)
        if codes:
            result.violations[ilju] = codes

    for _ in range(len(selections)):
        events, domains = _counts(selections)
        over_event = {k for k, n in events.items() if n > effective_event_cap}
        over_domain = {k for k, n in domains.items() if n > domain_cap}
        stale = {
            ilju for ilju, cur in selections.items()
            if ilju not in moved and cooldown_violation(history.get(ilju, ()), cur.event_key)
        }
        if not over_event and not over_domain and not stale:
            break

        moves: list[Move] = []
        pending: dict[str, UnresolvedCard] = {}
        for ilju, cur in selections.items():
            if ilju in moved:
                continue
            needs = (
                cur.event_key in over_event
                or cur.domain in over_domain
                or ilju in stale
            )
            if not needs:
                continue
            past = history.get(ilju, ())
            alts = [c for c in candidate_map.get(ilju, ()) if c.event_key != cur.event_key]
            blocked: collections.Counter[str] = collections.Counter()
            budget_best: tuple[int, HeadlineCandidate] | None = None
            for alt in alts:
                cost = cur.probability - alt.probability
                if cooldown_violation(past, alt.event_key):
                    blocked[ALL_CANDIDATES_COOLDOWN_BLOCKED] += 1
                    continue
                if events.get(alt.event_key, 0) + 1 > effective_event_cap:
                    blocked[ALL_CANDIDATES_EVENT_CAP_BLOCKED] += 1
                    continue
                if alt.domain != cur.domain and domains.get(alt.domain, 0) + 1 > domain_cap:
                    blocked[ALL_CANDIDATES_DOMAIN_CAP_BLOCKED] += 1
                    continue
                if max_displacement_cost is not None and cost > max_displacement_cost:
                    # 다른 제약은 모두 통과했고 **점수만** 모자란다 — G2 의 표적이다.
                    blocked[LOSS_BUDGET_EXCEEDED] += 1
                    if budget_best is None or cost < budget_best[0]:
                        budget_best = (cost, alt)
                    continue
                relief = (
                    int(cur.event_key in over_event)
                    + int(cur.domain in over_domain)
                    + int(ilju in stale)
                )
                moves.append(Move(
                    ilju=ilju, source_event=cur.event_key, source_domain=cur.domain,
                    destination_event=alt.event_key, destination_domain=alt.domain,
                    displacement_cost=cost, constraint_relief=relief,
                ))
            if not any(m.ilju == ilju for m in moves):
                pending[ilju] = _diagnose(
                    ilju, cur, alts, blocked, budget_best, max_displacement_cost
                )

        # 마지막으로 본 진단을 남긴다 — 이동이 없어 루프가 끝나는 경로에서도
        # 사유가 유실되면 안 된다(그러면 전부 NO_ELIGIBLE_HEADLINE_EVENT 로 뭉개진다).
        last_pending = pending

        if not moves:
            break

        best = min(
            moves,
            key=lambda m: (
                -m.constraint_relief, m.displacement_cost,
                _stable_hash(f"{contract}|{m.ilju}|{m.destination_event}"),
            ),
        )
        chosen = next(
            c for c in candidate_map[best.ilju] if c.event_key == best.destination_event
        )
        selections[best.ilju] = chosen
        moved.add(best.ilju)
        result.moves.append(best)
        result.codes[best.ilju] = (
            COOLDOWN_ALTERNATIVE_SELECTED if best.ilju in result.violations
            else CAP_ALTERNATIVE_SELECTED
        )

    events, domains = _counts(selections)
    result.selections = selections
    result.event_overflow = sum(
        max(0, n - effective_event_cap) for n in events.values()
    ) if event_cap is not None else 0
    result.domain_overflow = sum(max(0, n - domain_cap) for n in domains.values())
    result.cap_only_moves = sum(
        1 for m in result.moves if m.ilju not in result.violations
    )
    # 미해소는 **cooldown 이 트리거된 카드**만 센다 — 캡 때문에 막힌 카드를 섞지 않는다.
    for ilju in result.violations:
        if result.codes.get(ilju) == COOLDOWN_ALTERNATIVE_SELECTED:
            continue
        card = last_pending.get(ilju)
        if card is None:
            cur = selections[ilju]
            card = UnresolvedCard(
                ilju=ilju, reason=NO_ELIGIBLE_HEADLINE_EVENT,
                original_event_key=cur.event_key, original_domain=cur.domain,
                original_probability=cur.probability,
            )
        result.unresolved_cards.append(card)
        result.codes[ilju] = card.reason
    return result

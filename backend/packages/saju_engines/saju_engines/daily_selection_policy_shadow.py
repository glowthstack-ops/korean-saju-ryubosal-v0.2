"""OA-6f2 — 선택 활용 최적화 (**shadow 전용**, 라이브 불변).

F4@7p 실측이 남긴 문제: 후보는 있는데 선택으로 전환되지 않는다.

    eligible_unique_p10       17
    within_budget_unique_p10  16
    selected_unique_p10       14

미해소 478건 중 사건 부재는 27건(5.6%)뿐이다. 나머지는 예산(328)과 선택 제약(123)이다.
따라서 사전을 건드리기 전에 **같은 제약 안에서 더 나은 배치**를 찾아야 한다.

세 가지 정책을 스위치로 분리한다(같은 코드 경로에서 비교해야 차이가 정책 차이다):

    P1 global_swap       카드별 순차 처리 대신 전역 배정 + augmenting swap
    P2 severity_tiers    반복 위반을 강도로 나눠, 더 약한 반복으로의 이동을 허용
    P3 recency_rotation  예산 안 후보 중 **덜 쓰인** 사건을 먼저 고른다

세 정책 모두 점수·명리 판정을 바꾸지 않는다. 이미 카드에 표시되는 후보 가운데
어느 것을 제목으로 올릴지만 정한다.

P1 이 푸는 것 — 순차 처리의 선점 문제:

    A 카드가 사건 X 로 이동 → event cap 이 참
    → B 카드는 X 만 유효 대안이라 미해소

    전역으로 보면 A→Y, B→X 로 둘 다 해결된다.
"""

from __future__ import annotations

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .daily_board_constraints import HeadlineCandidate, Move
from .daily_cooldown_shadow import (
    ALL_CANDIDATES_COOLDOWN_BLOCKED,
    ALL_CANDIDATES_DOMAIN_CAP_BLOCKED,
    ALL_CANDIDATES_EVENT_CAP_BLOCKED,
    COOLDOWN_ALTERNATIVE_SELECTED,
    COOLDOWN_WINDOW,
    LOSS_BUDGET_EXCEEDED,
    NO_ELIGIBLE_HEADLINE_EVENT,
    UnresolvedCard,
    cooldown_violation,
)
from .daily_ilju_fortune import _stable_hash

#: 정책 계약 버전.
SELECTION_POLICY_VERSION = "selection-policy.v1-global-swap"

#: augmenting 탐색 깊이 — 1이면 직접 이동만, 2면 한 장을 밀어내고 들어간다.
MAX_CHAIN_DEPTH = 2

# ── 반복 위반 강도 (P2) ────────────────────────────────────────────────────
#
# 셋을 한 덩어리로 취급하면 "연속 반복"과 "7일 세 번째"를 같은 무게로 막게 된다.
# 연속이 체감상 가장 나쁘므로 가장 높은 강도를 준다.

SEVERITY_CLEAN = 0
SEVERITY_THIRD_IN_WINDOW = 1        # 7일 창 세 번째
SEVERITY_FOURTH_OR_MORE = 2         # 7일 창 네 번째 이상
SEVERITY_CONSECUTIVE = 3            # 직전 날짜와 동일

SEVERITY_NAMES = {
    SEVERITY_CLEAN: "CLEAN",
    SEVERITY_THIRD_IN_WINDOW: "ROLLING_7D_THIRD_OCCURRENCE_BLOCKED",
    SEVERITY_FOURTH_OR_MORE: "ROLLING_7D_FOURTH_OR_MORE_BLOCKED",
    SEVERITY_CONSECUTIVE: "CONSECUTIVE_REPEAT_BLOCKED",
}


def repeat_severity(history: Sequence[str], event_key: str) -> int:
    """이 사건을 오늘 고를 때의 반복 강도. 높을수록 나쁘다.

    Args:
        history: 그 일주의 과거 선택(오래된 순, 오늘 미포함).
        event_key: 오늘 고르려는 사건.

    Returns:
        0(문제 없음) ~ 3(연속 반복).
    """
    if history and history[-1] == event_key:
        return SEVERITY_CONSECUTIVE
    window = list(history[-(COOLDOWN_WINDOW - 1):])
    count = window.count(event_key)
    if count >= 3:
        return SEVERITY_FOURTH_OR_MORE
    if count >= 2:
        return SEVERITY_THIRD_IN_WINDOW
    return SEVERITY_CLEAN


# ── good 슬롯 표시 대표 선택 (P4) ──────────────────────────────────────────
#
# 이것은 **원판정을 덮어쓰는 것이 아니다.** 후보는 전부 기존 명리 점수로 산출된
# good 헤드라인 자격 사건이고, 같은 valence 이며, 손실 예산 안에 있다. 바뀌는 것은
# "원시 1위를 공개한다"에서 "충분히 강한 good 후보 중 오늘 보여줄 대표 장면을
# 고른다"로의 **슬롯 의미 정의**다.
#
# 그래서 사용자 노출 문구에서 '오늘 가장 강한 사건'·'1위'·'점수가 가장 높은' 같은
# 표현을 쓰면 안 된다. 감사 데이터에는 원시 1위와 표시 대표를 **분리해** 남긴다.

RAW_GOOD_WINNER_SELECTED = "RAW_GOOD_WINNER_SELECTED"
LONGITUDINAL_ALTERNATIVE_SELECTED = "LONGITUDINAL_ALTERNATIVE_SELECTED"
NO_VALID_LONGITUDINAL_ALTERNATIVE = "NO_VALID_LONGITUDINAL_ALTERNATIVE"
GOOD_LOSS_BUDGET_EXCEEDED = "LOSS_BUDGET_EXCEEDED"


@dataclass(frozen=True)
class GoodRepresentative:
    """good 슬롯 표시 대표 1건 — 원시 1위와 표시 선택을 분리해 남긴다."""

    raw_good_winner: str
    raw_good_probability: int
    display_good_representative: str
    display_good_probability: int
    good_selection_reason: str
    display_displacement_loss: int
    #: 예산만 아니면 쓸 수 있었던 최선 대안(G2 표적 산정용).
    best_blocked_alternative: str | None = None
    required_uplift_to_fit: int | None = None


def select_good_representative(
    goods: Sequence[tuple[str, int]], history: Sequence[str], budget: int,
) -> GoodRepresentative:
    """반복을 피하는 good 표시 대표를 고른다.

    후보를 만들지 않는다 — 넘겨받은 good 자격 사건 안에서만 고른다. 반복을 피할 수
    있는 후보가 예산 안에 없으면 **원시 1위를 그대로 쓴다**(억지로 낮은 사건을
    올리지 않는다).

    Args:
        goods: (event_key, probability) 목록. 점수 내림차순일 필요는 없다.
        history: 그 일주의 과거 표시 대표(오래된 순).
        budget: 허용 점수 손실 상한.

    Returns:
        표시 대표 + 선택 사유 + 손실.
    """
    ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
    top_key, top_p = ranked[0]
    if repeat_severity(history, top_key) == SEVERITY_CLEAN:
        return GoodRepresentative(
            raw_good_winner=top_key, raw_good_probability=top_p,
            display_good_representative=top_key, display_good_probability=top_p,
            good_selection_reason=RAW_GOOD_WINNER_SELECTED,
            display_displacement_loss=0,
        )

    blocked_best: tuple[int, str] | None = None
    for key, p in ranked[1:]:
        if repeat_severity(history, key) != SEVERITY_CLEAN:
            continue
        loss = top_p - p
        if loss <= budget:
            return GoodRepresentative(
                raw_good_winner=top_key, raw_good_probability=top_p,
                display_good_representative=key, display_good_probability=p,
                good_selection_reason=LONGITUDINAL_ALTERNATIVE_SELECTED,
                display_displacement_loss=loss,
            )
        if blocked_best is None or loss < blocked_best[0]:
            blocked_best = (loss, key)

    if blocked_best is not None:
        loss, key = blocked_best
        return GoodRepresentative(
            raw_good_winner=top_key, raw_good_probability=top_p,
            display_good_representative=top_key, display_good_probability=top_p,
            good_selection_reason=GOOD_LOSS_BUDGET_EXCEEDED,
            display_displacement_loss=0,
            best_blocked_alternative=key, required_uplift_to_fit=loss - budget,
        )
    return GoodRepresentative(
        raw_good_winner=top_key, raw_good_probability=top_p,
        display_good_representative=top_key, display_good_probability=top_p,
        good_selection_reason=NO_VALID_LONGITUDINAL_ALTERNATIVE,
        display_displacement_loss=0,
    )


@dataclass(frozen=True)
class SelectionPolicy:
    """OA-6f2 실험군 — 세 축을 독립으로 켠다."""

    global_swap: bool = False
    severity_tiers: bool = False
    recency_rotation: bool = False


#: P0 — 아무 정책도 켜지 않은 기본값(인자 기본값용 단일 객체).
BASELINE_POLICY = SelectionPolicy()


@dataclass
class PolicyResult:
    """배정 결과 + 감사. 카드 분할은 `CooldownResult` 와 같은 규약이다."""

    selections: dict[str, HeadlineCandidate] = field(default_factory=dict)
    moves: list[Move] = field(default_factory=list)
    codes: dict[str, str] = field(default_factory=dict)
    violations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    unresolved_cards: list[UnresolvedCard] = field(default_factory=list)
    #: augmenting 체인으로 **밀려난** 카드 수(자신은 위반이 아니었다)
    displaced_by_chain: int = 0
    cap_only_moves: int = 0
    domain_overflow: int = 0
    event_overflow: int = 0
    #: 강도 계층 허용으로 남은 약한 반복(P2)
    accepted_weaker_repeat: int = 0
    contract: str = SELECTION_POLICY_VERSION

    @property
    def cooldown_triggered(self) -> int:
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


def _counts(selections: Mapping[str, HeadlineCandidate]):
    return (
        collections.Counter(c.event_key for c in selections.values()),
        collections.Counter(c.domain for c in selections.values()),
    )


def _candidate_order(
    cur: HeadlineCandidate, alts: Sequence[HeadlineCandidate],
    history: Sequence[str], policy: SelectionPolicy, recent30: Mapping[str, int],
    last_seen: Mapping[str, int], today: int,
) -> list[HeadlineCandidate]:
    """후보 평가 순서 — P3 가 켜지면 **덜 쓰인 사건**이 앞으로 온다.

    점수를 바꾸지 않는다. 예산 안에서 이미 해석 가능한 후보들 사이의 순서만 정한다.
    """
    def key(c: HeadlineCandidate) -> tuple:
        loss = cur.probability - c.probability
        sev = repeat_severity(history, c.event_key)
        stable = _stable_hash(f"{SELECTION_POLICY_VERSION}|{cur.event_key}|{c.event_key}")
        if not policy.recency_rotation:
            return (sev, loss, stable)
        since = today - last_seen.get(c.event_key, today - 999)
        return (sev, recent30.get(c.event_key, 0), -since, loss, stable)

    return sorted(alts, key=key)


def _acceptable_severity(
    cur_sev: int, alt_sev: int, policy: SelectionPolicy
) -> bool:
    """이 대안을 반복 관점에서 받아들일 수 있는가.

    기본은 **완전히 깨끗한 후보만** 허용한다. P2 는 여기에 "현재보다 약한 반복이면
    허용"을 더한다 — 연속 반복(강도 3)에서 7일 세 번째(강도 1)로 내려가는 이동은
    최장 연속을 악화시킬 수 없으므로 안전하다.
    """
    if alt_sev == SEVERITY_CLEAN:
        return True
    if not policy.severity_tiers:
        return False
    # 연속 반복은 어떤 경우에도 새로 만들지 않는다(최장 연속 기준을 지킨다).
    if alt_sev >= SEVERITY_CONSECUTIVE:
        return False
    return alt_sev < cur_sev


def _find_chain(
    ilju: str, selections: dict[str, HeadlineCandidate],
    raw: Mapping[str, HeadlineCandidate],
    candidate_map: Mapping[str, Sequence[HeadlineCandidate]],
    history: Mapping[str, Sequence[str]], moved: set[str],
    *, domain_cap: int, event_cap: int, budget: int | None,
    policy: SelectionPolicy, recent30, last_seen, today: int,
    depth: int, in_chain: tuple[str, ...] = (),
) -> list[tuple[str, HeadlineCandidate]] | None:
    """이 카드를 옮길 이동(또는 이동 사슬)을 찾는다.

    깊이 2면 "먼저 자리를 차지한 카드를 다른 곳으로 보내고 들어가기"가 가능해진다.
    사슬 안에 같은 카드가 두 번 들어가지 않으므로 순환 이동은 구조적으로 없다.

    Returns:
        [(일주, 새 후보), ...] 또는 None.
    """
    cur = selections[ilju]
    cur_sev = repeat_severity(history.get(ilju, ()), cur.event_key)
    events, domains = _counts(selections)
    alts = [c for c in candidate_map.get(ilju, ()) if c.event_key != cur.event_key]
    base = raw[ilju].probability

    for alt in _candidate_order(
        cur, alts, history.get(ilju, ()), policy, recent30.get(ilju, {}),
        last_seen.get(ilju, {}), today,
    ):
        if budget is not None and base - alt.probability > budget:
            continue
        if not _acceptable_severity(
            cur_sev, repeat_severity(history.get(ilju, ()), alt.event_key), policy
        ):
            continue

        event_free = events.get(alt.event_key, 0) < event_cap
        domain_free = (
            alt.domain == cur.domain or domains.get(alt.domain, 0) < domain_cap
        )
        if event_free and domain_free:
            return [(ilju, alt)]

        if not policy.global_swap or depth <= 1:
            continue

        # 자리를 막고 있는 카드를 하나 골라 먼저 내보낸다(결정론 순서).
        blockers = sorted(
            k for k, sel in selections.items()
            if k != ilju and k not in moved and k not in in_chain
            and (
                (not event_free and sel.event_key == alt.event_key)
                or (not domain_free and sel.domain == alt.domain)
            )
        )
        for b in blockers:
            sub = _find_chain(
                b, selections, raw, candidate_map, history, moved,
                domain_cap=domain_cap, event_cap=event_cap, budget=budget,
                policy=policy, recent30=recent30, last_seen=last_seen, today=today,
                depth=depth - 1, in_chain=(*in_chain, ilju),
            )
            if sub is None:
                continue
            # 밀어낸 뒤 실제로 자리가 나는지 확인한다.
            trial = dict(selections)
            for k, c in sub:
                trial[k] = c
            ev2, dm2 = _counts(trial)
            if ev2.get(alt.event_key, 0) >= event_cap:
                continue
            if alt.domain != cur.domain and dm2.get(alt.domain, 0) >= domain_cap:
                continue
            return [*sub, (ilju, alt)]
    return None


def select_board(
    raw_selections: Mapping[str, HeadlineCandidate],
    candidate_map: Mapping[str, Sequence[HeadlineCandidate]],
    history: Mapping[str, Sequence[str]],
    *,
    domain_cap: int,
    event_cap: int | None = None,
    max_displacement_cost: int | None = None,
    policy: SelectionPolicy = BASELINE_POLICY,
    today: int = 0,
) -> PolicyResult:
    """보드 1장의 헤드라인을 정책에 따라 배정한다.

    Args:
        raw_selections: 일주 → 원시 승자.
        candidate_map: 일주 → 카드에 실제 표시되는 후보(이 밖의 사건을 만들지 않는다).
        history: 일주 → 과거 선택 이력(오래된 순).
        domain_cap: 도메인 정수 상한.
        event_cap: 사건 정수 상한. None 이면 사건 캡 없음.
        max_displacement_cost: 허용 점수 손실 상한(원시 승자 기준).
        policy: 실험군 스위치.
        today: 날짜 서수 — P3 의 '마지막 선택 이후 경과'를 재는 기준.

    Returns:
        최종 배정 + 감사.
    """
    selections = dict(raw_selections)
    result = PolicyResult(contract=SELECTION_POLICY_VERSION)
    effective_event_cap = event_cap if event_cap is not None else len(selections)
    moved: set[str] = set()

    for ilju, cur in selections.items():
        codes = cooldown_violation(history.get(ilju, ()), cur.event_key)
        if codes:
            result.violations[ilju] = codes

    # P3 용 사용량 — 이력에서 파생하므로 별도 상태를 두지 않는다.
    recent30: dict[str, dict[str, int]] = {}
    last_seen: dict[str, dict[str, int]] = {}
    for ilju, past in history.items():
        recent30[ilju] = collections.Counter(past[-30:])
        seen: dict[str, int] = {}
        for offset, key in enumerate(past):
            seen[key] = today - (len(past) - offset)
        last_seen[ilju] = seen

    progress = True
    while progress:
        progress = False
        events, domains = _counts(selections)
        over_event = {k for k, n in events.items() if n > effective_event_cap}
        over_domain = {k for k, n in domains.items() if n > domain_cap}
        targets = sorted(
            ilju for ilju, cur in selections.items()
            if ilju not in moved and (
                cur.event_key in over_event or cur.domain in over_domain
                or cooldown_violation(history.get(ilju, ()), cur.event_key)
            )
        )
        for ilju in targets:
            chain = _find_chain(
                ilju, selections, raw_selections, candidate_map, history, moved,
                domain_cap=domain_cap, event_cap=effective_event_cap,
                budget=max_displacement_cost, policy=policy,
                recent30=recent30, last_seen=last_seen, today=today,
                depth=MAX_CHAIN_DEPTH if policy.global_swap else 1,
            )
            if chain is None:
                continue
            for k, cand in chain:
                prev = selections[k]
                selections[k] = cand
                moved.add(k)
                result.moves.append(Move(
                    ilju=k, source_event=prev.event_key, source_domain=prev.domain,
                    destination_event=cand.event_key, destination_domain=cand.domain,
                    displacement_cost=raw_selections[k].probability - cand.probability,
                    constraint_relief=1,
                ))
                result.codes[k] = (
                    COOLDOWN_ALTERNATIVE_SELECTED if k in result.violations
                    else "CAP_OR_CHAIN_MOVE"
                )
                if k != ilju and k not in result.violations:
                    result.displaced_by_chain += 1
            progress = True
            break

    events, domains = _counts(selections)
    result.selections = selections
    result.event_overflow = sum(
        max(0, n - effective_event_cap) for n in events.values()
    ) if event_cap is not None else 0
    result.domain_overflow = sum(max(0, n - domain_cap) for n in domains.values())
    result.cap_only_moves = sum(
        1 for m in result.moves if m.ilju not in result.violations
    )
    result.accepted_weaker_repeat = sum(
        1 for ilju in result.violations
        if repeat_severity(history.get(ilju, ()), selections[ilju].event_key)
        not in (SEVERITY_CLEAN,)
        and result.codes.get(ilju) == COOLDOWN_ALTERNATIVE_SELECTED
    )

    for ilju in result.violations:
        if result.codes.get(ilju) == COOLDOWN_ALTERNATIVE_SELECTED:
            continue
        result.unresolved_cards.append(
            _diagnose_unresolved(
                ilju, selections, raw_selections, candidate_map, history,
                events, domains, domain_cap=domain_cap,
                event_cap=effective_event_cap, budget=max_displacement_cost,
                policy=policy,
            )
        )
        result.codes[ilju] = result.unresolved_cards[-1].reason
    return result


def _diagnose_unresolved(
    ilju: str, selections, raw, candidate_map, history, events, domains,
    *, domain_cap: int, event_cap: int, budget: int | None, policy: SelectionPolicy,
) -> UnresolvedCard:
    """왜 못 옮겼는가 — 처방이 갈리는 순서로 사유를 하나 고른다."""
    cur = selections[ilju]
    cur_sev = repeat_severity(history.get(ilju, ()), cur.event_key)
    alts = [c for c in candidate_map.get(ilju, ()) if c.event_key != cur.event_key]
    base = raw[ilju].probability
    if not alts:
        return UnresolvedCard(
            ilju=ilju, reason=NO_ELIGIBLE_HEADLINE_EVENT,
            original_event_key=cur.event_key, original_domain=cur.domain,
            original_probability=cur.probability,
        )
    blocked: collections.Counter[str] = collections.Counter()
    budget_best: tuple[int, HeadlineCandidate] | None = None
    for alt in alts:
        cost = base - alt.probability
        if not _acceptable_severity(
            cur_sev, repeat_severity(history.get(ilju, ()), alt.event_key), policy
        ):
            blocked[ALL_CANDIDATES_COOLDOWN_BLOCKED] += 1
            continue
        if events.get(alt.event_key, 0) >= event_cap:
            blocked[ALL_CANDIDATES_EVENT_CAP_BLOCKED] += 1
            continue
        if alt.domain != cur.domain and domains.get(alt.domain, 0) >= domain_cap:
            blocked[ALL_CANDIDATES_DOMAIN_CAP_BLOCKED] += 1
            continue
        if budget is not None and cost > budget:
            blocked[LOSS_BUDGET_EXCEEDED] += 1
            if budget_best is None or cost < budget_best[0]:
                budget_best = (cost, alt)
            continue
    if budget_best is not None:
        cost, alt = budget_best
        return UnresolvedCard(
            ilju=ilju, reason=LOSS_BUDGET_EXCEEDED,
            original_event_key=cur.event_key, original_domain=cur.domain,
            original_probability=cur.probability,
            best_alternative_event_key=alt.event_key,
            best_alternative_domain=alt.domain, probability_gap=cost,
            required_uplift_to_fit=cost - (budget if budget is not None else cost),
        )
    reason = blocked.most_common(1)[0][0] if blocked else NO_ELIGIBLE_HEADLINE_EVENT
    return UnresolvedCard(
        ilju=ilju, reason=reason, original_event_key=cur.event_key,
        original_domain=cur.domain, original_probability=cur.probability,
    )

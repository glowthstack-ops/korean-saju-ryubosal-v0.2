"""OA-10a — `CANONICAL_BOOTSTRAP` 생성기.

C10 의 90일 상태를 "사용자가 실제로 본 기록"이 아니라 **최종 출시 후보 계약으로 미리
계산한 공식 콘텐츠 배치 상태**로 재정의한다.

    D-180 ~ D-91   warm-up 전용 (C10 자체를 안정 상태로 만든다)
    D-90  ~ D-1    C10 이 실제 lookback 으로 쓸 canonical history
    D              최초 공개 보드

과거를 흉내 내지 않는다 — **전 구간에 최종 계약을 일관되게 적용**한다. 그래서
"2026년 5월에는 서비스가 없었다"는 문제가 생기지 않는다. 5월 서비스를 재현하는 게
아니라 공개일 스케줄러를 미리 안정화하는 계산 구간이기 때문이다.

이 방식은 새로운 것이 아니다. C10 이 출시 기준을 통과한 측정이 이미
`warm-up 90일 → 측정 90일` 구조였다. 그 검증 방식을 배포 초기화 계약으로
공식화한 것뿐이며, 따라서 **생성 결과가 self-warmup 감사와 같아야 한다**
(다르면 구현 드리프트다).
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import date, timedelta

from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count
from saju_engines.daily_ilju_fortune import (
    EVENT_SELECTION_COMPAT_SALT,
    _band,
    _headline_candidates,
    _score_event,
    _select_slots,
    build_day_context,
    load_daily_dicts_for,
)
from saju_engines.daily_selection_contracts import (
    DISPLAY_SELECTION_POLICY_C10_V1,
    required_lookback_days,
)
from saju_engines.daily_selection_policy_shadow import (
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    GoodRepresentative,
    LongTermPolicy,
    SelectionPolicy,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

#: bootstrap 계약 버전. 사전·문장·정책이 바뀌면 이 값을 올리고 전 구간을 다시 만든다.
BOOTSTRAP_CONTRACT_VERSION = "daily-selection-bootstrap.v1"

#: warm-up 기간 — C10 자체를 안정 상태로 만드는 구간(집계에 쓰지 않는다).
BOOTSTRAP_WARMUP_DAYS = 90

#: 승인된 출시 후보 C10.
C10_POLICY = LongTermPolicy(
    unused_semantic_family=True, unused_event_key=True,
    coverage_floor=16, recovery_prefers_low_loss=False, band_protection=True,
)
_BOARD_POLICY = SelectionPolicy(
    global_swap=True, severity_tiers=True, recency_rotation=True
)
_DOMAIN_CAP = cap_count(60, 0.35)
_EVENT_CAP = 10
_BUDGET = 7
_BAND_NAMES = {4: "s5", 3: "s4", 2: "s3", 1: "s2"}


@dataclass(frozen=True)
class BootstrapPlan:
    """생성 범위와 계약 — 언제든 같은 입력으로 재생해 지문 일치를 확인한다."""

    anchor_date: date
    bootstrap_contract_version: str
    selection_policy_version: str
    warmup_days: int
    lookback_days: int

    @property
    def start_date(self) -> date:
        """생성 시작일 = anchor - (warmup + lookback)."""
        return self.anchor_date - timedelta(days=self.warmup_days + self.lookback_days)

    @property
    def end_date(self) -> date:
        """생성 종료일 = anchor - 1. anchor 당일부터는 실제 공개 보드다."""
        return self.anchor_date - timedelta(days=1)

    @property
    def canonical_start(self) -> date:
        """C10 이 실제 lookback 으로 쓸 구간의 시작 = anchor - lookback."""
        return self.anchor_date - timedelta(days=self.lookback_days)

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True)
class BootstrapRow:
    """canonical 배치 1건. `is_published=False` — 사용자에게 제공된 적이 없다."""

    fortune_date: date
    ilju: str
    raw_good_winner: str
    raw_good_probability: int
    raw_good_band: str
    display_good_representative: str
    display_good_probability: int
    display_good_band: str
    display_good_semantic_family: str
    support_event: str
    caution_event: str
    raw_headline: str
    final_headline: str
    final_headline_semantic_family: str
    good_selection_reason: str
    display_displacement_loss: int
    raw_supporting_groups: int
    display_supporting_groups: int
    #: warm-up 구간인가(집계 제외) 아니면 canonical lookback 구간인가.
    is_canonical_history: bool


def make_plan(
    anchor_date: date,
    *,
    bootstrap_contract_version: str = BOOTSTRAP_CONTRACT_VERSION,
    warmup_days: int = BOOTSTRAP_WARMUP_DAYS,
) -> BootstrapPlan:
    """생성 계획. lookback 은 이력 계약이 요구하는 길이를 그대로 쓴다."""
    return BootstrapPlan(
        anchor_date=anchor_date,
        bootstrap_contract_version=bootstrap_contract_version,
        selection_policy_version=DISPLAY_SELECTION_POLICY_C10_V1,
        warmup_days=warmup_days,
        lookback_days=LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    )


def generate_bootstrap(
    plan: BootstrapPlan, family_of: dict[str, str]
) -> list[BootstrapRow]:
    """계획 구간을 날짜순으로 결정론적으로 생성한다.

    Args:
        plan: 생성 범위와 계약.
        family_of: event_key → semantic_family (taxonomy). C10 의 정책 입력이다.

    Returns:
        날짜 오름차순 · 60갑자 순의 배치 행. warm-up 구간도 포함하되
        `is_canonical_history=False` 로 구분한다.
    """
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    rows: list[BootstrapRow] = []

    day = plan.start_date
    while day <= plan.end_date:
        dicts = load_daily_dicts_for(day)
        events = dicts.catalog["events"]
        ctx = build_day_context(day)

        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        slots: dict[str, tuple] = {}
        reps: dict[str, GoodRepresentative] = {}

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
            scored = [_score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            rep = select_good_representative(
                goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=headline_history[ilju],
            )
            reps[ilju] = rep
            good, caution, support = _select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = _headline_candidates(good, support, caution, _band(good, caution))
            slots[ilju] = (good, caution, support, {s.event_key: s for s in scored})
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            good_history[ilju].append(rep.display_good_representative)

        result = select_board(
            raw, cmap, headline_history, domain_cap=_DOMAIN_CAP,
            event_cap=_EVENT_CAP, max_displacement_cost=_BUDGET,
            policy=_BOARD_POLICY, today=day.toordinal(),
        )
        is_canonical = day >= plan.canonical_start
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            good, caution, support, scored_by = slots[ilju]
            rep = reps[ilju]
            final = result.selections[ilju]
            rw = scored_by[rep.raw_good_winner]
            rows.append(BootstrapRow(
                fortune_date=day, ilju=ilju,
                raw_good_winner=rep.raw_good_winner,
                raw_good_probability=rep.raw_good_probability,
                raw_good_band=_BAND_NAMES[strength_band(rep.raw_good_probability)],
                display_good_representative=rep.display_good_representative,
                display_good_probability=rep.display_good_probability,
                display_good_band=_BAND_NAMES[
                    strength_band(rep.display_good_probability)
                ],
                display_good_semantic_family=family_of.get(
                    rep.display_good_representative, ""
                ),
                support_event=support.event_key,
                caution_event=caution.event_key,
                raw_headline=cmap[ilju][0].event_key,
                final_headline=final.event_key,
                final_headline_semantic_family=family_of.get(final.event_key, ""),
                good_selection_reason=rep.good_selection_reason,
                display_displacement_loss=rep.display_displacement_loss,
                raw_supporting_groups=rw.supporting_groups,
                display_supporting_groups=good.supporting_groups,
                is_canonical_history=is_canonical,
            ))
        for ilju, sel in result.selections.items():
            headline_history[ilju].append(sel.event_key)
        day += timedelta(days=1)
    return rows


def canonical_history(rows: list[BootstrapRow]) -> dict[str, list[str]]:
    """C10 최초 공개일이 lookback 으로 읽을 이력 — canonical 구간만.

    warm-up 구간은 C10 을 안정 상태로 만드는 데만 쓰이고 이력으로 넘기지 않는다.
    넘기면 lookback 이 계약(90일)보다 길어진다.
    """
    out: dict[str, list[str]] = collections.defaultdict(list)
    for r in sorted(rows, key=lambda x: (x.fortune_date, x.ilju)):
        if r.is_canonical_history:
            out[r.ilju].append(r.final_headline)
    return dict(out)


def verify_lookback_length(plan: BootstrapPlan, rows: list[BootstrapRow]) -> None:
    """canonical 구간이 계약 길이와 정확히 같은지 확인한다.

    Raises:
        ValueError: 길이가 다르면(계약 정정이 반영되지 않은 것).
    """
    expected = required_lookback_days("daily-selection-history.v1")
    if plan.lookback_days != expected:
        raise ValueError(f"lookback {plan.lookback_days} != 계약 {expected}")
    for ilju, series in canonical_history(rows).items():
        if len(series) != expected:
            raise ValueError(f"{ilju}: canonical 이력 {len(series)}일 != {expected}")

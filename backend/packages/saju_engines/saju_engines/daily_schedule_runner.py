"""날짜순 daily schedule 공용 runner — 계약을 한 곳에서 고정한다.

OA-10b(현행 C10 기준선)와 OA-11d(정책 비교)가 같은 함수를 쓰게 하려는 모듈이다.
각 harness 가 원점·cap·예열을 다시 조립하면 조용히 표류한다 — 실제로 OA-11d 가
그렇게 어긋났다(비율 0.30 을 개수 자리에 넘김, anchor 마다 움직이는 원점,
의도/실현 이력 혼동).

    advance_daily_schedule()      하루 전이 — 순수 함수. 입력 state 를 바꾸지 않는다.
    build_daily_schedule()        날짜순 반복만 담당.
    build_rolling_audit_schedule() 감사 계약을 wrapper 가 고정. 숫자를 받지 않는다.

이번 단계는 **S0(현행 C10) 전용**이다. S1/S2 를 같이 배선하면 parity 실패가 runner
문제인지 정책 분기 문제인지 구분할 수 없다.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from saju_engines.daily_board_constraints import HeadlineCandidate
from saju_engines.daily_cooldown_shadow import COOLDOWN_WINDOW
from saju_engines.daily_selection_contracts import (
    DAILY_ROLLING_AUDIT_ORIGIN,
    DAILY_ROLLING_AUDIT_WARMUP_DAYS,
)
from saju_engines.daily_selection_policy_shadow import (
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    LongTermPolicy,
    ProjectionStatus,
    SelectionPolicy,
    Top1FamilyProjection,
    select_board,
    select_good_representative,
)

#: state fingerprint 직렬화 규약. 스키마가 바뀌면 결과가 같아도 기존 artifact 와
#: 직접 비교하지 않고 별도 버전으로 다룬다.
STATE_FINGERPRINT_SCHEMA = "daily-schedule-state-fingerprint.v1"


class RepeatHistorySource(StrEnum):
    """정책이 반복 판정에 **읽는** 이력.

    현행 C10 은 의도한 대표를 기록한다. 실현 대표·최종 헤드라인 family 로 바꾸는
    것은 별도 감사(H0/H1/H2) 축이며, 여기서 소스만 교체할 수 있게 한다.
    """

    INTENDED_GOOD = "INTENDED_GOOD"
    REALIZED_GOOD = "REALIZED_GOOD"
    FINAL_HEADLINE_FAMILY = "FINAL_HEADLINE_FAMILY"


@dataclass(frozen=True)
class DailyBoardContract:
    """보드 제약. cap 은 **비율이 아니라 개수**다."""

    version: str
    board_size: int
    domain_cap_count: int
    event_cap_count: int
    displacement_loss_budget: int


@dataclass(frozen=True)
class DailyHistoryContract:
    """이력 계약 — 창 길이와 정책이 읽는 소스."""

    version: str
    lookback_days: int
    repeat_history_source: RepeatHistorySource


@dataclass(frozen=True)
class DailyRollingAuditContract:
    """장기 rolling **감사** 시간 계약. 베타 풀 bootstrap 과 다른 계약이다."""

    version: str
    origin: date
    warmup_days: int


DAILY_BOARD_CONTRACT_V1 = DailyBoardContract(
    version="daily-board.v1",
    board_size=60,
    domain_cap_count=21,          # cap_count(60, 0.35)
    event_cap_count=10,
    displacement_loss_budget=7,
)
DAILY_HISTORY_CONTRACT_V1 = DailyHistoryContract(
    version="daily-selection-history.v1",
    lookback_days=LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    repeat_history_source=RepeatHistorySource.INTENDED_GOOD,
)
DAILY_ROLLING_AUDIT_CONTRACT_V1 = DailyRollingAuditContract(
    version="daily-rolling-audit.v1",
    origin=DAILY_ROLLING_AUDIT_ORIGIN,
    warmup_days=DAILY_ROLLING_AUDIT_WARMUP_DAYS,
)

class DailyScheduleContractError(RuntimeError):
    """계약 위반 — 디버깅 가정이 아니라 정확성을 지키는 런타임 검사다."""


class DailyScheduleStateLeakError(RuntimeError):
    """같은 날짜 안에서 일주끼리 상태가 샜다."""


def validate_history_contract(contract: DailyHistoryContract) -> None:
    """이력 창이 두 소비자 모두를 만족하는지 확인한다.

    창 길이를 쿨다운 하나로만 설명하면 안 된다. `final_headline_family_history` 는
    90일 family coverage 계산에 창 **전체**가 필요하므로, coverage 창이 나중에
    120일로 바뀌는데 이력은 90일로 남는 표류도 함께 막는다.

    Raises:
        DailyScheduleContractError: 창이 어느 한쪽 요구를 못 맞출 때.
    """
    if contract.lookback_days < COOLDOWN_WINDOW:
        raise DailyScheduleContractError(
            "이력 창이 쿨다운 창보다 짧다: "
            f"lookback={contract.lookback_days}, cooldown={COOLDOWN_WINDOW}"
        )
    if contract.lookback_days != LONGITUDINAL_HISTORY_LOOKBACK_DAYS:
        raise DailyScheduleContractError(
            "이력 창과 family coverage 창이 다르다: "
            f"lookback={contract.lookback_days}, "
            f"coverage={LONGITUDINAL_HISTORY_LOOKBACK_DAYS}"
        )


validate_history_contract(DAILY_HISTORY_CONTRACT_V1)


def _canon(value: Any) -> Any:
    """직렬화 정규화 — 한자 문자열은 NFC, None 은 명시적으로 남긴다."""
    if value is None:
        return None
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, Mapping):
        return {_canon(k): _canon(v) for k, v in value.items()}
    if isinstance(value, date):
        return value.isoformat()
    return value


def _fingerprint(payload: Any) -> str:
    """sha256 — 배열 순서는 유지하고 key 만 정렬한다."""
    return hashlib.sha256(
        json.dumps(_canon(payload), ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DailyScheduleState:
    """날짜순 상태 — 정책 입력과 관측 이력을 분리해 보존한다.

    세 이력을 모두 들고 있되 정책이 읽는 것은 `history_contract` 가 정한 하나다.
    직접 필드에 접근하지 말고 `repeat_history_for()` 를 쓴다 — 정책 코드가 필드를
    직접 읽으면 H0/H1/H2 감사에서 분기가 다시 흩어진다.
    """

    intended_good_history: Mapping[str, tuple[str, ...]]
    realized_good_history: Mapping[str, tuple[str, ...]]
    final_headline_family_history: Mapping[str, tuple[str, ...]]
    #: 최종 헤드라인 event_key 이력 — `select_good_representative` 의 헤드라인 축.
    final_headline_history: Mapping[str, tuple[str, ...]]

    def repeat_history_for(
        self, ilju: str, *, source: RepeatHistorySource
    ) -> tuple[str, ...]:
        """정책이 반복 판정에 쓸 이력."""
        table = {
            RepeatHistorySource.INTENDED_GOOD: self.intended_good_history,
            RepeatHistorySource.REALIZED_GOOD: self.realized_good_history,
            RepeatHistorySource.FINAL_HEADLINE_FAMILY:
                self.final_headline_family_history,
        }[source]
        return table.get(ilju, ())

    def fingerprint(self) -> str:
        return _fingerprint({
            "schema": STATE_FINGERPRINT_SCHEMA,
            "intended": {k: list(v) for k, v in self.intended_good_history.items()},
            "realized": {k: list(v) for k, v in self.realized_good_history.items()},
            "final_family": {
                k: list(v) for k, v in self.final_headline_family_history.items()
            },
            "final_headline": {
                k: list(v) for k, v in self.final_headline_history.items()
            },
        })


def empty_state() -> DailyScheduleState:
    """호출마다 새 state — mutable 기본값을 공유하지 않는다."""
    return DailyScheduleState({}, {}, {}, {})


@dataclass(frozen=True)
class DailyScheduleStep:
    """하루 결과."""

    fortune_date: date
    state_before_fingerprint: str
    rows: tuple[dict[str, Any], ...]
    board_fingerprint: str
    state_after_fingerprint: str
    eviction_summary: dict[str, Any]


@dataclass(frozen=True)
class CardCandidateBundle:
    """한 카드의 완성된 후보 자료.

    실제 선택과 projection 계산이 **같은 자료**를 쓴다. projection 을 위해 후보
    생성부터 다시 하면 두 경로가 향후 조건·사전·정렬 변경에서 갈라질 수 있다.
    """

    good_event_key: str
    slots: tuple[Any, ...]              # (good, caution, support)
    headline_candidates: tuple[Any, ...]

    @property
    def card_top1_event_key(self) -> str:
        return str(self.headline_candidates[0].event_key)


#: `UNAVAILABLE` 세부 원인. 정책은 구분하지 않고 모두 우회하지 않는다.
UNAVAILABLE_RAW_TOP_CARD_NOT_AVAILABLE = "RAW_TOP_CARD_NOT_AVAILABLE"
UNAVAILABLE_NO_HEADLINE_CANDIDATE = "NO_HEADLINE_CANDIDATE"
UNAVAILABLE_EMPTY_FAMILY = "EMPTY_FAMILY"


def unavailable_reason(
    *, raw_top_event_key: str, card_candidates: CardCandidateBundle,
    family_of: Mapping[str, str],
) -> str | None:
    """`UNAVAILABLE` 이라면 그 원인 — 측정 전용이다."""
    if card_candidates.good_event_key != raw_top_event_key:
        return UNAVAILABLE_RAW_TOP_CARD_NOT_AVAILABLE
    if not card_candidates.headline_candidates:
        return UNAVAILABLE_NO_HEADLINE_CANDIDATE
    top1 = card_candidates.headline_candidates[0]
    if not family_of.get(top1.event_key, ""):
        return UNAVAILABLE_EMPTY_FAMILY
    return None


def derive_top1_family_projection(
    *,
    raw_top_event_key: str,
    card_candidates: CardCandidateBundle,
    family_of: Mapping[str, str],
) -> Top1FamilyProjection:
    """원시 1위 카드가 **board 적용 전에** 낼 headline family.

    board cap·rebalance·다른 일주 결과·당일 최종 headline·history 갱신·사후
    realized family 는 들어가지 않는다. 부작용도 없다 — 완성된 bundle 만 읽는다.

    Args:
        raw_top_event_key: 원시 good 1위 사건.
        card_candidates: 그 사건을 good 으로 둔 카드의 완성된 후보 자료.
        family_of: event_key → semantic family.

    Returns:
        결박된 projection. 예외나 빈 값을 억지로 PROJECTED 로 만들지 않는다.
    """
    if card_candidates.good_event_key != raw_top_event_key:
        return Top1FamilyProjection(
            event_key=raw_top_event_key, family="",
            status=ProjectionStatus.UNAVAILABLE,
        )
    if not card_candidates.headline_candidates:
        return Top1FamilyProjection(
            event_key=raw_top_event_key, family="",
            status=ProjectionStatus.UNAVAILABLE,
        )
    # 아래 세 원인은 정책상 모두 fail-closed 로 같지만, 측정에서는 구분할 가치가
    # 있다 — funnel 에서 병목이 helper 문제인지 카드 구성 문제인지 갈린다.
    top1 = card_candidates.headline_candidates[0]
    family = family_of.get(top1.event_key, "")
    if not family:
        return Top1FamilyProjection(
            event_key=raw_top_event_key, family="",
            status=ProjectionStatus.UNAVAILABLE,
        )
    # 동률 top-1 이 서로 다른 family 면 단일 투영으로 확정할 수 없다.
    tied = [
        c for c in card_candidates.headline_candidates
        if c.probability == top1.probability
    ]
    if len({family_of.get(c.event_key, "") for c in tied}) > 1:
        return Top1FamilyProjection(
            event_key=raw_top_event_key, family=family,
            status=ProjectionStatus.AMBIGUOUS,
        )
    return Top1FamilyProjection(
        event_key=raw_top_event_key, family=family,
        status=ProjectionStatus.PROJECTED,
    )


def _append_window(
    hist: Mapping[str, tuple[str, ...]], additions: Mapping[str, str], keep: int
) -> tuple[dict[str, tuple[str, ...]], dict[str, str | None]]:
    """당일 결과를 붙이고 창 밖으로 밀린 값을 함께 돌려준다.

    순서 계약: D일 선택은 D-90~D-1 을 읽고 → D일 결과 append → D-90 제거 →
    다음 날 state 는 D-89~D 다.

    Returns:
        (갱신된 이력, 일주 → 밀려난 값 또는 None).
    """
    out: dict[str, tuple[str, ...]] = dict(hist)
    evicted: dict[str, str | None] = {}
    for ilju, value in additions.items():
        merged = (*out.get(ilju, ()), value)
        if len(merged) > keep:
            # 제거가 없는 초기 구간은 None 을 명시한다 — 필드 누락으로 표현하면
            # fingerprint 가 불안정해진다.
            evicted[ilju] = merged[0]
            merged = merged[-keep:]
        else:
            evicted[ilju] = None
        out[ilju] = merged
    return out, evicted


def advance_daily_schedule(
    *,
    fortune_date: date,
    state: DailyScheduleState,
    policy: LongTermPolicy,
    board_policy: SelectionPolicy,
    board_contract: DailyBoardContract,
    history_contract: DailyHistoryContract,
    family_of: Mapping[str, str],
    iljus: Sequence[str],
    compute_projection_trace: bool = False,
) -> tuple[DailyScheduleStep, DailyScheduleState]:
    """하루 전이 — 입력 state 를 바꾸지 않고 새 state 를 돌려준다.

    같은 날짜의 선택 중에는 next_state 를 읽지 않는다. 60일주 계산이 모두 끝나고
    board 가 확정된 뒤에 세 이력을 **한꺼번에** 갱신한다 — 앞쪽 일주 결과가 뒤쪽
    일주 선택에 들어가는 당일 누수를 구조적으로 막는다.

    Args:
        fortune_date: 대상 날짜.
        state: 전날까지의 상태(불변).
        policy: good 대표 선택 정책(S0 = C10).
        board_policy: board 재배정 정책.
        board_contract: 보드 제약(개수).
        history_contract: 이력 계약.
        family_of: event_key → semantic family.
        iljus: 60갑자 공식 순서.

    Returns:
        (하루 결과, 다음 state).
    """
    import saju_engines.daily_ilju_fortune as M
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    validate_history_contract(history_contract)
    before_fp = state.fingerprint()
    events = M.load_daily_dicts().catalog["events"]
    ctx = M.build_day_context(fortune_date)
    look = history_contract.lookback_days
    source = history_contract.repeat_history_source

    raw: dict[str, HeadlineCandidate] = {}
    cmap: dict[str, list[HeadlineCandidate]] = {}
    pending: dict[str, dict[str, Any]] = {}
    read_fps: set[str] = set()

    for idx, ilju in enumerate(iljus):
        stem, branch = ganzi_from_index(idx)
        seed = f"{fortune_date.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
        scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
        goods = [
            (s.event_key, s.probability) for s in scored
            if s.valence == "good"
            and "good" in (events[s.event_key].get("headline_slots")
                           or events[s.event_key]["slots"])
        ]
        repeat_hist = state.repeat_history_for(ilju, source=source)
        headline_hist = state.final_headline_history.get(ilju, ())
        # 60일주가 모두 같은 state 를 읽었는지 확인할 수 있게 지문을 모은다.
        read_fps.add(before_fp)

        # projection 은 **측정 모드에서만** 계산한다. production 경로에서는 반사실
        # 카드 구성이 아예 일어나지 않아 C10 의 비용·결과가 완전히 불변이다.
        raw_top_key = sorted(goods, key=lambda x: (-x[1], x[0]))[0][0]
        projection = None
        raw_top_bundle: tuple[Any, Any, Any, Any] | None = None
        if compute_projection_trace:
            rg, rc, rs = M._select_slots(scored, seed, good_override=raw_top_key)
            rcands = M._headline_candidates(rg, rs, rc, M._band(rg, rc))
            raw_top_bundle = (rg, rc, rs, rcands)
            bundle = CardCandidateBundle(
                good_event_key=rg.event_key, slots=(rg, rc, rs),
                headline_candidates=tuple(rcands),
            )
            projection = derive_top1_family_projection(
                raw_top_event_key=raw_top_key, card_candidates=bundle,
                family_of=family_of,
            )
            projection_reason = unavailable_reason(
                raw_top_event_key=raw_top_key, card_candidates=bundle,
                family_of=family_of,
            )

        rep = select_good_representative(
            list(goods), list(repeat_hist),
            board_contract.displacement_loss_budget,
            policy=policy, family_of=family_of,
            headline_history=list(headline_hist),
            top1_projection=projection,
        )
        if raw_top_bundle is not None and (
            rep.display_good_representative == raw_top_key
        ):
            # 실제 대표가 원시 1위다 — 이미 만든 bundle 을 재사용한다(추가 호출 0).
            g, c, s, cands = raw_top_bundle
        else:
            g, c, s = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
        cmap[ilju] = [
            HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
        ]
        raw[ilju] = cmap[ilju][0]
        pending[ilju] = {
            "fortune_date": fortune_date.isoformat(),
            "ilju": ilju,
            "raw_good_winner": rep.raw_good_winner,
            "intended_good_representative": rep.display_good_representative,
            "realized_good_event": g.event_key,
            "support_event": s.event_key,
            "caution_event": c.event_key,
            "raw_headline": cands[0].event_key,
            "selection_reason_codes": [rep.good_selection_reason],
            # legacy 필드명 유지 — 의미는 의도 대표 기준 손실이다.
            "display_displacement_loss": rep.display_displacement_loss,
        }
        if compute_projection_trace and projection is not None:
            # 측정 전용 trace — selection reason code 와 섞지 않는다.
            reused = rep.display_good_representative == raw_top_key
            pending[ilju]["oa11d_trace"] = {
                "raw_top_event_key": raw_top_key,
                "projected_top1_event_key": projection.event_key,
                "projected_top1_family": projection.family,
                "projection_status": projection.status.value,
                "projection_source": (
                    "REUSED_ACTUAL_CARD" if reused
                    else "COUNTERFACTUAL_RAW_TOP_CARD"
                ),
                "counterfactual_select_slots_calls": 0 if reused else 1,
                "unavailable_reason": (
                    projection_reason
                    if projection.status is ProjectionStatus.UNAVAILABLE else None
                ),
            }

    if len(read_fps) != 1:
        raise DailyScheduleStateLeakError(
            "60일주가 모두 같은 board 이전 상태를 읽어야 한다: "
            f"fortune_date={fortune_date}, fingerprints={sorted(read_fps)}"
        )

    result = select_board(
        raw, cmap,
        {k: list(v) for k, v in state.final_headline_history.items()},
        domain_cap=board_contract.domain_cap_count,
        event_cap=board_contract.event_cap_count,
        max_displacement_cost=board_contract.displacement_loss_budget,
        policy=board_policy, today=fortune_date.toordinal(),
    )

    rows: list[dict[str, Any]] = []
    add_intended: dict[str, str] = {}
    add_realized: dict[str, str] = {}
    add_family: dict[str, str] = {}
    add_headline: dict[str, str] = {}
    for ilju, sel in result.selections.items():
        row = dict(pending[ilju])
        row["final_headline"] = sel.event_key
        row["final_headline_family"] = family_of.get(sel.event_key, sel.event_key)
        rows.append(row)
        add_intended[ilju] = row["intended_good_representative"]
        add_realized[ilju] = row["realized_good_event"]
        add_family[ilju] = row["final_headline_family"]
        add_headline[ilju] = sel.event_key

    intended, ev_intended = _append_window(
        state.intended_good_history, add_intended, look
    )
    realized, ev_realized = _append_window(
        state.realized_good_history, add_realized, look
    )
    family, ev_family = _append_window(
        state.final_headline_family_history, add_family, look
    )
    headline, _ev_headline = _append_window(
        state.final_headline_history, add_headline, look
    )
    next_state = replace(
        state,
        intended_good_history=intended,
        realized_good_history=realized,
        final_headline_family_history=family,
        final_headline_history=headline,
    )
    eviction = {
        "intended_evicted_by_ilju": ev_intended,
        "realized_evicted_by_ilju": ev_realized,
        "final_family_evicted_by_ilju": ev_family,
    }
    step = DailyScheduleStep(
        fortune_date=fortune_date,
        state_before_fingerprint=before_fp,
        rows=tuple(rows),
        board_fingerprint=_fingerprint(
            [[i, result.selections[i].event_key] for i in sorted(result.selections)]
        ),
        state_after_fingerprint=next_state.fingerprint(),
        eviction_summary=eviction,
    )
    return step, next_state


def build_daily_schedule(
    *,
    start_date: date,
    days: int,
    policy: LongTermPolicy,
    board_policy: SelectionPolicy,
    board_contract: DailyBoardContract,
    history_contract: DailyHistoryContract,
    family_of: Mapping[str, str],
    initial_state_factory: Callable[[], DailyScheduleState] = empty_state,
    compute_projection_trace: bool = False,
) -> tuple[list[DailyScheduleStep], DailyScheduleState]:
    """날짜순 반복만 담당한다.

    `initial_state_factory` 는 호출마다 새 state 를 만든다 — mutable 초기 state 를
    공유하면 재실행 간 상태가 섞인다.
    """
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    iljus = [
        f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}"
        for i in range(board_contract.board_size)
    ]
    state = initial_state_factory()
    steps: list[DailyScheduleStep] = []
    for offset in range(days):
        step, state = advance_daily_schedule(
            fortune_date=start_date + timedelta(days=offset),
            state=state, policy=policy, board_policy=board_policy,
            board_contract=board_contract, history_contract=history_contract,
            family_of=family_of, iljus=iljus,
            compute_projection_trace=compute_projection_trace,
        )
        steps.append(step)
    return steps, state


def build_rolling_audit_schedule(
    *,
    days: int,
    policy: LongTermPolicy,
    board_policy: SelectionPolicy,
    family_of: Mapping[str, str],
    audit_contract: DailyRollingAuditContract = DAILY_ROLLING_AUDIT_CONTRACT_V1,
    compute_projection_trace: bool = False,
) -> tuple[list[DailyScheduleStep], DailyScheduleState]:
    """감사 계약을 고정한 진입점 — 호출부가 원점·cap·예열을 조립하지 않는다."""
    return build_daily_schedule(
        start_date=audit_contract.origin,
        days=days,
        policy=policy,
        board_policy=board_policy,
        board_contract=DAILY_BOARD_CONTRACT_V1,
        history_contract=DAILY_HISTORY_CONTRACT_V1,
        family_of=family_of,
        compute_projection_trace=compute_projection_trace,
    )

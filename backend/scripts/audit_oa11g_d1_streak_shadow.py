#!/usr/bin/env python3
"""OA-11g — BOUNDED_D1_STREAK_PRESERVATION_SHADOW (측정 전용, 정책 미채택).

OA-11f-P 가 2026-04-02 丙辰 퇴행의 인과를 확정했다.

    2026-02-12 개입  (enabling)  → 03-14 marginal 후보 자격 발생
    2026-03-14 개입  (proximate) → 원시 1위 대신 다른 사건 commit
                                 → 03-15 연속 반복 severity 3→0
                                 → C10 자체 반복 회피 미발동
                                 → love_deepening replenishment 소멸

즉 보조 다양성 selector 는 C10 이 **손실 0 으로** 수행했을 자체 다양화 기회를
소비한다. 그 손해는 D 시점 로컬 state 로 판정할 수 없다 — 필요한 사실은 "D+1 원시
1위가 D 와 같은가" 이고, 이것은 D+1 채점 결과다.

따라서 이것은 R6 의 작은 가드가 **아니다.** 오늘의 결정이 내일의 채점에 의존하므로
인과·비용·실행 계약이 다른 별도 sequencing 정책이며, 그렇게 분리해 측정한다.

기반 selector 는 **R6 로 고정**한다. R7 에 붙이면 OA-11f-Q 의 손실 여유 없음
유보가 되살아나므로, R7 은 비교군으로만 남기고 정책 기반으로 쓰지 않는다.

    base_selector                 FIRST_SAFE_POSITIVE_MARGINAL_CANDIDATE_R6
    effective_display_loss_limit  6
    global_hard_loss_budget       7
    LOOKAHEAD_SOURCE              RAW_SCORER_ONLY
    LOOKAHEAD_HORIZON             EXACTLY_ONE_DAY

D+1 조회는 실행 중 상태와 분리된 **immutable oracle** 이다. 평가 시작 전에 전
구간을 불변 테이블로 만들고 런타임은 read-only lookup 만 한다 — 조회 때문에
candidate cache 나 RNG 가 움직일 여지를 없앤다.

    raw_winner(D, ilju) = f(D, ilju, frozen scoring configuration)

조회 실패는 production 방향으로 fail-closed 한다: 개입을 포기하고 C10 선택을
유지한다. 단 정상 측정의 수용 조건은 `D1_LOOKAHEAD_UNAVAILABLE = 0` 이다 — 조회
실패로 fallback 이 늘어 게이트가 통과하는 것을 효과로 인정하지 않는다.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_oa11f_b_online_replay as B  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    build_rolling_audit_aggregates,
    contract_mode,
    derive_diagnostic_contract,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_BOARD_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

POLICY_ID = "oa11g-d1-raw-winner-streak-preservation-shadow.v1"
#: oracle 은 raw scorer 만 쓴다 — selector 구현 버전과 분리한다. selector 코드가
#: 바뀌어도 raw winner 의 의미가 같으면 oracle 지문이 흔들려서는 안 된다.
RAW_SCORER_CONTRACT_VERSION = "daily-raw-good-winner.v1"
TIE_BREAK_CONTRACT_VERSION = "desc-probability-then-event-key.v1"
BASE_SELECTOR = "FIRST_SAFE_POSITIVE_MARGINAL_CANDIDATE_R6"
#: R6 의 표시 손실 실효 상한. 전역 하드 예산(7p)을 바꾸는 것이 아니다.
EFFECTIVE_DISPLAY_LOSS_LIMIT = 6
#: 5-anchor 측정 종료일(OA-11f 계열과 같은 구간).
FIVE_ANCHOR_LAST = dt.date(2027, 10, 9)
#: canonical 730-anchor 종료일. origin(2025-04-06) + warmup 180 + window 90 =
#: 첫 anchor 2026-01-01, 여기까지 1,000일 → anchor 730.
CANONICAL_LAST = dt.date(2027, 12, 31)
EVALUATION_LAST = FIVE_ANCHOR_LAST
#: oracle 생성 범위 — 평가 첫날의 D+1 부터 마지막 날의 D+1 까지.
ORACLE_FIRST = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin + dt.timedelta(days=1)
ORACLE_LAST = EVALUATION_LAST + dt.timedelta(days=1)
MODES = ("S0", "R6", "R6G")
_QUALIFY = 15
#: 판 계약상 일주 수. `len(B._ILJUS)` 에서 유도하면 목록이 줄어도 기대값이 같이
#: 줄어 카디널리티 검사가 결함을 못 잡는다 — 상수로 고정한다.
ILJU_COUNT = 60

#: 골든 fixture — 인과 사슬을 최종 coverage 가 아니라 단계별로 검증한다.
FIXTURE_ILJU = "丙辰"
FIXTURE_BLOCK_DATE = "2026-03-14"
FIXTURE_EFFECT_DATE = "2026-03-15"
FIXTURE_ANCHOR = "2026-04-02"

#: 가드 판정 사유 코드 — 하나로 뭉치면 "왜 개입했는가"를 잃는다.
D1_STREAK_PRESERVED = "D1_RAW_WINNER_STREAK_PRESERVED"
D1_WINNER_DIFFERENT = "D1_RAW_WINNER_DIFFERENT"
D1_NOT_ELIGIBLE = "D1_NOT_ELIGIBLE"
D1_UNAVAILABLE = "D1_LOOKAHEAD_UNAVAILABLE"
REASON_CODES = (
    D1_STREAK_PRESERVED, D1_WINNER_DIFFERENT, D1_NOT_ELIGIBLE, D1_UNAVAILABLE,
)


@dataclass(frozen=True)
class D1LookaheadContract:
    """1일 선행 조회의 정보 범위 계약 — 넓히면 미래 정책 시뮬레이션이 된다."""

    policy_id: str = POLICY_ID
    base_selector: str = BASE_SELECTOR
    effective_display_loss_limit: int = EFFECTIVE_DISPLAY_LOSS_LIMIT
    global_hard_loss_budget: int = DAILY_BOARD_CONTRACT_V1.displacement_loss_budget
    lookahead_source: str = "RAW_SCORER_ONLY"
    lookahead_horizon_days: int = 1
    compares: str = "event_key"
    runtime_behavior: str = "READ_ONLY_LOOKUP"
    unavailable_action: str = "FAIL_CLOSED_TO_C10"
    reads_history: bool = False
    reads_c10_representative: bool = False
    reads_repeat_severity: bool = False
    reads_deficit_state: bool = False
    reads_marginal_selector: bool = False
    reads_board: bool = False
    reads_realized_headline: bool = False


D1_CONTRACT = D1LookaheadContract()


@dataclass(frozen=True)
class RawWinnerProjection:
    """D+1 원시 good 1위 투영 — 실행 상태와 무관한 순수 채점 결과."""

    event_key: str | None
    raw_score: int | None
    tie_break_value: str | None
    scorer_version: str
    input_fingerprint: str


@dataclass(frozen=True)
class RawWinnerOracle:
    """불변 (날짜, 일주) → 원시 1위 테이블. 런타임은 읽기만 한다.

    history·selector·board 를 담지 않으므로 replay 시작일·종료일이나 이전 선택이
    조회 결과를 바꿀 수 없다 — 경계 불변식의 근거다.
    """

    config: dict[str, str]
    first_day: dt.date
    last_day: dt.date
    table: dict[tuple[str, str], RawWinnerProjection]
    #: 물리 실행 단위 = PER_DATE_ILJU (batch 최적화 없음). batch 로 바뀌면 호출 수와
    #: 평가 pair 수가 갈라지므로 둘을 따로 센다.
    physical_execution_unit: str
    physical_scorer_invocations: int
    scored_date_ilju_pairs: int
    cardinality: dict[str, Any]
    candidate_accounting: dict[str, Any]
    content_fingerprint: str
    build_seconds: float

    def lookup(self, day: dt.date, ilju: str) -> RawWinnerProjection | None:
        """읽기 전용 조회. 범위를 벗어나면 `None`(→ fail-closed)."""
        return self.table.get((day.isoformat(), ilju))


def event_catalog_fingerprint(events: dict[str, Any]) -> str:
    """사건 카탈로그 지문 — 키뿐 아니라 채점 입력 전체를 덮는다."""
    payload = json.dumps(events, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def selection_salt_fingerprint() -> str:
    """선택 salt 지문."""
    return hashlib.sha256(
        M.EVENT_SELECTION_COMPAT_SALT.encode("utf-8")
    ).hexdigest()


def raw_winner_oracle_config_fp(events: dict[str, Any]) -> dict[str, str]:
    """oracle 설정 지문 — 네 구성요소를 분리해 남기고 합성 지문을 만든다."""
    parts = {
        "raw_scorer_contract_version": RAW_SCORER_CONTRACT_VERSION,
        "tie_break_contract_version": TIE_BREAK_CONTRACT_VERSION,
        "event_catalog_fingerprint": event_catalog_fingerprint(events),
        "selection_salt_fingerprint": selection_salt_fingerprint(),
    }
    parts["raw_winner_oracle_config_fp"] = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return parts


def _raw_good_winner(
    day: dt.date, ilju_index: int, events, oracle_config_fp: str
) -> RawWinnerProjection:
    """(날짜, 일주) 의 원시 good 1위. history 를 인자로도 받지 않는다."""
    stem, branch = ganzi_from_index(ilju_index)
    ilju = f"{stem.value}{branch.value}"
    ctx = M.build_day_context(day)
    scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
    goods = [
        (s.event_key, s.probability) for s in scored
        if s.valence == "good"
        and "good" in (events[s.event_key].get("headline_slots")
                       or events[s.event_key]["slots"])
    ]
    # 원시 후보 입력 자체의 지문 — 무엇을 보고 1위를 뽑았는지 재현 가능하게 남긴다.
    raw_input_fp = hashlib.sha256(
        "|".join(f"{k}:{v}" for k, v in sorted(goods)).encode("utf-8")
    ).hexdigest()[:16]
    fp = hashlib.sha256(
        f"{day.isoformat()}|{ilju}|{oracle_config_fp}|{raw_input_fp}".encode()
    ).hexdigest()[:32]
    if not goods:
        return RawWinnerProjection(
            None, None, None, RAW_SCORER_CONTRACT_VERSION, fp
        )
    key, score = sorted(goods, key=lambda x: (-x[1], x[0]))[0]
    return RawWinnerProjection(
        key, score, f"{-score}|{key}", RAW_SCORER_CONTRACT_VERSION, fp
    )


def build_raw_winner_oracle(
    events, *, first: dt.date = ORACLE_FIRST, last: dt.date = ORACLE_LAST
) -> RawWinnerOracle:
    """평가 전에 전 구간 oracle 을 불변 테이블로 생성한다(사전 계산)."""
    t0 = time.perf_counter()
    config = raw_winner_oracle_config_fp(events)
    cfp = config["raw_winner_oracle_config_fp"]
    if len(B._ILJUS) != ILJU_COUNT:
        raise RuntimeError(
            f"ILJU_SET_INCOMPLETE: {len(B._ILJUS)} != {ILJU_COUNT}"
        )
    expected_dates = (last - first).days + 1
    expected_keys = expected_dates * ILJU_COUNT
    table: dict[tuple[str, str], RawWinnerProjection] = {}
    invocations = 0
    duplicates = 0
    catalog_size = len(events)
    scored_counts: list[int] = []
    per_date: collections.Counter[str] = collections.Counter()
    dates: list[str] = []
    day = first
    while day <= last:
        iso = day.isoformat()
        dates.append(iso)
        for idx, ilju in enumerate(B._ILJUS):
            k = (iso, ilju)
            if k in table:                       # 조용한 덮어쓰기를 막는다
                duplicates += 1
            table[k] = _raw_good_winner(day, idx, events, cfp)
            invocations += 1
            scored_counts.append(catalog_size)   # 매 행 카탈로그 전체를 채점한다
            per_date[iso] += 1
        day += dt.timedelta(days=1)
    bad_dates = {d: c for d, c in per_date.items() if c != ILJU_COUNT}
    cardinality = {
        "expected_dates": expected_dates,
        "expected_iljus_per_date": ILJU_COUNT,
        "expected_keys": expected_keys,
        "actual_unique_keys": len(table),
        "duplicate_key_overwrites": duplicates,
        "missing_keys": max(0, expected_keys - len(table)),
        "extra_keys": max(0, len(table) - expected_keys),
        "actual_dates": len(per_date),
        "dates_without_exactly_60_keys": bad_dates,
        "extra_dates": sorted(set(per_date) - set(dates)),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "complete": (
            len(table) == expected_keys and duplicates == 0 and not bad_dates
            and len(per_date) == expected_dates
        ),
    }
    if not cardinality["complete"]:
        raise RuntimeError(f"ORACLE_CARDINALITY_MISMATCH: {cardinality}")
    candidate_accounting = {
        "catalog_size": catalog_size,
        "min_candidates_per_pair": min(scored_counts) if scored_counts else None,
        "max_candidates_per_pair": max(scored_counts) if scored_counts else None,
        "mean_candidates_per_pair": (
            round(sum(scored_counts) / len(scored_counts), 3)
            if scored_counts else None
        ),
        "candidate_count_total": sum(scored_counts),
        "candidate_count_is_constant": len(set(scored_counts)) <= 1,
        "matches_pairs_times_catalog": (
            sum(scored_counts) == invocations * catalog_size
        ),
    }
    if not candidate_accounting["matches_pairs_times_catalog"]:
        raise RuntimeError(
            f"CANDIDATE_ACCOUNTING_MISMATCH: {candidate_accounting}"
        )
    content_fp = hashlib.sha256(
        "|".join(
            f"{d}:{i}:{table[(d, i)].event_key}:{table[(d, i)].input_fingerprint}"
            for d, i in sorted(table)
        ).encode("utf-8")
    ).hexdigest()
    return RawWinnerOracle(
        config=config, first_day=first, last_day=last, table=table,
        physical_execution_unit="PER_DATE_ILJU",
        physical_scorer_invocations=invocations,
        scored_date_ilju_pairs=invocations,
        cardinality=cardinality, candidate_accounting=candidate_accounting,
        content_fingerprint=content_fp,
        build_seconds=round(time.perf_counter() - t0, 3),
    )


@dataclass
class LookaheadLedger:
    """선행 조회의 논리/물리 계상과 실행 순수성 원장.

    "적격 행마다 조회 exactly 1" 은 **논리적** 조회 횟수의 계약이다. 사전 계산이나
    중복 제거를 쓰면 물리적 scorer 실행 수는 달라진다 — 그래서 분리해 센다.
    """

    #: 조회 **전** 탈락 — C10 fallback 이 이미 원시 1위가 아닌 행. 조회하지 않는다.
    not_eligible_rows: int = 0
    guard_eligible_rows: int = 0
    logical_lookahead_queries: int = 0
    oracle_cache_hits: int = 0
    unique_oracle_keys: set[tuple[str, str]] = field(default_factory=set)
    recursive_lookahead_calls: int = 0
    lookup_latencies_us: list[float] = field(default_factory=list)
    reasons: collections.Counter[str] = field(default_factory=collections.Counter)

    def as_record(self) -> dict[str, Any]:
        """직렬화 — 지연 표본은 백분위로 요약한다."""
        lat = sorted(self.lookup_latencies_us)
        preserved = self.reasons.get(D1_STREAK_PRESERVED, 0)
        different = self.reasons.get(D1_WINNER_DIFFERENT, 0)
        unavailable = self.reasons.get(D1_UNAVAILABLE, 0)
        return {
            "not_eligible_rows": self.not_eligible_rows,
            "guard_eligible_rows": self.guard_eligible_rows,
            "logical_lookahead_queries": self.logical_lookahead_queries,
            "oracle_cache_hits": self.oracle_cache_hits,
            "unique_oracle_keys": len(self.unique_oracle_keys),
            "recursive_lookahead_calls": self.recursive_lookahead_calls,
            "reasons": dict(self.reasons),
            # 적격 행만 세 사유로 분할된다. NOT_ELIGIBLE 은 조회 전이므로 분모 밖.
            "logical_query_count": self.logical_lookahead_queries,
            "unique_logical_query_keys": len(self.unique_oracle_keys),
            "repeated_logical_queries": (
                self.logical_lookahead_queries - len(self.unique_oracle_keys)
            ),
            "eligible_partition_sum": preserved + different + unavailable,
            "eligible_partition_holds": (
                preserved + different + unavailable == self.guard_eligible_rows
                == self.logical_lookahead_queries
            ),
            "not_eligible_consumed_zero_lookups": (
                self.reasons.get(D1_NOT_ELIGIBLE, 0) == self.not_eligible_rows
                and self.logical_lookahead_queries == self.guard_eligible_rows
            ),
            "lookup_latency_us_p50": (
                round(statistics.median(lat), 3) if lat else None
            ),
            "lookup_latency_us_p95": (
                round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 3) if lat else None
            ),
            "one_logical_query_per_eligible_row": (
                self.logical_lookahead_queries == self.guard_eligible_rows
            ),
        }


def guard_eligible(
    *, raw_winner_event_key: str, proposed_r6_event_key: str | None,
    safe_positive_candidate_exists: bool,
) -> bool:
    """조회 **전** 적격 판정.

    적격성의 본질은 "R6 가 고르려는 후보가 D 원시 1위를 실제로 치환하는가" 다.
    C10 fallback 은 가드 발동 후 돌아갈 결과이지 적격성의 기준값이 아니다 —
    fallback 을 기준으로 쓰면 잘못된 `D1_NOT_ELIGIBLE` 이 생긴다.
    """
    return (
        safe_positive_candidate_exists
        and proposed_r6_event_key is not None
        and proposed_r6_event_key != raw_winner_event_key
    )


def streak_preservation_reason(
    *, d_raw_winner: str, proposed_r6_event_key: str | None,
    d1: RawWinnerProjection | None,
) -> str:
    """적격 행의 가드 사유. `event_key` 정확 일치만 쓴다 — family·순위는 안 읽는다.

    적격 행은 셋으로만 분할된다. `D1_NOT_ELIGIBLE` 은 조회 전 상태이므로 이 함수의
    분모에 들어가지 않는다 — 그것을 여기서 반환하면 partition 이 흐려진다.
    """
    if not guard_eligible(
        raw_winner_event_key=d_raw_winner,
        proposed_r6_event_key=proposed_r6_event_key,
        safe_positive_candidate_exists=proposed_r6_event_key is not None,
    ):
        return D1_NOT_ELIGIBLE
    if d1 is None:
        return D1_UNAVAILABLE           # fail-closed → C10 유지
    if d1.event_key == d_raw_winner:
        return D1_STREAK_PRESERVED
    return D1_WINNER_DIFFERENT


def _fp(values) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()[:16]


def oracle_inline_parity_audit(events, oracle: RawWinnerOracle) -> dict[str, Any]:
    """ORACLE_INLINE_PARITY_AUDIT — oracle 이 같은 raw scorer 인지 전수 대조.

    oracle 검증 **전용** 실행이다. board·history commit 이 없고, 정책 비용 산정과
    OA-11g 효과 판정에 쓰지 않는다. 여기서만 inline 재채점이 일어난다.
    """
    t0 = time.perf_counter()
    checked = 0
    disagreements: list[dict[str, Any]] = []
    invocations = 0
    good_counts: list[int] = []
    catalog_sizes: set[int] = set()
    day = oracle.first_day
    while day <= oracle.last_day:
        ctx = M.build_day_context(day)
        for idx, ilju in enumerate(B._ILJUS):
            stem, branch = ganzi_from_index(idx)
            scored = [M._score_event(k, e, stem, branch, ctx)
                      for k, e in events.items()]
            invocations += 1
            catalog_sizes.add(len(scored))
            goods = [
                (x.event_key, x.probability) for x in scored
                if x.valence == "good"
                and "good" in (events[x.event_key].get("headline_slots")
                               or events[x.event_key]["slots"])
            ]
            good_counts.append(len(goods))
            inline = (
                sorted(goods, key=lambda z: (-z[1], z[0]))[0][0] if goods else None
            )
            proj = oracle.lookup(day, ilju)
            checked += 1
            if proj is None or proj.event_key != inline:
                disagreements.append({
                    "date": day.isoformat(), "ilju": ilju,
                    "inline": inline,
                    "oracle": proj.event_key if proj else None,
                })
        day += dt.timedelta(days=1)
    return {
        "mode": "ORACLE_INLINE_PARITY_AUDIT",
        "excluded_from": [
            "policy_cost_accounting", "oa11g_effect_result",
            "board_commit", "history_commit",
        ],
        "board_commits": 0, "history_commits": 0,
        "checked_pairs": checked,
        "expected_pairs": oracle.cardinality["expected_keys"],
        "disagreements": len(disagreements),
        "disagreement_samples": disagreements[:10],
        "physical_scorer_invocations": invocations,
        "catalog_size_constant": len(catalog_sizes) == 1,
        "catalog_size": next(iter(catalog_sizes)) if len(catalog_sizes) == 1 else None,
        "candidates_scored_total": invocations * (
            next(iter(catalog_sizes)) if len(catalog_sizes) == 1 else 0
        ),
        "raw_good_candidate_count_min": min(good_counts) if good_counts else None,
        "raw_good_candidate_count_max": max(good_counts) if good_counts else None,
        "raw_good_candidate_count_mean": (
            round(sum(good_counts) / len(good_counts), 3) if good_counts else None
        ),
        "raw_good_candidate_count_total": sum(good_counts),
        "audit_seconds": round(time.perf_counter() - t0, 3),
        "verdict": (
            "ORACLE_SEMANTICS_MATCH_INLINE_SCORER" if not disagreements
            and checked == oracle.cardinality["expected_keys"]
            else "ORACLE_SEMANTICS_MISMATCH"
        ),
    }


def replay(
    mode: str, family_of, events, *, last: dt.date,
    oracle: RawWinnerOracle | None = None,
) -> dict[str, Any]:
    """canonical origin 부터 연속 재생한다. `mode` 만 다르고 나머지는 동일하다."""
    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    stats: collections.Counter[str] = collections.Counter()
    ledger = LookaheadLedger()
    rows_out: list[dict[str, Any]] = []
    decisions: dict[str, str] = {}
    consultations: dict[str, str] = {}
    guard_rows: list[dict[str, Any]] = []
    fixture: dict[str, dict[str, Any]] = {}
    losses: list[int] = []
    board_fp: dict[str, str] = {}
    committed_last: dt.date | None = None
    t0 = time.perf_counter()
    day = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= last:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        raw_sel: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        intended: dict[str, str] = {}
        for idx, ilju in enumerate(B._ILJUS):
            stem, branch = ganzi_from_index(idx)
            seed = f"{iso}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx)
                      for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            if not goods:
                continue
            ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
            raw_key, raw_p = ranked[0]
            # oracle 의미 일치 대조는 이 실행에서 하지 않는다 — 정책 replay 의
            # oracle 접근을 가드 D+1 조회로만 한정한다(비용 분모 오염 방지).
            # 전수 대조는 `oracle_inline_parity_audit` 이 별도 실행으로 한다.
            stats["primary_scoring_calls"] += 1
            window = tuple(hh[ilju][-B._LOOKBACK:])
            families = {family_of.get(k, k) for k in window}
            deficit = len(families) < C10_POLICY.coverage_floor
            clean = repeat_severity(gh[ilju], raw_key) == SEVERITY_CLEAN
            chosen = None
            if mode != "S0" and deficit and clean:
                options = B._safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window, family_of,
                    loss_limit=EFFECTIVE_DISPLAY_LOSS_LIMIT,
                )
                stats["rows_with_options"] += bool(options)
                chosen = B._pick("B1", options) if options else None
            # C10 fallback — 같은 날 정보만 쓴다(선행 조회 아님).
            rep = select_good_representative(
                goods, gh[ilju], B._BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=hh[ilju],
            )
            fallback = rep.display_good_representative
            # ── D+1 연속 반복 보존 (read-only oracle) ──────────────────────
            eligible = mode == "R6G" and chosen is not None and guard_eligible(
                raw_winner_event_key=raw_key,
                proposed_r6_event_key=chosen["event_key"] if chosen else None,
                safe_positive_candidate_exists=chosen is not None,
            )
            if mode == "R6G" and chosen is not None and not eligible:
                # 조회 전 탈락. R6 는 항상 원시 1위 아닌 후보를 제안하므로 구조상
                # 0 이어야 한다 — 0 이 아니면 그 가정이 깨진 것이다.
                ledger.not_eligible_rows += 1
                ledger.reasons[D1_NOT_ELIGIBLE] += 1
                consultations[f"{iso}|{ilju}"] = D1_NOT_ELIGIBLE
            elif eligible and chosen is not None:
                ledger.guard_eligible_rows += 1
                d1_day = day + dt.timedelta(days=1)
                t = time.perf_counter()
                d1 = oracle.lookup(d1_day, ilju) if oracle is not None else None
                ledger.lookup_latencies_us.append(
                    (time.perf_counter() - t) * 1_000_000
                )
                ledger.logical_lookahead_queries += 1
                if d1 is not None:
                    ledger.oracle_cache_hits += 1
                ledger.unique_oracle_keys.add((d1_day.isoformat(), ilju))
                reason = (
                    D1_UNAVAILABLE if d1 is None
                    else D1_STREAK_PRESERVED if d1.event_key == raw_key
                    else D1_WINNER_DIFFERENT
                )
                ledger.reasons[reason] += 1
                consultations[f"{iso}|{ilju}"] = reason
                if reason == D1_STREAK_PRESERVED:
                    stats["blocked_by_streak_preservation"] += 1
                    # 차단해도 C10 fallback 이 원시 1위가 아니면 연속 반복이
                    # 복원되지 않는다 — 헛된 차단을 숨기지 않고 센다.
                    if fallback != raw_key:
                        stats["blocked_but_fallback_not_raw_winner"] += 1
                elif reason == D1_UNAVAILABLE:
                    stats["blocked_by_lookup_unavailable"] += 1
                if reason in (D1_STREAK_PRESERVED, D1_UNAVAILABLE):
                    stats["blocked_interventions"] += 1
                    stats["blocked_immediate_gain"] += chosen["fam_qual"] > 0
                    stats["blocked_coverage_only_gain"] += chosen["fam_qual"] == 0
                    guard_rows.append({
                        "date": iso, "ilju": ilju, "reason_code": reason,
                        "d_raw_winner": raw_key,
                        "d1_raw_winner": d1.event_key if d1 else None,
                        "c10_fallback": fallback,
                        "blocked_event": chosen["event_key"],
                        "blocked_fam_qual": chosen["fam_qual"],
                        "blocked_fam_cov": chosen["fam_cov"],
                        "blocked_loss": chosen["loss"],
                    })
                    chosen = None
            if chosen is not None:
                stats["selected"] += 1
                stats["immediate_threshold_gain"] += chosen["fam_qual"] > 0
                losses.append(chosen["loss"])
                if chosen["loss"] > EFFECTIVE_DISPLAY_LOSS_LIMIT:
                    stats["loss_violation"] += 1
                if chosen["loss"] >= B._BUDGET:
                    stats["global_budget_loss_interventions"] += 1
                top_band = strength_band(raw_p)
                band = strength_band(raw_p - chosen["loss"])
                if top_band == 4 and band < top_band:
                    stats["strong_signal_violation"] += 1
                if top_band - band >= 2:
                    stats["two_band_violation"] += 1
                g, c, s = chosen["slots"]
                cands = chosen["cands"]
                intended[ilju] = chosen["event_key"]
            else:
                g, c, s = M._select_slots(scored, seed, good_override=fallback)
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                intended[ilju] = fallback
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw_sel[ilju] = cmap[ilju][0]
            if ilju == FIXTURE_ILJU and iso in (
                FIXTURE_BLOCK_DATE, FIXTURE_EFFECT_DATE
            ):
                fixture[iso] = {
                    "raw_good_winner": raw_key,
                    "repeat_severity_of_raw_top": repeat_severity(gh[ilju], raw_key),
                    "family_deficit_active": deficit,
                    "marginal_candidate_exists": bool(
                        stats and mode != "S0" and deficit and clean
                    ),
                    "c10_consulted": True,
                    "c10_representative": fallback,
                    "c10_kept_raw_top": fallback == raw_key,
                    "selector_intervened": chosen is not None,
                    "guard_reason": consultations.get(f"{iso}|{ilju}"),
                    "intended_committed": intended[ilju],
                }
            gh[ilju].append(intended[ilju])
            rows_out.append({
                "fortune_date": iso, "ilju": ilju, "final_headline": None,
            })
        result = select_board(
            raw_sel, cmap, hh,
            domain_cap=DAILY_BOARD_CONTRACT_V1.domain_cap_count,
            event_cap=DAILY_BOARD_CONTRACT_V1.event_cap_count,
            max_displacement_cost=B._BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        stats["domain_cap_hard_violation"] += result.domain_cap_hard_violation
        stats["domain_cap_authorized_override"] += result.domain_cap_authorized_override
        stats["domain_overflow"] += result.domain_overflow
        stats["event_overflow"] += result.event_overflow
        base = len(rows_out) - len(raw_sel)
        for offset, ilju in enumerate(i for i in B._ILJUS if i in raw_sel):
            sel = result.selections[ilju]
            rows_out[base + offset]["final_headline"] = sel.event_key
            hh[ilju].append(sel.event_key)
            decisions[f"{iso}|{ilju}"] = sel.event_key
            if ilju == FIXTURE_ILJU and iso in fixture:
                fixture[iso]["board_realized"] = sel.event_key
                fixture[iso]["history_committed"] = sel.event_key
                fixture[iso]["history_committed_family"] = family_of.get(
                    sel.event_key, sel.event_key
                )
        board_fp[iso] = _fp(
            [f"{i}={result.selections[i].event_key}" for i in sorted(result.selections)]
        )
        committed_last = day
        day += dt.timedelta(days=1)
    return {
        "rows": rows_out, "stats": dict(stats), "decisions": decisions,
        "consultations": consultations, "fixture": fixture,
        "ledger": ledger.as_record(), "guard_rows": guard_rows,
        "board_fp": board_fp,
        "history_fp": _fp(
            [f"{k}={'>'.join(v)}" for k, v in sorted(hh.items())]
        ),
        "state_fp": _fp(
            [f"{k}={'>'.join(v)}" for k, v in sorted(gh.items())]
        ),
        "display_loss_max": max(losses) if losses else 0,
        "replay_seconds": round(time.perf_counter() - t0, 3),
        "last_committed_day": committed_last.isoformat() if committed_last else None,
        "days_committed": (
            (committed_last - DAILY_ROLLING_AUDIT_CONTRACT_V1.origin).days + 1
            if committed_last else 0
        ),
    }


def _anchor_view(rows, family_of, domain_of, contract) -> dict[str, Any]:
    """계약이 정한 **모든** anchor 를 낸다 — 5개 고정 목록에 묶지 않는다."""
    agg = build_rolling_audit_aggregates(rows, family_of, domain_of, contract)
    by = {a["anchor_date"]: a for a in agg["anchors"]}
    fam_q = agg["family_qualifying_count_by_anchor"]
    fam_below = agg["family_below_iljus_by_anchor"]
    key_below = agg["below_iljus_by_anchor"]
    return {
        iso: {
            "family_p10": by[iso]["family_p10"],
            "family_qualifying": fam_q[iso],
            "key_p10": by[iso]["key_p10"],
            "key_below_15": by[iso]["count_below_15"],
            "domain_p10": by[iso]["domain_p10"],
            "family_below_iljus": sorted(fam_below[iso]),
            "key_below_iljus": sorted(key_below[iso]),
        }
        for iso in by
    }


def _causal_fixture(res, anchors) -> dict[str, Any]:
    """인과 사슬을 단계별로 검증한다 — 최종 coverage 만 보지 않는다."""
    g, s0, r6 = res["R6G"]["fixture"], res["S0"]["fixture"], res["R6"]["fixture"]
    d14, d15 = FIXTURE_BLOCK_DATE, FIXTURE_EFFECT_DATE
    blocked = [
        r for r in res["R6G"]["guard_rows"]
        if r["date"] == d14 and r["ilju"] == FIXTURE_ILJU
    ]
    a = anchors["R6G"][FIXTURE_ANCHOR]
    steps = {
        "0314_r6_would_intervene": r6.get(d14, {}).get("selector_intervened") is True,
        "0314_d_raw_winner_is_good_news": (
            g.get(d14, {}).get("raw_good_winner") == "good_news_arrives"
        ),
        "0314_guard_consulted": g.get(d14, {}).get("guard_reason") is not None,
        "0314_guard_triggered": bool(blocked)
        and blocked[0]["reason_code"] == D1_STREAK_PRESERVED,
        "0314_d1_matches_d": bool(blocked)
        and blocked[0]["d1_raw_winner"] == blocked[0]["d_raw_winner"],
        "0314_intervention_blocked": (
            g.get(d14, {}).get("selector_intervened") is False
        ),
        "0314_history_committed_raw_winner": (
            g.get(d14, {}).get("history_committed")
            == g.get(d14, {}).get("raw_good_winner")
        ),
        "0315_severity_consecutive": (
            g.get(d15, {}).get("repeat_severity_of_raw_top") == 3
        ),
        "0315_c10_avoidance_fired": g.get(d15, {}).get("c10_kept_raw_top") is False,
        "0315_representative_matches_s0": (
            g.get(d15, {}).get("c10_representative")
            == s0.get(d15, {}).get("c10_representative")
        ),
        "0315_board_realized_matches_s0": (
            g.get(d15, {}).get("board_realized")
            == s0.get(d15, {}).get("board_realized")
        ),
        "0315_history_committed_matches_s0": (
            g.get(d15, {}).get("history_committed")
            == s0.get(d15, {}).get("history_committed")
        ),
        "anchor_family_not_below": FIXTURE_ILJU not in a["family_below_iljus"],
        "anchor_key_not_below": FIXTURE_ILJU not in a["key_below_iljus"],
    }
    # 반대 fixture — D+1 원시 1위가 다르면 상담만 하고 차단하지 않는다.
    diff_rows = [
        k for k, v in res["R6G"]["consultations"].items() if v == D1_WINNER_DIFFERENT
    ]
    counter = {
        "observed_rows": len(diff_rows),
        "sample": diff_rows[:5],
        "none_of_them_blocked": all(
            not any(
                r["date"] == k.split("|")[0] and r["ilju"] == k.split("|")[1]
                for r in res["R6G"]["guard_rows"]
            )
            for k in diff_rows
        ),
        "intervention_survived": all(
            res["R6G"]["decisions"].get(k) is not None for k in diff_rows
        ),
    }
    return {
        "target_ilju": FIXTURE_ILJU,
        "block_date": d14, "effect_date": d15, "anchor": FIXTURE_ANCHOR,
        "guard_row": blocked[0] if blocked else None,
        "trace": {"S0": s0, "R6": r6, "R6G": g},
        "steps": steps,
        "chain_fully_restored": all(steps.values()),
        "failed_steps": [k for k, v in steps.items() if not v],
        "counter_fixture_d1_different": counter,
    }


def run(*, canonical: bool = False) -> dict[str, Any]:
    """oracle 사전 생성 → S0·R6·R6G 재생 → 수용 기준 적용.

    Args:
        canonical: True 면 평가 종료일을 2027-12-31 로 늘리고 공식 v1 계약(anchor
            730)을 쓴다. False 면 OA-11f 계열과 같은 5-anchor 구간이다.
    """
    global EVALUATION_LAST, ORACLE_LAST
    EVALUATION_LAST = CANONICAL_LAST if canonical else FIVE_ANCHOR_LAST
    ORACLE_LAST = EVALUATION_LAST + dt.timedelta(days=1)
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}
    anchor_days = (EVALUATION_LAST - dt.date(2026, 1, 1)).days + 1
    contract = (
        ROLLING_AUDIT_AGGREGATE_CONTRACT_V1 if canonical
        else derive_diagnostic_contract(anchor_days=anchor_days)
    )
    if canonical and contract.anchor_days != anchor_days:
        raise RuntimeError(
            "CANONICAL_ANCHOR_RANGE_MISMATCH: 계약 "
            f"{contract.anchor_days} != 생성 구간 {anchor_days}"
        )
    oracle = build_raw_winner_oracle(events, last=ORACLE_LAST)
    # ── oracle 의미 일치 — 고정 표본 회귀 ─────────────────────────────────
    #: 전수(55,020행) inline 재채점은 release blocker 로 두지 않는다. oracle 이
    #: **같은 raw scorer 를 직접 호출한다는 구조** + config 지문 + 인과 fixture +
    #: 아래 고정 표본으로 봉인한다. 전수 감사는 필요할 때
    #: `oracle_inline_parity_audit()` 를 따로 실행한다.
    sample_keys = [
        (dt.date(2026, 3, 14), FIXTURE_ILJU),
        (dt.date(2026, 3, 15), FIXTURE_ILJU),
        (ORACLE_FIRST, B._ILJUS[0]),
        (ORACLE_LAST, B._ILJUS[-1]),
        (dt.date(2026, 2, 12), FIXTURE_ILJU),
        (dt.date(2027, 3, 3), B._ILJUS[30]),
    ]
    sample_rows: list[dict[str, Any]] = []
    for day_, ilju_ in sample_keys:
        idx_ = B._ILJUS.index(ilju_)
        stem_, branch_ = ganzi_from_index(idx_)
        ctx_ = M.build_day_context(day_)
        scored_ = [M._score_event(k, e, stem_, branch_, ctx_)
                   for k, e in events.items()]
        goods_ = [
            (x.event_key, x.probability) for x in scored_
            if x.valence == "good"
            and "good" in (events[x.event_key].get("headline_slots")
                           or events[x.event_key]["slots"])
        ]
        inline_ = (
            sorted(goods_, key=lambda z: (-z[1], z[0]))[0][0] if goods_ else None
        )
        proj_ = oracle.lookup(day_, ilju_)
        sample_rows.append({
            "date": day_.isoformat(), "ilju": ilju_, "inline": inline_,
            "oracle": proj_.event_key if proj_ else None,
            "agrees": proj_ is not None and proj_.event_key == inline_,
        })
    sample_parity = {
        "scope": "FIXED_SAMPLE_NOT_EXHAUSTIVE",
        "release_blocker": False,
        "sealed_by": [
            "oracle calls the same raw scorer directly",
            "raw_winner_oracle_config_fp",
            "2026-03-14 causal fixture",
            "these fixed samples",
        ],
        "checked": len(sample_rows),
        "disagreements": sum(1 for r in sample_rows if not r["agrees"]),
        "rows": sample_rows,
        "verdict": (
            "SAMPLE_PARITY_OK" if all(r["agrees"] for r in sample_rows)
            else "SAMPLE_PARITY_MISMATCH"
        ),
    }
    # ── oracle 순수성 — 재생 전후로 테이블이 움직이지 않았는지 ────────────
    def _rng_state() -> str:
        parts = [repr(random.getstate())]
        try:                                     # numpy 는 선택 의존성
            import numpy as _np

            parts.append(repr(_np.random.get_state()))
        except ImportError:
            parts.append("numpy_absent")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    before = {
        "size": len(oracle.table),
        "content_fp": hashlib.sha256(
            "|".join(
                f"{d}:{i}:{oracle.table[(d, i)].event_key}"
                f":{oracle.table[(d, i)].input_fingerprint}"
                for d, i in sorted(oracle.table)
            ).encode("utf-8")
        ).hexdigest(),
        "rng": _rng_state(),
    }
    # 같은 key 를 반복 조회해도 값이 같고 테이블이 변하지 않아야 한다.
    probe_key = (ORACLE_FIRST.isoformat(), B._ILJUS[0])
    repeated = [
        oracle.lookup(ORACLE_FIRST, B._ILJUS[0]) for _ in range(3)
    ]
    repeat_stable = all(r == repeated[0] for r in repeated)
    repeat_no_growth = len(oracle.table) == before["size"]
    res = {
        m: replay(m, family_of, events, last=EVALUATION_LAST, oracle=oracle)
        for m in MODES
    }
    after = {
        "size": len(oracle.table),
        "content_fp": hashlib.sha256(
            "|".join(
                f"{d}:{i}:{oracle.table[(d, i)].event_key}"
                f":{oracle.table[(d, i)].input_fingerprint}"
                for d, i in sorted(oracle.table)
            ).encode("utf-8")
        ).hexdigest(),
        "rng": _rng_state(),
    }
    oracle_purity = {
        "size_before": before["size"], "size_after": after["size"],
        "size_unchanged": before["size"] == after["size"],
        "content_fp_unchanged": before["content_fp"] == after["content_fp"],
        "content_fp_matches_build": before["content_fp"] == oracle.content_fingerprint,
        "rng_state_unchanged": before["rng"] == after["rng"],
        "repeated_lookup_value_equal": repeat_stable,
        "repeated_lookup_no_table_growth": repeat_no_growth,
        "probe_key": list(probe_key),
        "scorer_reexecution_during_replay": 0,
        "holds": (
            before["size"] == after["size"]
            and before["content_fp"] == after["content_fp"]
            and before["content_fp"] == oracle.content_fingerprint
            and before["rng"] == after["rng"]
            and repeat_stable and repeat_no_growth
        ),
    }
    anchors = {
        m: _anchor_view(res[m]["rows"], family_of, domain_of, contract) for m in MODES
    }

    s0 = anchors["S0"]
    anchor_dates = sorted(s0)
    verdict: dict[str, Any] = {}
    for m in ("R6", "R6G"):
        a, st = anchors[m], res[m]["stats"]
        cross_all = {
            iso: {
                "family_downcross": sorted(
                    set(a[iso]["family_below_iljus"])
                    - set(s0[iso]["family_below_iljus"])
                ),
                "key_downcross": sorted(
                    set(a[iso]["key_below_iljus"]) - set(s0[iso]["key_below_iljus"])
                ),
                "family_upcross": sorted(
                    set(s0[iso]["family_below_iljus"])
                    - set(a[iso]["family_below_iljus"])
                ),
            }
            for iso in anchor_dates
        }
        cross = {
            iso: c for iso, c in cross_all.items()
            if c["family_downcross"] or c["key_downcross"] or c["family_upcross"]
        }
        v = {
            "anchor_count": len(anchor_dates),
            "family_gate_pass_anchors": sum(
                a[iso]["family_p10"] >= _QUALIFY and a[iso]["family_qualifying"] >= 55
                for iso in anchor_dates
            ),
            "family_qualifying_regression_anchors": [
                iso for iso in anchor_dates
                if a[iso]["family_qualifying"] < s0[iso]["family_qualifying"]
            ],
            "key_below_increase_anchors": [
                iso for iso in anchor_dates
                if a[iso]["key_below_15"] > s0[iso]["key_below_15"]
            ],
            "domain_regression_anchors": [
                iso for iso in anchor_dates
                if a[iso]["domain_p10"] < s0[iso]["domain_p10"]
            ],
            "family_downcross_anchors": sorted(
                iso for iso, c in cross_all.items() if c["family_downcross"]
            ),
            "key_downcross_anchors": sorted(
                iso for iso, c in cross_all.items() if c["key_downcross"]
            ),
            "family_downcross_count": sum(
                len(c["family_downcross"]) for c in cross_all.values()
            ),
            "key_downcross_count": sum(
                len(c["key_downcross"]) for c in cross_all.values()
            ),
            "crossings_nonempty_only": cross,
            "strong_signal_violation": st.get("strong_signal_violation", 0),
            "two_band_violation": st.get("two_band_violation", 0),
            "loss_violation": st.get("loss_violation", 0),
            "cap_violation": st.get("domain_cap_hard_violation", 0),
            #: 정당화된 override 는 **증가**만 퇴행이다. 감소(-1)는 개선이므로
            #: `== 0` 을 요구하면 개선을 실패로 계상한다(ERRATUM 참조).
            "authorized_overrides": st.get("domain_cap_authorized_override", 0),
            "s0_authorized_overrides": res["S0"]["stats"].get(
                "domain_cap_authorized_override", 0
            ),
            "override_delta": (
                st.get("domain_cap_authorized_override", 0)
                - res["S0"]["stats"].get("domain_cap_authorized_override", 0)
            ),
            "new_override_introduced": (
                st.get("domain_cap_authorized_override", 0)
                > res["S0"]["stats"].get("domain_cap_authorized_override", 0)
            ),
            "display_loss_max": res[m]["display_loss_max"],
            "global_budget_loss_interventions": st.get(
                "global_budget_loss_interventions", 0
            ),
            "lookahead_unavailable": res[m]["ledger"]["reasons"].get(D1_UNAVAILABLE, 0),
        }
        verdict[m] = v

    # 범위 누출 — R6G 가 R6 와 처음 갈리기 전 구간에서 달라졌는가.
    first_block = (
        res["R6G"]["guard_rows"][0]["date"] if res["R6G"]["guard_rows"] else None
    )
    leaks = [
        k for k, val in res["R6G"]["decisions"].items()
        if res["R6"]["decisions"].get(k) != val
        and (first_block is None or k.split("|")[0] < first_block)
    ]
    for m in ("R6", "R6G"):
        v = verdict[m]
        v["scope_leakage"] = len(leaks) if m == "R6G" else 0
        checks = {
            "family_gate": v["family_gate_pass_anchors"] == len(anchor_dates),
            "family_qualifying_regression": not v[
                "family_qualifying_regression_anchors"
            ],
            "key_below_increase": not v["key_below_increase_anchors"],
            "domain_regression": not v["domain_regression_anchors"],
            "family_downcross": v["family_downcross_count"] == 0,
            "key_downcross": v["key_downcross_count"] == 0,
            "strong_signal": v["strong_signal_violation"] == 0,
            "two_band": v["two_band_violation"] == 0,
            "loss": v["loss_violation"] == 0,
            "cap_hard_violation": v["cap_violation"] == 0,
            "authorized_override_not_increased": v["override_delta"] <= 0,
            "scope_leakage": v["scope_leakage"] == 0,
            "display_loss_max": (
                v["display_loss_max"] <= EFFECTIVE_DISPLAY_LOSS_LIMIT
            ),
            "global_budget_interventions": (
                v["global_budget_loss_interventions"] == 0
            ),
            "lookahead_available": v["lookahead_unavailable"] == 0,
        }
        v["criteria"] = checks
        v["failed_criteria"] = [k for k, ok in checks.items() if not ok]
        v["fully_nonregressive_computed"] = all(checks.values())
        v["fully_nonregressive"] = (
            v["family_gate_pass_anchors"] == len(B.ANCHORS)
            and not v["family_qualifying_regression_anchors"]
            and not v["key_below_increase_anchors"]
            and not v["domain_regression_anchors"]
            and v["family_downcross_count"] == 0
            and v["key_downcross_count"] == 0
            and v["strong_signal_violation"] == 0
            and v["two_band_violation"] == 0
            and v["loss_violation"] == 0
            and v["cap_violation"] == 0
            and v["override_delta"] <= 0
            and v["scope_leakage"] == 0
            and v["display_loss_max"] <= EFFECTIVE_DISPLAY_LOSS_LIMIT
            and v["global_budget_loss_interventions"] == 0
            and v["lookahead_unavailable"] == 0
        )

    # ── 차단 손실 — 로컬 delta 합산이 아니라 두 replay 의 anchor 차이 ────────
    r6a, r6ga = anchors["R6"], anchors["R6G"]
    per_anchor = {
        iso: r6ga[iso]["family_qualifying"] - r6a[iso]["family_qualifying"]
        for iso in B.ANCHORS
    }
    blocked_cost = {
        "blocked_local_gain_count": res["R6G"]["stats"].get(
            "blocked_immediate_gain", 0
        ),
        "blocked_interventions": res["R6G"]["stats"].get("blocked_interventions", 0),
        "blocked_coverage_only_gain": res["R6G"]["stats"].get(
            "blocked_coverage_only_gain", 0
        ),
        "per_anchor_family_qualifying_delta_vs_r6": per_anchor,
        "gross_anchor_gain_lost": sum(-d for d in per_anchor.values() if d < 0),
        "downstream_gain_recovered": sum(d for d in per_anchor.values() if d > 0),
        "net_anchor_effect": sum(per_anchor.values()),
        "note": (
            "차단 후보의 로컬 delta 를 합산하지 않는다 — 순차 history 가 바뀌므로 "
            "R6 와 OA-11g 두 replay 의 anchor 결과 차이로만 판정한다."
        ),
    }

    # harness drift — S0·R6 는 냉동된 OA-11f-B 의 S0·B1 과 같아야 한다.
    prior = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_b_online_replay_r6.json"
    drift: dict[str, Any] = {"artifact_present": prior.exists()}
    if prior.exists():
        pri = json.loads(prior.read_text(encoding="utf-8"))["modes"]
        fields_ = ("family_p10", "family_qualifying", "key_p10", "key_below_15")
        mismatches = [
            {
                "anchor": iso, "pair": f"{here}=={there}",
                "mine": {k: anchors[here][iso][k] for k in fields_},
                "frozen": {k: pri[there]["anchors"][iso][k] for k in fields_},
            }
            for here, there in (("S0", "S0"), ("R6", "B1"))
            for iso in B.ANCHORS
            if any(
                anchors[here][iso][k] != pri[there]["anchors"][iso][k]
                for k in fields_
            )
        ]
        drift |= {
            "compared_pairs": ["S0==S0", "R6==B1"],
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:10],
            "verdict": "NO_DRIFT" if not mismatches else "HARNESS_DRIFT",
        }

    g = verdict["R6G"]
    no_downcross = (
        g["family_downcross_count"] == 0 and g["key_downcross_count"] == 0
    )
    gate_full = g["family_gate_pass_anchors"] == len(anchor_dates)
    conclusion = (
        "ONLINE_CAUSAL_CLOSABILITY_PROVEN" if g["fully_nonregressive"]
        else "OVERCONSERVATIVE" if no_downcross and not gate_full
        # downcross 0 · gate 만점인데도 실패면 비퇴행 부족이 아니라 다른 플래그다.
        # 라벨을 뭉개면 원인이 사라지므로 걸린 플래그를 이름에 남긴다.
        else f"BLOCKED_BY:{','.join(g['failed_criteria'])}"
        if no_downcross and gate_full
        else "NONREGRESSION_INSUFFICIENT"
    )
    lg = res["R6G"]["ledger"]
    def _passing(view) -> int:
        return sum(
            view[iso]["family_p10"] >= _QUALIFY
            and view[iso]["key_p10"] >= _QUALIFY
            for iso in anchor_dates
        )

    def _movement(field: str) -> dict[str, int]:
        imp = unc = reg = 0
        for iso in anchor_dates:
            delta = anchors["R6G"][iso][field] - s0[iso][field]
            imp += delta > 0
            unc += delta == 0
            reg += delta < 0
        return {"improved": imp, "unchanged": unc, "regressed": reg}

    effect = {
        "anchor_count": len(anchor_dates),
        "s0_passing_anchors": _passing(s0),
        "r6_passing_anchors": _passing(anchors["R6"]),
        "r6g_passing_anchors": _passing(anchors["R6G"]),
        "net_passing_anchor_gain": _passing(anchors["R6G"]) - _passing(s0),
        "family_p10": _movement("family_p10"),
        "key_p10": _movement("key_p10"),
        "domain_p10": _movement("domain_p10"),
        "family_qualifying": _movement("family_qualifying"),
    }
    return {
        "audit_id": "OA-11g",
        "policy_id": POLICY_ID,
        "policy_status": "shadow_measurement_only",
        "live_behavior_changed": False,
        "production_policy": "C10_UNCHANGED",
        "base_selector": BASE_SELECTOR,
        "contract_mode": contract_mode(contract),
        "anchor_days": contract.anchor_days,
        "evaluation_last": EVALUATION_LAST.isoformat(),
        #: 수용 기준 정정 기록 — 결과를 통과시키기 위한 완화가 아니라, "추가
        #: override 가 없어야 한다"는 기존 의도를 올바른 부호로 구현한 것이다.
        "erratum": {
            "id": "OA11G-ERRATUM-1",
            "previous_check": "override_delta == 0",
            "defect": (
                "감소까지 실패로 처리해 '추가 override 없음' 이라는 의도와 불일치"
            ),
            "corrected_check": "override_delta <= 0",
            "policy_behavior_changed": False,
            "measurement_rows_changed": False,
            "selection_changed": False,
            "acceptance_semantics_corrected": True,
            "observed": {
                "s0_authorized_overrides": res["S0"]["stats"].get(
                    "domain_cap_authorized_override", 0
                ),
                "r6g_authorized_overrides": res["R6G"]["stats"].get(
                    "domain_cap_authorized_override", 0
                ),
                "override_delta": (
                    res["R6G"]["stats"].get("domain_cap_authorized_override", 0)
                    - res["S0"]["stats"].get("domain_cap_authorized_override", 0)
                ),
                "new_override_introduced": (
                    res["R6G"]["stats"].get("domain_cap_authorized_override", 0)
                    > res["S0"]["stats"].get("domain_cap_authorized_override", 0)
                ),
                "domain_cap_hard_violation": {
                    m: res[m]["stats"].get("domain_cap_hard_violation", 0)
                    for m in MODES
                },
            },
        },
        "effect": effect,
        "oracle_implementation_status": (
            "AUDIT_ONLY_NOT_PRODUCTION_READY — 전 구간 사전 생성은 조회 대비 "
            "과생성이 크다. 상용 구현은 일일 배치 병합 또는 적격 행 lazy 생성이 "
            "필요하며, 이는 정책 효과 검증과 분리된 후속 최적화다."
        ),
        "r7_role": "COMPARISON_ONLY_NOT_A_POLICY_BASE",
        "r6_r7_status": "INERT_REJECTED",
        "lookahead_contract": D1_CONTRACT.__dict__,
        "oracle": {
            "config": oracle.config,
            "generation_range": (
                f"{oracle.first_day.isoformat()} ~ {oracle.last_day.isoformat()}"
            ),
            "cardinality": oracle.cardinality,
            "physical_execution_unit": oracle.physical_execution_unit,
            "physical_scorer_invocations": oracle.physical_scorer_invocations,
            "scored_date_ilju_pairs": oracle.scored_date_ilju_pairs,
            "content_fingerprint": oracle.content_fingerprint,
            "build_seconds": oracle.build_seconds,
            "runtime_behavior": "READ_ONLY_LOOKUP",
            "purity": oracle_purity,
            "inline_sample_parity": sample_parity,
        },
        "boundary_contract": {
            "evaluation_range": (
                f"{DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat()} ~ "
                f"{EVALUATION_LAST.isoformat()}"
            ),
            "oracle_touches_through": ORACLE_LAST.isoformat(),
            "padding_excluded_from": [
                "public_row", "board", "history_commit", "anchor_aggregate", "episode",
            ],
            "last_committed_day": res["R6G"]["last_committed_day"],
            "days_committed": res["R6G"]["days_committed"],
            "padding_day_committed": (
                res["R6G"]["last_committed_day"] == ORACLE_LAST.isoformat()
            ),
            "rows_beyond_evaluation_last": sum(
                1 for r in res["R6G"]["rows"]
                if r["fortune_date"] > EVALUATION_LAST.isoformat()
            ),
        },
        "purity": {
            m: {
                "ledger": res[m]["ledger"],
                "recursive_lookahead_calls": res[m]["ledger"][
                    "recursive_lookahead_calls"
                ],
                "one_logical_query_per_eligible_row": res[m]["ledger"][
                    "one_logical_query_per_eligible_row"
                ],
            }
            for m in MODES
        },
        "cost": {
            "logical_query_count": lg["logical_query_count"],
            "unique_logical_query_keys": lg["unique_logical_query_keys"],
            "repeated_logical_queries": lg["repeated_logical_queries"],
            "oracle_cache_hits": lg["oracle_cache_hits"],
            "physical_scorer_invocations": oracle.physical_scorer_invocations,
            "scored_date_ilju_pairs": oracle.scored_date_ilju_pairs,
            #: 실제 합계 — pairs × |catalog| 는 후보 수가 완전히 고정된 경우에만
            #: 맞다. 그래서 build 에서 센 값을 쓰고 불변성도 함께 남긴다.
            "extra_candidates_scored": oracle.candidate_accounting[
                "candidate_count_total"
            ],
            "candidate_accounting": oracle.candidate_accounting,
            "unused_oracle_keys": (
                oracle.cardinality["actual_unique_keys"]
                - lg["unique_logical_query_keys"]
            ),
            "oracle_storage_fill_ratio": round(
                oracle.cardinality["actual_unique_keys"]
                / max(1, oracle.cardinality["expected_keys"]), 6
            ),
            "oracle_query_overbuild_ratio": round(
                oracle.cardinality["actual_unique_keys"]
                / max(1, lg["unique_logical_query_keys"]), 2
            ),
            "oracle_build_cost_seconds": oracle.build_seconds,
            "runtime_lookup_latency_us_p50": lg["lookup_latency_us_p50"],
            "runtime_lookup_latency_us_p95": lg["lookup_latency_us_p95"],
            "replay_seconds": {m: res[m]["replay_seconds"] for m in MODES},
            "replay_wall_time_multiplier_vs_r6": round(
                res["R6G"]["replay_seconds"] / max(1e-9, res["R6"]["replay_seconds"]),
                4,
            ),
            "note": (
                "전 구간 사전 생성이므로 물리 실행이 논리 조회보다 훨씬 많다 — "
                "overbuild 비율을 함께 남긴다. 상용화 판단에는 oracle_build_cost 와 "
                "runtime_lookup_cost 를 합친 요청당 모델이 필요하다."
            ),
        },
        "blocked_cost": blocked_cost,
        "causal_fixture": _causal_fixture(res, anchors),
        "baseline_drift_check": drift,
        "stats": {m: res[m]["stats"] for m in MODES},
        "named_anchor_continuity": {
            m: {iso: anchors[m][iso] for iso in B.ANCHORS if iso in anchors[m]}
            for m in MODES
        },
        "anchors": (
            {m: {iso: anchors[m][iso] for iso in B.ANCHORS if iso in anchors[m]}
             for m in MODES}
            if canonical else anchors
        ),
        "verdict": verdict,
        "conclusion": conclusion,
        "guard_rows": res["R6G"]["guard_rows"],
        "reason_code_totals": lg["reasons"],
    }


if __name__ == "__main__":
    _canonical = "--canonical" in sys.argv
    r = run(canonical=_canonical)
    out = _ROOT / "doc" / "v2_2" / "audits" / (
        "oa11g_canonical_730_anchor.json" if _canonical
        else "oa11g_d1_streak_shadow.json"
    )
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name, "→", r["conclusion"])
    print("  기반 selector:", r["base_selector"], "· 계약", r["contract_mode"],
          "· anchor", r["anchor_days"], "· 평가 종료", r["evaluation_last"])
    print("  효과:", r["effect"])
    print("  oracle:", r["oracle"]["cardinality"]["actual_unique_keys"], "keys ·",
          "완전성", r["oracle"]["cardinality"]["complete"], "·",
          r["oracle"]["build_seconds"], "s ·", "순수성",
          r["oracle"]["purity"]["holds"])
    print("  카디널리티:", {k: v for k, v in r["oracle"]["cardinality"].items()
                           if k not in ("dates_without_exactly_60_keys",)})
    print("  표본 parity:", r["oracle"]["inline_sample_parity"]["verdict"],
          "불일치", r["oracle"]["inline_sample_parity"]["disagreements"])
    print("  경계: 마지막 commit", r["boundary_contract"]["last_committed_day"],
          "· padding commit", r["boundary_contract"]["padding_day_committed"],
          "· 초과 행", r["boundary_contract"]["rows_beyond_evaluation_last"])
    print("  사유 코드:", r["reason_code_totals"])
    pu = r["purity"]["R6G"]["ledger"]
    print("  partition 성립:", pu["eligible_partition_holds"],
          "· NOT_ELIGIBLE 조회 0:", pu["not_eligible_consumed_zero_lookups"],
          "· 적격", pu["guard_eligible_rows"], "논리조회",
          pu["logical_lookahead_queries"], "비적격", pu["not_eligible_rows"])
    print("  비용:", {k: r["cost"][k] for k in (
        "logical_query_count", "unique_logical_query_keys",
        "physical_scorer_invocations", "oracle_query_overbuild_ratio",
        "unused_oracle_keys", "oracle_build_cost_seconds",
        "runtime_lookup_latency_us_p50", "runtime_lookup_latency_us_p95",
        "replay_wall_time_multiplier_vs_r6")})
    print("  차단 손실:", {k: v for k, v in r["blocked_cost"].items() if k != "note"})
    print("  기준선 대조:", r["baseline_drift_check"].get("verdict"),
          r["baseline_drift_check"].get("mismatch_count"))
    for m in MODES:
        print(f"  {m:5} {r['stats'][m]}")
        for iso in B.ANCHORS:
            a = r["named_anchor_continuity"][m].get(iso)
            if a is None:
                continue
            print(f"        {iso} family {a['family_p10']}/{a['family_qualifying']} "
                  f"key {a['key_p10']}/{a['key_below_15']} domain {a['domain_p10']}")
    for m in ("R6", "R6G"):
        v = r["verdict"][m]
        print(f"  판정 {m}: gate {v['family_gate_pass_anchors']}/5 "
              f"downcross f{v['family_downcross_count']}/k{v['key_downcross_count']} "
              f"qual퇴행 {v['family_qualifying_regression_anchors']} "
              f"key증가 {v['key_below_increase_anchors']} "
              f"domain {v['domain_regression_anchors']} "
              f"safety s5={v['strong_signal_violation']}/2band="
              f"{v['two_band_violation']}/loss={v['loss_violation']} "
              f"cap {v['cap_violation']} override {v['override_delta']} "
              f"실패기준 {v['failed_criteria']} "
              f"lossmax {v['display_loss_max']} leak {v['scope_leakage']} "
              f"→ 전면비퇴행 {v['fully_nonregressive']}")
    cf = r["causal_fixture"]
    print("  인과 fixture 전면 복원:", cf["chain_fully_restored"],
          "실패:", cf["failed_steps"])
    for k, v in cf["steps"].items():
        print(f"      {'OK ' if v else 'NG '} {k}")
    print("  반대 fixture:", cf["counter_fixture_d1_different"])

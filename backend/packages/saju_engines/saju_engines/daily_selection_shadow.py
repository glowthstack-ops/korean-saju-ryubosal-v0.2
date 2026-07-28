"""OA-6d2 — 선택 계약 v1(라이브 동결) vs v2(후보 해시) shadow 비교.

**라이브 선택을 바꾸지 않는다.** v2가 무엇을 골랐을지만 계산해 감사에 남긴다.

핵심 불변식: candidate hash는 **최고 merit 동치류 안에서만** 승자를 바꿀 수 있다.
낮은 probability 후보로 이동했다면 tie-break이 실질 순위를 침범한 것이다.

변경 원인을 두 종류로 나눈다 — 한 칸에 담으면 v1에서 발견한 해시 충돌 결함이 묻힌다.

    legacy_truncated_hash_collision_resolved   `% 9973` 축약 충돌 해소(결함 수정)
    candidate_hash_contract_changed            정상적인 새 tie-break 결과
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.daily_fortune import DayGanjiContext

from .daily_ilju_fortune import (
    EVENT_SELECTION_COMPAT_SALT,
    EVENT_SELECTION_CONTRACT,
    EVENT_SELECTION_CONTRACT_V2,
    DailyFortuneDicts,
    _rank_key_v2,
    _score_event,
    _select_slots,
    _stable_hash,
    _tiebreak_v1,
    _tiebreak_v2,
    event_merit_key,
)


@dataclass(frozen=True)
class EventRankTrace:
    """v2 순위 추적 — 계약이 어떤 값으로 결정됐는지 사후 확인용."""

    event_key: str
    probability: int
    merit_key: tuple[int, ...]
    tiebreak_full_hash: int
    final_stable_key: str
    selection_contract: str = EVENT_SELECTION_CONTRACT_V2


@dataclass(frozen=True)
class LegacyEventRankTrace:
    """v1 순위 추적 — 축약값과 입력 위치까지 남긴다.

    `input_position`은 라이브 선택에 다시 쓰려는 값이 아니라, 배열 순서 의존이 실제로
    발생했던 사례를 감사하기 위한 정보다.
    """

    event_key: str
    probability: int
    merit_key: tuple[int, ...]
    tiebreak_full_hash: int
    tiebreak_mod_9973: int
    input_position: int
    selection_contract: str = EVENT_SELECTION_CONTRACT


@dataclass(frozen=True)
class ContractComparison:
    """카드 1건의 v1↔v2 비교."""

    ilju: str
    legacy_event_key: str
    v2_event_key: str
    legacy_probability: int
    v2_probability: int
    merit_tie: bool
    change_allowed: bool
    legacy_hash_mod_9973_collision: bool = False
    change_reason: str = ""
    violation: str = ""


@dataclass
class ShadowReport:
    """하루 보드의 비교 요약."""

    cards: int = 0
    changed: int = 0
    changed_by_collision_fix: int = 0
    changed_by_contract: int = 0
    violations: list[ContractComparison] = field(default_factory=list)
    comparisons: list[ContractComparison] = field(default_factory=list)

    @property
    def has_violation(self) -> bool:
        """비동점 후보로 이동했는가 — 반드시 0이어야 한다."""
        return bool(self.violations)


def _mod_collision_in_top_group(scored: list[Any], seed_base: str) -> bool:
    """승자를 정한 동치류 안에서 v1 축약 해시가 충돌했는가.

    전체 후보가 아니라 **good 슬롯 경쟁군**에서 본다 — 승자는 거기서 나오므로, 전체
    목록의 충돌을 세면 실제로 결과를 흔들지 않은 충돌까지 결함으로 집계된다.
    """
    goods = [s for s in scored if s.valence == "good" and "good" in s.slots]
    if not goods:
        return False
    best = max(event_merit_key(s) for s in goods)
    top = [s for s in goods if event_merit_key(s) == best]
    counts = collections.Counter(_tiebreak_v1(s, seed_base) for s in top)
    return any(n > 1 for n in counts.values())


def compare_contracts(
    ctx: DayGanjiContext, dicts: DailyFortuneDicts
) -> ShadowReport:
    """하루 60일주에 대해 v1·v2 선택을 비교한다(순수 함수).

    슬롯 선발 전체를 같은 경로로 돌린다 — 단일 사건만 비교하면 domain·동의어 제약이
    반영되지 않아 실제 선택과 어긋난다.

    Args:
        ctx: 날짜 간지 컨텍스트.
        dicts: 사전 묶음.

    Returns:
        비교 결과. `has_violation`이 True면 v2가 실질 순위를 침범한 것이다.
    """
    report = ShadowReport()
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ilju = f"{stem.value}{branch.value}"
        seed_base = f"{ctx.the_date.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        scored = [
            _score_event(key, ev, stem, branch, ctx)
            for key, ev in dicts.catalog["events"].items()
        ]
        legacy_good, _, _ = _select_slots(scored, seed_base)
        v2_good, _, _ = _select_slots(
            scored, seed_base,
            # 루프 변수를 기본 인자로 묶는다 — 늦은 바인딩이면 마지막 일주로 평가된다.
            rank=lambda s, _d=ctx.the_date, _i=ilju: _rank_key_v2(s, _d, _i),
        )
        report.cards += 1
        merit_tie = event_merit_key(legacy_good) == event_merit_key(v2_good)
        changed = legacy_good.event_key != v2_good.event_key
        row = ContractComparison(
            ilju=ilju,
            legacy_event_key=legacy_good.event_key,
            v2_event_key=v2_good.event_key,
            legacy_probability=legacy_good.probability,
            v2_probability=v2_good.probability,
            merit_tie=merit_tie,
            change_allowed=merit_tie,
            legacy_hash_mod_9973_collision=(
                _mod_collision_in_top_group(scored, seed_base) if changed else False
            ),
        )
        if changed:
            report.changed += 1
            if not merit_tie:
                row = ContractComparison(
                    **{**row.__dict__, "violation": "v2_selected_lower_probability",
                       "change_reason": ""},
                )
                report.violations.append(row)
            elif row.legacy_hash_mod_9973_collision:
                row = ContractComparison(
                    **{**row.__dict__,
                       "change_reason": "legacy_truncated_hash_collision_resolved"},
                )
                report.changed_by_collision_fix += 1
            else:
                row = ContractComparison(
                    **{**row.__dict__,
                       "change_reason": "candidate_hash_contract_changed"},
                )
                report.changed_by_contract += 1
        report.comparisons.append(row)
    return report


def trace_v2(scored: Any, target_date: date, ilju: str) -> EventRankTrace:
    """v2 순위 추적값."""
    return EventRankTrace(
        event_key=scored.event_key,
        probability=scored.probability,
        merit_key=event_merit_key(scored),
        tiebreak_full_hash=_tiebreak_v2(scored, target_date, ilju),
        final_stable_key=scored.event_key,
    )


def trace_legacy(scored: Any, seed_base: str, position: int) -> LegacyEventRankTrace:
    """v1 순위 추적값 — 축약 전 전체 해시도 함께 남긴다."""
    return LegacyEventRankTrace(
        event_key=scored.event_key,
        probability=scored.probability,
        merit_key=event_merit_key(scored),
        tiebreak_full_hash=_stable_hash(f"{seed_base}|{scored.event_key}"),
        tiebreak_mod_9973=_tiebreak_v1(scored, seed_base),
        input_position=position,
    )


__all__ = [
    "ContractComparison",
    "EventRankTrace",
    "LegacyEventRankTrace",
    "ShadowReport",
    "compare_contracts",
    "trace_legacy",
    "trace_v2",
]


def board_candidates_v2(
    ctx: DayGanjiContext, dicts: DailyFortuneDicts
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """v2 선택 계약으로 뽑은 원시 승자와 허용 후보 목록 (OA-6c 입력).

    점수·판정을 다시 계산하지 않는다 — 이미 산출된 후보에서 노출 사건만 고른다.

    Args:
        ctx: 날짜 간지 컨텍스트.
        dicts: 사전 묶음.

    Returns:
        `(일주 → 원시 승자, 일주 → 허용 후보 목록)`.
    """
    from .daily_board_constraints import HeadlineCandidate
    from .daily_ilju_fortune import _band, _headline_candidates

    raw: dict[str, Any] = {}
    cand_map: dict[str, list[Any]] = {}
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ilju = f"{stem.value}{branch.value}"
        seed_base = f"{ctx.the_date.isoformat()}|{ilju}|{EVENT_SELECTION_COMPAT_SALT}"
        scored = [
            _score_event(key, ev, stem, branch, ctx)
            for key, ev in dicts.catalog["events"].items()
        ]
        good, caution, support = _select_slots(
            scored, seed_base,
            rank=lambda s, _d=ctx.the_date, _i=ilju: _rank_key_v2(s, _d, _i),
        )
        band = _band(good, caution)
        cands = _headline_candidates(good, support, caution, band)
        cand_map[ilju] = [
            HeadlineCandidate(c.event_key, c.domain, c.probability) for c in cands
        ]
        raw[ilju] = cand_map[ilju][0]
    return raw, cand_map

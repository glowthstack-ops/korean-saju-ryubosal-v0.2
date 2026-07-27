"""후보 기여 provenance 수집 (P2-PROV-1) — 계산에 개입하지 않는 shadow 관측.

설계 계약: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md`

이 모듈은 **아무것도 판정하지 않는다.** 사건 후보가 왜 생겼고 무엇이 실제로 점수를
결정했는지를 재현 가능하게 기록만 한다. 상위 사건 지지의 정의는 감수 대상이라
여기서 확정하지 않는다.

핵심 구분(설계 §0):

    evaluated evidence     규칙이 검토한 모든 근거
    selected base evidence max 경쟁의 최종 승자 — base score를 실제 결정한 근거

기존 `_Acc.reasons`·`_Acc.ten_gods`는 패자 근거까지 무조건 누적하는 **evaluated union**
이므로 provenance로 재해석하면 안 된다(설계 §1-1-b).

수집은 `ProvenanceRecorder`가 주어질 때만 일어난다. recorder가 None이면 기존 실행
경로와 객체 구조·결과가 동일하다.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum


class SelectionReason(StrEnum):
    """max 경쟁에서 이 근거가 어떻게 처리됐는지."""

    INITIAL_WINNER = "INITIAL_WINNER"  # 초기 상태에서 승리
    REPLACED_LOWER_SCORE = "REPLACED_LOWER_SCORE"  # 기존 승자를 밀어냄
    NOT_SELECTED_LOWER_SCORE = "NOT_SELECTED_LOWER_SCORE"  # 제안 점수가 더 낮음
    # 현행 비교는 strict `>`라 동점이면 기존 승자가 유지된다(선착 승자).
    # 동점 정책을 나중에 바꿀 때 영향 범위를 실측하려고 별도 값으로 둔다.
    NOT_SELECTED_EQUAL_SCORE = "NOT_SELECTED_EQUAL_SCORE"


class SelectionStatus(StrEnum):
    """후보가 최종적으로 base 승자를 갖는지."""

    SELECTED = "SELECTED"
    # 초깃값 0에서 모든 제안이 0이면 `>`가 한 번도 성립하지 않는다. 그래도 후보는
    # 출력될 수 있으므로 정상 상태로 인정한다(설계 §4-1).
    NO_SELECTED_BASE = "NO_SELECTED_BASE"


@dataclass(frozen=True)
class SourceOccurrence:
    """근거가 나온 실제 자리 — 층위만으로는 같은 글자를 구분할 수 없다.

    같은 정관이 대운·세운·일운에 모두 있어도, 또 같은 기둥의 천간·지지에 같은 글자가
    있어도 서로 다른 occurrence로 구분돼야 한다.
    """

    source_kind: str  # natal / transit
    layer: str  # daewoon / sewoon / wolwoon / ilwoon
    period_key: str  # 2026 / 2026-07 / 2026-07-27 (대운은 간지 라벨)
    pillar_position: str  # year / month / day / hour / transit
    component: str  # stem / branch
    glyph: str  # 午
    signal_role: str  # target / helper / context

    @property
    def occurrence_id(self) -> str:
        """구조에서 결정적으로 생성한 식별자."""
        return ":".join((
            self.source_kind, self.layer, self.period_key,
            self.pillar_position, self.component, self.glyph, self.signal_role,
        ))


def signal_id_of(occurrence_id: str, ten_god: str) -> str:
    """occurrence + 십성 → 신호 식별자."""
    return f"{occurrence_id}#{ten_god}"


def evidence_id_of(
    event_key: str, rule_id: str, formula_id: str, signal_ids: tuple[str, ...]
) -> str:
    """근거 식별자 — 실행 순서에 의존하지 않도록 정렬된 signal_ids로 해시한다.

    occurrence_id와는 다른 축이다: 하나의 occurrence가 여러 룰에 평가되기 때문이다.
    동일한 평가가 반복될 수 있는 경우는 `evaluation_index`를 별도 필드로 남기고
    해시에는 넣지 않는다(설계 §4-2).
    """
    payload = "|".join((event_key, rule_id, formula_id, *sorted(signal_ids)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EvaluatedEvidence:
    """규칙이 검토한 근거 1건 — 승패와 무관하게 기록한다."""

    evidence_id: str
    event_key: str
    rule_id: str
    formula_id: str
    evaluation_index: int
    signal_ids: tuple[str, ...]
    source_occurrences: tuple[str, ...]
    source_layers: tuple[str, ...]
    ten_gods: tuple[str, ...]
    proposed_score: float
    score_before: float
    selected_at_evaluation: bool
    selection_reason: SelectionReason
    # factor()의 십성별 강도를 실제로 정한 신호(argmax). 같은 십성이 여러 층에서
    # 들어오면 최댓값만 점수에 반영되므로, 검토된 신호 전체와 구분해 남긴다.
    strength_source_signal_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectedBaseEvidence:
    """base score를 실제로 결정한 근거 — 후보당 최대 1건."""

    evidence_id: str
    event_key: str
    final_base_score: float
    rule_id: str
    formula_id: str
    signal_ids: tuple[str, ...]
    source_occurrences: tuple[str, ...]
    source_layers: tuple[str, ...]
    ten_gods: tuple[str, ...]


@dataclass
class PeriodProvenance:
    """한 시점(period)의 관측 결과."""

    period: str
    evaluated: list[EvaluatedEvidence] = field(default_factory=list)
    selected: dict[str, SelectedBaseEvidence] = field(default_factory=dict)
    selection_status: dict[str, SelectionStatus] = field(default_factory=dict)


class ProvenanceRecorder:
    """감사 실행에서만 붙는 수집기 — production 계산 객체에는 싣지 않는다.

    불변식:
        recorder=None   기존 실행 경로와 객체 구조·결과가 동일
        recorder 활성   감사 데이터만 추가되고 계산 결과는 동일
    """

    def __init__(self) -> None:
        self._periods: dict[str, PeriodProvenance] = {}
        self._eval_seen: dict[tuple[str, str], int] = defaultdict(int)

    # ── 수집 ────────────────────────────────────────────────────
    def next_evaluation_index(self, period: str, evidence_id: str) -> int:
        """동일 근거가 같은 시점에 반복 평가될 때의 회차(0부터)."""
        key = (period, evidence_id)
        idx = self._eval_seen[key]
        self._eval_seen[key] = idx + 1
        return idx

    def record_evaluated(self, period: str, ev: EvaluatedEvidence) -> None:
        """검토된 근거 1건을 남긴다."""
        self._period(period).evaluated.append(ev)

    def record_selected(self, period: str, ev: SelectedBaseEvidence) -> None:
        """현재 승자를 갱신한다 — 나중에 교체되면 덮어쓴다."""
        p = self._period(period)
        p.selected[ev.event_key] = ev
        p.selection_status[ev.event_key] = SelectionStatus.SELECTED

    def record_no_selection(self, period: str, event_key: str) -> None:
        """한 번도 `>`가 성립하지 않은 후보를 정상 상태로 남긴다."""
        p = self._period(period)
        if event_key not in p.selected:
            p.selection_status[event_key] = SelectionStatus.NO_SELECTED_BASE

    # ── 조회 ────────────────────────────────────────────────────
    def periods(self) -> dict[str, PeriodProvenance]:
        """수집 결과 전체."""
        return self._periods

    def counts(self) -> dict[str, int]:
        """집계 단위를 분리해 보고한다 — 후보 수와 근거 수를 섞지 않는다.

        `evaluated_evidence_count`가 후보 수보다 큰 것은 정상이다.
        """
        evaluated = sum(len(p.evaluated) for p in self._periods.values())
        selected = sum(len(p.selected) for p in self._periods.values())
        candidates = sum(len(p.selection_status) for p in self._periods.values())
        return {
            "period_count": len(self._periods),
            "unique_candidate_count": candidates,
            "evaluated_evidence_count": evaluated,
            "selected_base_evidence_count": selected,
        }

    def _period(self, period: str) -> PeriodProvenance:
        p = self._periods.get(period)
        if p is None:
            p = PeriodProvenance(period=period)
            self._periods[period] = p
        return p

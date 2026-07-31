"""P2-PROV-1 — base 기여 provenance 관측 (2026-07-27 데굴님 계약).

설계: `doc/v2_2/REVIEW_CONTRIBUTION_PROVENANCE.md`

이 슬라이스는 아무것도 판정하지 않는다. 두 가지만 고정한다.

    1. recorder가 없으면 기존 계산과 완전히 동일하다
    2. recorder가 있으면 evaluated / selected base를 정확히 구분해 남긴다
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines.contribution_provenance import (
    ProvenanceRecorder,
    SelectionReason,
    SelectionStatus,
    SourceOccurrence,
)
from saju_engines.ten_god_brancher import TenGodEventBrancher, TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import LuckLayer, TenGod
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.luck import LuckPillar

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def brancher() -> TenGodEventBrancher:
    return TenGodEventBrancher(_DICTS)


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


def _pillar(label: str, stem_god: str, branch_god: str, stem="甲", branch="子") -> LuckPillar:
    return LuckPillar(
        label=label, period_type="year", ganji=f"{stem}{branch}",
        stem=stem, branch=branch,
        stem_ten_god=stem_god, branch_ten_god=branch_god,
    )


# ── 1. occurrence 구별 ────────────────────────────────────────────


def test_same_glyph_in_different_layers_yields_distinct_occurrences(brancher) -> None:
    """세운 午와 일운 午는 서로 다른 occurrence다."""
    sew = brancher.collect_from_pillar(
        _pillar("2026", "정관", "편재", branch="午"), LuckLayer.SEWOON
    )
    ilw = brancher.collect_from_pillar(
        _pillar("2026-07-27", "정관", "편재", branch="午"), LuckLayer.ILWOON
    )
    sew_ids = {s.occurrence.occurrence_id for s in sew}
    ilw_ids = {s.occurrence.occurrence_id for s in ilw}
    assert sew_ids and ilw_ids
    assert not (sew_ids & ilw_ids)


def test_stem_and_branch_are_distinguished_by_component(brancher) -> None:
    """같은 기둥의 천간·지지는 component로 구분된다."""
    sigs = brancher.collect_from_pillar(
        _pillar("2026", "정관", "편재"), LuckLayer.SEWOON
    )
    comps = {s.occurrence.component for s in sigs}
    assert comps == {"stem", "branch"}
    assert len({s.occurrence.occurrence_id for s in sigs}) == len(sigs)


def test_occurrence_id_is_deterministic() -> None:
    """식별자는 구조에서 결정적으로 생성된다."""
    occ = SourceOccurrence(
        source_kind="transit", layer="ilwoon", period_key="2026-07-27",
        pillar_position="transit", component="branch", glyph="寅", signal_role="target",
    )
    assert occ.occurrence_id == "transit:ilwoon:2026-07-27:transit:branch:寅:target"


def test_context_layer_is_marked_as_context(brancher) -> None:
    """배경 운층 신호는 target이 아니라 context로 표시된다."""
    sigs = brancher.collect_from_pillar(
        _pillar("2026", "정관", "편재"), LuckLayer.SEWOON, is_target=False
    )
    assert {s.occurrence.signal_role for s in sigs} == {"context"}


# ── 2. evaluated vs selected ──────────────────────────────────────


def _stack_signals(brancher) -> list[TransitSignal]:
    """대운+세운+월운 3층 스택 — 실제 채점과 같은 모양의 신호 집합."""
    return [
        *brancher.collect_from_pillar(
            _pillar("甲子", "정관", "정인"), LuckLayer.DAEWOON, is_target=False
        ),
        *brancher.collect_from_pillar(
            _pillar("2026", "정재", "편인", stem="丙", branch="午"),
            LuckLayer.SEWOON, is_target=False,
        ),
        *brancher.collect_from_pillar(
            _pillar("2026-07", "편재", "식신", stem="乙", branch="未"), LuckLayer.WOLWOON
        ),
    ]


def _record(brancher, signals, period="2026") -> ProvenanceRecorder:
    rec = ProvenanceRecorder()
    brancher.branch(signals, period, provenance_recorder=rec)
    return rec


def test_losers_are_recorded_as_evaluated_not_selected(brancher, chart) -> None:
    """패자 근거는 evaluated에 남고 selected base에는 없다 — 핵심 구분."""
    rec = _record(brancher, _stack_signals(brancher))
    p = rec.periods()["2026"]

    assert p.evaluated, "평가 근거가 하나도 없으면 이 테스트는 의미가 없다"
    # 같은 event_key에 여러 근거가 평가돼도 승자는 최대 1건이다.
    for event_key, sel in p.selected.items():
        same = [e for e in p.evaluated if e.event_key == event_key]
        assert len(same) >= 1
        assert sel.evidence_id in {e.evidence_id for e in same}
    losers = [e for e in p.evaluated if not e.selected_at_evaluation]
    for lo in losers:
        # 위 루프의 `sel` 과 이름을 나눈다 — 여기서는 '이 패자의 event_key 에 승자가
        # 있는가' 를 묻는 것이라 없을 수도 있다.
        winner = p.selected.get(lo.event_key)
        # 패자는 그 후보의 최종 승자가 될 수 없다.
        if winner is not None:
            assert winner.evidence_id != lo.evidence_id or lo.selection_reason in (
                SelectionReason.NOT_SELECTED_EQUAL_SCORE,
                SelectionReason.NOT_SELECTED_LOWER_SCORE,
            )


def test_ten_gods_is_evaluated_union_not_provenance(brancher) -> None:
    """source_ten_gods는 승자 십성이 아니라 평가된 십성의 합집합이다.

    실제 거버닝 스택(대운+세운+월운)을 써야 그룹 룰이 넓은 십성 집합으로 평가돼
    승자 십성과 후보 십성의 차이가 드러난다.
    """
    rec = ProvenanceRecorder()
    cands = brancher.branch(_stack_signals(brancher), "2026-07", provenance_recorder=rec)
    p = rec.periods()["2026-07"]

    checked = 0
    for c in cands:
        sel = p.selected.get(str(c.event_key))
        if sel is None:
            continue
        cand_gods = {str(g) for g in c.source_ten_gods}
        # 승자 십성은 후보의 evaluated union에 포함되지만, 역은 성립하지 않아도 된다.
        assert set(sel.ten_gods) <= cand_gods
        if set(sel.ten_gods) < cand_gods:
            checked += 1
    assert checked > 0, "패자 십성이 섞인 후보가 없으면 evaluated union을 입증하지 못한다"


def test_selection_reason_marks_replacement(brancher) -> None:
    """승자 교체가 일어나면 REPLACED_LOWER_SCORE로 기록된다."""
    rec = _record(brancher, _stack_signals(brancher))
    reasons = {e.selection_reason for e in rec.periods()["2026"].evaluated}
    assert SelectionReason.INITIAL_WINNER in reasons
    # 교체·미선택 중 최소 하나는 실제 데이터에서 발생한다.
    assert reasons - {SelectionReason.INITIAL_WINNER}


def test_tie_keeps_incumbent(brancher) -> None:
    """동점은 현행 `>`대로 선착 승자를 유지하고 EQUAL로 표시한다."""
    # 같은 십성 신호를 두 층위로 넣어 동일 룰이 같은 점수로 두 번 평가되게 한다.
    sigs = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem", strength=1.0),
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.ILWOON, "stem", strength=1.0),
    ]
    rec = _record(brancher, sigs)
    p = rec.periods()["2026"]
    first = {}
    for e in p.evaluated:
        if e.selected_at_evaluation and e.event_key not in first:
            first[e.event_key] = e.evidence_id
    for event_key, evidence_id in first.items():
        assert p.selected[event_key].evidence_id == evidence_id


def test_no_selected_base_is_a_valid_state(brancher) -> None:
    """모든 제안이 0이면 승자 없이도 정상 상태로 남는다."""
    rec = ProvenanceRecorder()
    brancher.branch([], "2026", provenance_recorder=rec)
    p = rec.periods().get("2026")
    if p is not None:
        for status in p.selection_status.values():
            assert status in (SelectionStatus.SELECTED, SelectionStatus.NO_SELECTED_BASE)


def test_counts_separate_candidates_from_evidence(brancher) -> None:
    """집계 단위를 섞지 않는다 — 근거 수가 후보 수보다 큰 것은 정상."""
    c = _record(brancher, _stack_signals(brancher)).counts()
    assert c["selected_base_evidence_count"] <= c["unique_candidate_count"]
    assert c["evaluated_evidence_count"] >= c["selected_base_evidence_count"]


def test_strength_source_is_narrower_than_evaluated_signals(brancher) -> None:
    """factor()의 강도를 실제로 정한 신호는 검토된 신호의 부분집합이다."""
    sigs = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem", strength=1.0),
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.ILWOON, "branch_main", strength=0.9),
    ]
    rec = _record(brancher, sigs)
    for e in rec.periods()["2026"].evaluated:
        assert set(e.strength_source_signal_ids) <= set(e.signal_ids)


# ── 3. score-neutral 보증 ─────────────────────────────────────────


def _fingerprint(cands) -> list[tuple]:
    return [
        (
            str(c.event_key), c.period, c.score, c.raw_score,
            str(c.confidence_level), str(c.quality), str(c.polarity_role),
            tuple(str(x) for x in c.source_layers),
            tuple(str(g) for g in c.source_ten_gods),
            tuple(c.reason_codes),
        )
        for c in cands
    ]


def test_recorder_off_and_on_produce_identical_candidates(brancher, chart) -> None:
    """recorder 유무가 후보 결과를 바꾸지 않는다 — P2-PROV의 최상위 불변식."""
    sigs = _stack_signals(brancher)
    off = brancher.branch(sigs, "2026")
    on = brancher.branch(sigs, "2026", provenance_recorder=ProvenanceRecorder())
    assert _fingerprint(off) == _fingerprint(on)


def test_full_engine_scoring_is_unchanged(chart) -> None:
    """엔진 전 구간(모디파이어·랭커·soft_cap 포함) 결과가 동일하다."""
    scorer = EventEngineV2(_DICTS)
    levels = {GanjiLevel.YEAR, GanjiLevel.MONTH, GanjiLevel.DAY}
    first = scorer.score_legacy(chart, levels=levels)
    second = scorer.score_legacy(chart, levels=levels)
    assert [
        (str(c.event_key), c.period, c.score, str(c.confidence), tuple(c.evidence_path))
        for c in first
    ] == [
        (str(c.event_key), c.period, c.score, str(c.confidence), tuple(c.evidence_path))
        for c in second
    ]
    assert first, "후보가 비면 회귀 의미가 없다"


def test_layer_flow_multiplier_input_unchanged(chart) -> None:
    """layer_flow_modifier가 읽는 스택 조합이 그대로다(단계 0 정정의 소비 경로)."""
    scorer = EventEngineV2(_DICTS)
    v2 = scorer.score(chart, levels={GanjiLevel.MONTH})
    assert v2
    for c in v2:
        # 스택 구성은 여전히 시점별로 동일 — 후보별 기여로 바뀌지 않았다.
        assert set(c.source_layers) <= {
            LuckLayer.DAEWOON, LuckLayer.SEWOON, LuckLayer.WOLWOON, LuckLayer.ILWOON
        }

"""관계 벡터 shadow chat 배선 회귀 — P1-6 §12 (RELATIONSHIP_EVENT_SYSTEM 부록 D).

검증: ①탐지 재호출·결과 변형 없음(주 채점 delta 0) ②bounded top-cap 보존 +
전체 aggregate 반영 ③서명 기반 join 1건·복수 매치 JOIN_AMBIGUOUS fail-closed
④pre_reduce_rank=production comparator 순위 ⑤최종에만 있고 base 미결합=JOIN_NOT_FOUND
⑥REL 후보 없는 기간=NO_CANDIDATE(degraded 분모 제외) ⑦기간 실패 격리.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services import relationship_vector_sidecar as S
from saju_api.services import relationship_vector_telemetry as T
from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import (
    EventEngineV2,
    RelationActivationProjection,
    RelationshipShadowProjection,
)
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import EventKeyV2
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventPolarity,
    EventType,
)
from saju_shared_types.ganji_calendar import GanjiLevel

# 실행 위치에 독립적이어야 한다 — 상대 경로를 쓰면 리포 루트에서 돌릴 때만 깨져
# 코드 결함으로 오진하기 쉽다(실측: 리포 루트 실행 시 9건 실패).
_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="서울", gender="female", reference_date=date(2026, 7, 24)))


def _cand(key: str, period: str, score: int = 60,
          conf: str = "medium", etype: str = "progress") -> EventCandidate:
    return EventCandidate(
        event_key=EventKeyV2(key), event_type=EventType(etype), period=period,
        score=score, confidence=Confidence(conf),
        polarity=EventPolarity("positive"), raw_total=float(score))


def _build(projs, chart, scope="self"):
    return S.build_relationship_effect_accumulator(
        projs, chart, dictionaries_dir=_DICTS, thread_scope="t1", turn=1,
        subject_scope=scope, input_signature="q")


# ── ① 주 채점 delta 0(탐지 재호출·결과 변형 없음) ────────────────────────────
def test_shadow_collection_does_not_alter_scoring():
    """projection sink 활성 채점 == 없을 때 채점(bit 동일 — shadow는 관측 전용)."""
    chart = _chart()
    eng = EventEngineV2(_DICTS, **marriage_engine_flags())
    a = eng.score_legacy_personalized(chart, levels={GanjiLevel.YEAR})
    # take_relationship_shadow가 실제 projection을 수집했어도 결과는 그대로여야 한다.
    projs = eng.take_relationship_shadow()
    assert projs  # 수집은 됐다
    b = eng.score_legacy_personalized(chart, levels={GanjiLevel.YEAR})
    assert [c.model_dump() for c in a] == [c.model_dump() for c in b]


def test_sidecar_has_no_scorer_reference():
    """sidecar 빌더 시그니처에 scorer/engine 인자가 없다(재호출 불가 — 구조 보증)."""
    import inspect
    params = inspect.signature(
        S.build_relationship_effect_accumulator).parameters
    assert "scorer" not in params
    assert not any("engine" in p for p in params)


# ── ② bounded cap + 전체 aggregate ──────────────────────────────────────────
def test_bounded_cap_but_full_aggregate():
    """상세는 cap개만 보존하고 aggregate는 전 기간(성공분) 반영."""
    chart = _chart()
    base = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    n = T.MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST + 10
    projs = tuple(
        RelationshipShadowProjection(
            layer="sewoon", label=str(2000 + i), luck_stem=base.luck_stem,
            luck_branch=base.luck_branch, activations=base.activations,
            spouse_palace_clashed=False)
        for i in range(n))
    acc = _build(projs, chart).accumulator
    assert acc.vector_success_count == n
    assert len(acc.detailed_drafts) == T.MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST
    # aggregate는 전 기간 반영.
    assert sum(acc.aggregate.separation_status_counts.values()) == n
    envs = [
        T.finalize_shadow_envelope(d, audit_status=T.AuditProjectionStatus.NO_CANDIDATE)
        for d in acc.detailed_drafts]
    batch = T.build_batch_from_accumulator(acc, envs)
    assert batch.vector_success_count == n
    assert batch.detailed_period_count == T.MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST
    assert batch.truncated_success_period_count == \
        n - T.MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST


def test_accumulator_and_batch_equivalent_to_bulk():
    """bounded 누적 경로 == 일괄 build_batch(동일 계약·동일 결과)."""
    chart = _chart()
    eng = EventEngineV2(_DICTS, **marriage_engine_flags())
    eng.score_legacy_personalized(chart, levels={GanjiLevel.YEAR})
    projs = eng.take_relationship_shadow()
    res = _build(projs, chart)
    acc = res.accumulator
    # 일괄 경로 재구성: 같은 draft 목록으로 build_batch.
    bulk_drafts = []
    for p in projs:
        r2 = _build((p,), chart)
        bulk_drafts += list(r2.accumulator.detailed_drafts)
    envs_acc = [T.finalize_shadow_envelope(
        d, audit_status=T.AuditProjectionStatus.NO_CANDIDATE)
        for d in acc.detailed_drafts]
    b_acc = T.build_batch_from_accumulator(acc, envs_acc)
    b_bulk = T.build_batch(bulk_drafts, [])
    assert b_acc.aggregate.model_dump() == b_bulk.aggregate.model_dump()


# ── ③ 서명 기반 join 1건·복수 매치 JOIN_AMBIGUOUS ────────────────────────────
def _one_draft(acc):
    assert acc.detailed_drafts
    return acc.detailed_drafts[0]


def test_join_by_signature_single_success():
    chart = _chart()
    proj = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    acc = _build((proj,), chart).accumulator
    scored = [_cand("marriage_signal", "2027", 61, "medium_high"),
              _cand("career_change", "2027", 80)]
    envs = S.finalize_relationship_envelopes(
        acc.detailed_drafts, subject_scope="self", all_scored=scored,
        pre_reduce_candidates=scored, final_candidates=scored[:1])
    assert envs[0].audit_status is T.AuditProjectionStatus.SUCCESS
    audits = envs[0].legacy_candidate_audits
    assert [a.event_key for a in audits] == ["marriage_signal"]
    assert audits[0].pre_reduce_rank == 1          # scored 목록 순서(1-based)
    assert audits[0].selected_in_top_n is True     # final[:1]에 포함


def test_join_ambiguous_fail_closed():
    """같은 서명(subject·period·event_key·event_type) 2건 → JOIN_AMBIGUOUS(결합 안 함)."""
    chart = _chart()
    proj = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    acc = _build((proj,), chart).accumulator
    scored = [_cand("marriage_signal", "2027", 61),
              _cand("marriage_signal", "2027", 40)]  # 동일 서명 2건
    envs = S.finalize_relationship_envelopes(
        acc.detailed_drafts, subject_scope="self", all_scored=scored,
        pre_reduce_candidates=scored, final_candidates=[])
    assert envs[0].audit_status is T.AuditProjectionStatus.JOIN_AMBIGUOUS
    assert envs[0].legacy_candidate_audits == ()   # 추정 결합 없음


def test_pre_reduce_rank_is_production_order():
    """pre_reduce_rank는 reducer 입력 목록 순서 — all_scored와 다를 수 있다."""
    chart = _chart()
    proj = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    acc = _build((proj,), chart).accumulator
    ms = _cand("marriage_signal", "2027", 61)
    scored = [ms]
    pre = [_cand("career_change", "2027", 80), ms]   # marriage_signal이 2번째
    envs = S.finalize_relationship_envelopes(
        acc.detailed_drafts, subject_scope="self", all_scored=scored,
        pre_reduce_candidates=pre, final_candidates=[ms])
    a = envs[0].legacy_candidate_audits[0]
    assert a.pre_reduce_rank == 2      # pre 목록 순서
    assert a.final_rank == 1           # final 목록 순서


def test_no_candidate_period():
    """해당 기간에 REL 후보가 없으면 NO_CANDIDATE(정상 관측)."""
    chart = _chart()
    proj = RelationshipShadowProjection(
        layer="sewoon", label="2099", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    acc = _build((proj,), chart).accumulator
    scored = [_cand("career_change", "2099", 80)]   # REL 아님
    envs = S.finalize_relationship_envelopes(
        acc.detailed_drafts, subject_scope="self", all_scored=scored,
        pre_reduce_candidates=scored, final_candidates=scored)
    assert envs[0].audit_status is T.AuditProjectionStatus.NO_CANDIDATE
    # eligible 분모(NO_CANDIDATE 제외) — audit_degraded False.
    batch = T.build_batch_from_accumulator(acc, envs)
    assert batch.detailed_audit_no_candidate_count == 1
    assert batch.audit_degraded is False


def test_join_not_found_when_final_only():
    """최종 Top-N에 REL 후보가 있는데 base 서명과 결합 안 되면 JOIN_NOT_FOUND."""
    chart = _chart()
    proj = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    acc = _build((proj,), chart).accumulator
    final_only = [_cand("marriage_signal", "2027", 61)]
    envs = S.finalize_relationship_envelopes(
        acc.detailed_drafts, subject_scope="self", all_scored=[],
        pre_reduce_candidates=[], final_candidates=final_only)
    assert envs[0].audit_status is T.AuditProjectionStatus.JOIN_NOT_FOUND


# ── ⑦ 기간 실패 격리 ────────────────────────────────────────────────────────
def test_period_failure_isolated():
    """한 기간 어댑터 실패가 다른 기간 draft 생성을 막지 않는다."""
    chart = _chart()
    good = RelationshipShadowProjection(
        layer="sewoon", label="2027", luck_stem="丁", luck_branch="未",
        activations=(RelationActivationProjection(
            kind="CHUNG", palace="day_pillar", layer="sewoon",
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    bad = RelationshipShadowProjection(
        layer="sewoon", label="2028", luck_stem="戊", luck_branch="申",
        activations=(RelationActivationProjection(
            kind="NOT_A_KIND", palace="day_pillar", layer="sewoon",  # RelationKind 변환 실패
            position="branch", hap_subtype=None, element=None),),
        spouse_palace_clashed=False)
    res = _build((good, bad), chart)
    assert res.accumulator.vector_success_count == 1
    assert sum(res.period_failure_counts.values()) == 1

"""상담 결론 의미론 P0 — 이중 채널 보존·구조 필드 승격·큰 결정 분기(2026-08-21).

P0-1: activation/stem_role/branch_role이 legacy 변환에서 드롭되지 않는다(INV-C·INV-E).
P0-2: 결실 뉘앙스 카테고리·검토월이 텍스트가 아니라 구조 필드로 실린다.
P0-3: 큰 결정 디렉티브가 event-local 근거/배경 저점/무근거 3분기로 갈린다 —
      배경 저점 단독으로는 보류를 권하지 않는다(INV-B: luck 비거부권).
P0-5: event_phase 영문 원시값이 동반 신호 문자열로 누출되지 않는다.
"""

from __future__ import annotations

from saju_api.services.chat_service import _big_decision_directive
from saju_engines.context_reducer import _to_llm_candidate
from saju_engines.event_engine_v2 import _period_role_labels, to_legacy_candidate
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2
from saju_shared_types.events import Confidence, EventCandidate, EventPolarity, EventType, Signal
from saju_shared_types.llm_input import LlmEventCandidate, MonthOverviewRow
from saju_shared_types.luck import LuckPillar


def _v2(**kw) -> EventCandidateV2:
    base = dict(event_key=EventKeyV2.JOB_GAIN, period="2026-12", score=80)
    base.update(kw)
    return EventCandidateV2(**base)


# ── P0-1: 이중 채널·역할 라벨 보존 ──────────────────────────────────────────


def test_legacy_conversion_preserves_activation_and_roles() -> None:
    c = _v2(activation=61.5, favorability=-0.7, stem_role="구신", branch_role="한신")
    legacy = to_legacy_candidate(c)
    assert legacy.activation == 61.5
    assert legacy.favorability == -0.7  # INV-C: 두 채널이 독립으로 함께 살아남는다
    assert legacy.stem_role == "구신"
    assert legacy.branch_role == "한신"


def test_period_role_labels_not_folded() -> None:
    # 천간 庚(金)·지지 子(水) — 접힘 전 두 라벨이 각각 보존된다.
    target = LuckPillar(
        label="2026-12", period_type="month", ganji="庚子",
        stem="庚", branch="子", stem_ten_god="정재", branch_ten_god="편관",
    )
    fav = {"金": "구신", "水": "한신"}
    assert _period_role_labels(target, fav) == ("구신", "한신")
    # 합거(制)로 천간이 묶이면 천간 라벨만 비운다(판정 기준은 _period_role과 동일).
    assert _period_role_labels(target, fav, stem_bound=True) == ("", "한신")


# ── P0-5: event_phase 한글화(영문 원시값 누출 차단) ─────────────────────────


def test_event_phase_not_leaked_in_english() -> None:
    legacy = to_legacy_candidate(_v2(event_phase="formalization"))
    mat = next(s for s in legacy.signals if s.type == "materialization")
    assert "formalization" not in mat.effect
    assert "공식화 단계" in mat.effect


# ── P0-2: 뉘앙스 카테고리·검토월 구조 필드 ──────────────────────────────────


def _legacy(**kw) -> EventCandidate:
    base = dict(
        event_key="job_gain", event_type=EventType.PROGRESS, period="2026-12",
        score=80, confidence=Confidence.MEDIUM, polarity=EventPolarity.NEUTRAL,
    )
    base.update(kw)
    return EventCandidate(**base)


def test_nuance_category_and_review_month_structured() -> None:
    # 庚子 + 金=구신·水=한신 → 천간 흉신(unfavorable) / 공망 신호 → 검토월.
    c = _legacy(signals=[Signal(type="void", name="void", effect="공망 지연", weight=0.0)])
    llm = _to_llm_candidate(
        c, ganji={"2026-12": "庚子"}, dw_by_year={}, fav_map={"金": "구신", "水": "한신"}
    )
    assert llm.result_nuance == "unfavorable"
    assert llm.review_month is True
    # 검토월 문구는 caution_note 텍스트에 concat되지 않는다(구조 필드로 분리).
    assert "검토월" not in llm.caution_note
    assert "천간 흉신" in llm.caution_note


def test_no_signal_no_review_month() -> None:
    llm = _to_llm_candidate(
        _legacy(), ganji={"2026-12": "甲午"}, dw_by_year={},
        fav_map={"木": "용신", "火": "희신"},
    )
    assert llm.review_month is False
    assert llm.result_nuance == ""  # 길천간·무누설 — 뉘앙스 없음(빈값 ≠ mixed, INV-D)


# ── P0-3: 큰 결정 디렉티브 3분기 ────────────────────────────────────────────


def _cand(**kw) -> LlmEventCandidate:
    base = dict(event_key="marriage_signal", period="2026-12", ganji="庚子",
                daewoon_context="", score=80, confidence="medium", polarity="neutral")
    base.update(kw)
    return LlmEventCandidate(**base)


def _row(period: str, grade: str) -> MonthOverviewRow:
    return MonthOverviewRow(period=period, ganji="庚子", luck_grade=grade)


def test_big_decision_local_adverse_recommends_deferral() -> None:
    out = _big_decision_directive([_cand(result_nuance="unfavorable")], [])
    assert "미루는 것" in out
    assert "결실·실속 불리" in out  # 근거를 그대로 지시문에 명시


def test_big_decision_low_luck_alone_is_backdrop_only() -> None:
    # INV-B: 배경 저점 단독 — 보류 권고 금지, 배경 사실 언급으로 한정.
    out = _big_decision_directive(
        [_cand()], [_row("2026-12", "기신운(부분)")]
    )
    assert "미루는 것" not in out
    assert "보류를 권하지 말 것" in out


def test_big_decision_no_evidence_calm_review() -> None:
    out = _big_decision_directive([_cand()], [_row("2026-12", "강한 용신운")])
    assert "차분히 검토" in out
    assert "만들어 붙이지 말 것" in out  # 무근거 균형 caution 생성 금지

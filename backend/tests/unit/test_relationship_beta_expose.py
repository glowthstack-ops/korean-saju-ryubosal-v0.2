"""관계 신호 beta 노출(슬라이스 1) 회귀 — 플래그·3축·가드.

flag off면 관계 벡터가 shadow로 복귀(출력 무변경), flag on이면 관계 질문에 3축 beta
블록 주입. 미평가 4축은 노출하지 않는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_api.services.relationship_vector_sidecar import (
    RelationshipBetaSignal,
    build_relationship_beta_signals,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _projections_and_chart():
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="서울", gender="female", reference_date=date(2026, 7, 24)))
    eng = EventEngineV2(_DICTS, **marriage_engine_flags())
    eng.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
    return eng.take_relationship_shadow(), chart


def test_beta_signals_only_evaluated_activation():
    """평가된 activation 기간만 노출·3축만·간지 미노출."""
    projs, chart = _projections_and_chart()
    sig = build_relationship_beta_signals(projs, chart, dictionaries_dir=_DICTS)
    assert sig
    for s in sig:
        assert isinstance(s, RelationshipBetaSignal)
        assert s.activation_band in ("strong", "moderate", "weak", "low")
        assert s.stability_sign in (None, "favorable", "neutral", "adverse")
        # 3축 필드만 — 미평가 4축(exposure 등) 필드 자체가 없음.
        assert set(vars(s)) == {"layer", "label", "activation_band",
                                "stability_sign", "separation_band"}


def test_beta_signals_window_filter():
    """window 밖 기간은 제외."""
    projs, chart = _projections_and_chart()
    sig = build_relationship_beta_signals(
        projs, chart, dictionaries_dir=_DICTS, window=("2027", "2027"))
    assert all(s.label[:4] == "2027" for s in sig)


def test_beta_signals_capped_and_deduped():
    projs, chart = _projections_and_chart()
    sig = build_relationship_beta_signals(projs, chart, dictionaries_dir=_DICTS, cap=3)
    assert len(sig) <= 3
    assert len({s.label for s in sig}) == len(sig)   # 라벨 중복 없음


def test_beta_block_formatter():
    """3축 라벨 한글화 + beta 헤더."""
    sig = [RelationshipBetaSignal("sewoon", "2027", "strong", "adverse", "moderate"),
           RelationshipBetaSignal("sewoon", "2028", "moderate", None, None)]
    block = chat_service._relationship_beta_block(sig)
    assert block is not None
    assert "[관계 신호(beta)" in block
    assert "2027: 관계 활성 강 · 유지 우호도 불리 · 종료압력 중" in block
    assert "종료압력 관측 안 됨" in block   # 미평가 축은 '관측 안 됨'(0 아님)


def test_beta_block_empty_returns_none():
    assert chat_service._relationship_beta_block([]) is None


def test_beta_directive_has_no_determination():
    """가드 지시문에 단정 금지·성사 미판정·beta 라벨 문구 포함."""
    d = chat_service._RELATIONSHIP_BETA_DIRECTIVE
    assert "확정이 아니다" in d
    assert "단정하지" in d
    assert "성사" in d and "beta" in d


def test_report_relationship_section_beta_when_flag_on(monkeypatch):
    """플래그 on → 관계 도메인 리포트 섹션에 beta 블록 주입(슬라이스 2)."""
    from saju_api.services import relationship_shadow, report_service
    from saju_shared_types.intent import SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec
    monkeypatch.setattr(relationship_shadow, "RELATIONSHIP_BETA_EXPOSE", True)
    birth = BirthInput(calendar_type="solar", birth_date=date(1985, 3, 15),
                       birth_time="14:30", birth_place_name="서울", gender="female")
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(subject_id="self", label="본인", kind="self")],
        topic="relationship", period=ReportPeriod(start="2026", end="2031"))
    ctxs = report_service.plan_report(birth, spec, today=date(2026, 7, 24))
    beta = [c for c in ctxs if "[관계 인사이트(beta)" in (c.body_prompt or "")]
    assert beta, "관계 섹션에 beta 블록이 없음"
    # 미평가 축 문구(성사/공식화)는 판정으로 노출되지 않고 '판정하지 않는다'만.
    assert "확정이 아니며" in beta[0].body_prompt


def test_report_no_beta_when_flag_off(monkeypatch):
    """플래그 off → 리포트 무변경(beta 블록 없음)."""
    from saju_api.services import relationship_shadow, report_service
    from saju_shared_types.intent import SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec
    monkeypatch.setattr(relationship_shadow, "RELATIONSHIP_BETA_EXPOSE", False)
    birth = BirthInput(calendar_type="solar", birth_date=date(1985, 3, 15),
                       birth_time="14:30", birth_place_name="서울", gender="female")
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(subject_id="self", label="본인", kind="self")],
        topic="relationship", period=ReportPeriod(start="2026", end="2031"))
    ctxs = report_service.plan_report(birth, spec, today=date(2026, 7, 24))
    assert not any("[관계 인사이트(beta)" in (c.body_prompt or "") for c in ctxs)


def test_flag_default_off():
    """기본(env 미설정)은 off — shadow 복귀·기존 출력 불변."""
    import importlib

    from saju_api.services import relationship_shadow
    importlib.reload(relationship_shadow)
    # env 미설정 상태에서 기본 False(테스트 환경 기준).
    import os
    if not os.getenv("SAJU_RELATIONSHIP_BETA_EXPOSE"):
        assert relationship_shadow.RELATIONSHIP_BETA_EXPOSE is False
        assert relationship_shadow.REL_LIVE_CONTEXT_EXPOSE_ENABLED is False

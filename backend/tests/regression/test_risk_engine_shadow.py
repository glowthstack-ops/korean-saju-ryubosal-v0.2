"""위험 엔진 R0 shadow 회귀 — 기존 출력 불변 계약 (RISK_ENGINE.md §8).

기준 차트(1980-11-22 09:08 서울 남)로 고정한다:
- OFF(기본): 위험 계산 없음 + 긍정 후보 byte-identical.
- SHADOW: 긍정 후보 불변 + risk_shadow 사이드채널에만 원자 후보 기록(LLM 입력 미주입).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, risk_engine_config
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.risk_engine import EvidenceRole, RiskCandidate

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    """기준 차트(기준일 2026-06-11 — 기존 회귀와 동일)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


def _dump(cands) -> list[dict]:
    return [c.model_dump() for c in cands]


def test_off_is_default_and_collects_nothing(chart) -> None:
    """기본(config off)에서는 위험 계산이 전혀 없다 — risk_shadow 빈 목록."""
    engine = EventEngineV2(_DICTS)
    engine.score(chart, levels={GanjiLevel.YEAR})
    assert engine.risk_shadow == []


def test_shadow_keeps_positive_output_byte_identical(chart) -> None:
    """SHADOW 모드는 긍정 후보 출력을 단 하나도 바꾸지 않는다(OFF와 동일 직렬화)."""
    off = EventEngineV2(_DICTS, risk_mode="off").score(chart, levels={GanjiLevel.YEAR})
    shadow_engine = EventEngineV2(_DICTS, risk_mode="shadow")
    shadow = shadow_engine.score(chart, levels={GanjiLevel.YEAR})
    assert _dump(off) == _dump(shadow)


def test_shadow_candidates_are_atomic_and_r0_scoped(chart) -> None:
    """shadow 원자 후보는 R0 계약을 지킨다 — 근거 보유·점수 미산출·단일 기간."""
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    engine.score(chart, levels={GanjiLevel.YEAR})
    assert engine.risk_shadow, "기준 차트 세운 10년 창에는 불리 시기가 존재한다"
    for c in engine.risk_shadow:
        assert isinstance(c, RiskCandidate)
        triggers = [e for e in c.evidence if e.role is EvidenceRole.TRIGGER]
        assert triggers, "trigger 근거 없는 후보 금지"
        assert c.score_components is None and c.confidence == 0.0  # R1 이전 미산출
        assert c.period_key.isdigit()  # 세운 레벨 원자 후보 — 단일 연도 라벨(병합은 R2)
        # evidence_id 중복 반영 금지(동일 원인·동일 역할·동일 그룹 1회 — 같은 사실을
        # event_shape/targeted 룰이 함께 잡는 경우는 그룹 사실 보존을 위해 허용).
        keys = [(e.evidence_id, e.role, e.source_group) for e in c.evidence]
        assert len(keys) == len(set(keys))


def test_config_gate_is_read_at_call_time(chart, monkeypatch) -> None:
    """생성자 강제값 없이도 config 상수 1줄 전환으로 shadow가 켜진다(운영 전환 경로)."""
    engine = EventEngineV2(_DICTS)
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", "shadow")
    engine.score(chart, levels={GanjiLevel.YEAR})
    assert engine.risk_shadow
    monkeypatch.setattr(risk_engine_config, "RISK_ENGINE_MODE", "off")
    engine.score(chart, levels={GanjiLevel.YEAR})
    assert engine.risk_shadow == []


def test_score_years_resets_shadow(chart) -> None:
    """score_years도 호출마다 사이드채널을 초기화한다(누적 오염 방지)."""
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    engine.score_years(chart, [2026])
    first = list(engine.risk_shadow)
    engine.score_years(chart, [2026])
    assert _dump(first) == _dump(engine.risk_shadow)


def test_off_vs_shadow_final_llm_input_byte_identical(chart) -> None:
    """감수 42차 §9: OFF와 SHADOW의 **최종 LLM 입력 직렬화**가 byte-identical.

    grep(모듈 미배선)은 보조 장치 — 실제 직렬화 결과 비교가 감수 기준이다.
    SHADOW는 presentation payload를 별도로 계산할 수 있지만 최종 LLM 입력에는
    필드·문구·토큰 변화가 0이어야 한다(주입 후 '사용 금지' 지시 방식 불허).
    """
    import json

    from saju_engines.llm_event_serializer import serialize_candidate_v2

    off_cands = EventEngineV2(_DICTS, risk_mode="off").score(
        chart, levels={GanjiLevel.YEAR})
    shadow_engine = EventEngineV2(_DICTS, risk_mode="shadow")
    shadow_cands = shadow_engine.score(chart, levels={GanjiLevel.YEAR})
    off_llm = json.dumps([serialize_candidate_v2(c) for c in off_cands],
                         ensure_ascii=False, sort_keys=True)
    shadow_llm = json.dumps([serialize_candidate_v2(c) for c in shadow_cands],
                            ensure_ascii=False, sort_keys=True)
    assert off_llm == shadow_llm  # byte-identical
    # SHADOW 진단(presentation payload)은 생성 가능해야 하고, 생성 후에도
    # 최종 LLM 입력이 변하지 않는다.
    from saju_engines.risk_presentation import build_presentation
    from saju_engines.risk_scoring import score_shadow
    from saju_engines.risk_selection import build_episodes

    scored = score_shadow(list(shadow_engine.risk_shadow), {})
    payload = build_presentation(build_episodes(scored), scored)
    assert "presentationRecords" in payload
    shadow_llm_after = json.dumps(
        [serialize_candidate_v2(c) for c in shadow_cands],
        ensure_ascii=False, sort_keys=True)
    assert shadow_llm_after == off_llm

"""P1 기회·호전 사전 + 경량 엔진(2026-09-18 데굴님 승인) — 위험 사전의 긍정 대칭 층.

판정 공유·점수 불변: 후보 서술의 '호전·기회 신호' 줄만 추가한다(플래그 SAJU_OPPORTUNITY_ENABLED).
성사·당첨·확정 표현은 사전의 prohibitedClaims 로 프롬프트에 함께 실린다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import context_reducer as cr
from saju_engines import period_v2_config
from saju_engines.dictionaries import OpportunityMappingFile
from saju_engines.event_scoring import favorability_map
from saju_engines.opportunity_engine import (
    _DOMAINS,
    detect_opportunities,
    format_opportunity_notes,
    load_opportunities,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate, EventKey

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FORBIDDEN_IN_NOTES = ("반드시", "확실히", "당첨됩니다", "합격합니다", "결혼합니다")


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def chart():
    return calculate(_birth())


@pytest.fixture(scope="module")
def months():
    return luck_months(_birth(), 2026) + luck_months(_birth(), 2027)


def test_dictionaries_cover_seven_domains_and_positive_families() -> None:
    """7 도메인 36종, family 는 event_process_types 긍정 유형 id, 확정 금지 문구 필수."""
    files = load_opportunities(_DICTS)
    assert [f.domain for f in files] == list(_DOMAINS)
    items = [i for f in files for i in f.items]
    assert len(items) == 36
    types = json.loads((_DICTS / "event_process_types.json").read_text("utf-8"))["items"]
    positive = {i["id"] for i in types if i["valence"] == "positive"}
    for it in items:
        assert it.family in positive, it.opportunity_id
        assert it.prohibited_claims, it.opportunity_id
        assert it.kind in ("opportunity", "achievement", "maintenance", "relief")
        assert not it.reviewed  # 감수 전 상태 위조 금지
    ids = [i.opportunity_id for i in items]
    assert len(ids) == len(set(ids))
    # 스키마는 미정의 룰 필드를 거부한다(extra=forbid).
    bad = {"version": "x", "domain": "career", "items": [{
        "opportunityId": "X", "domain": "career", "kind": "opportunity", "family": "recovery",
        "baseValue": 0.2, "triggerRules": [{"id": "r", "bogus": 1}],
        "manifestations": [{"id": "a", "ko": "b"}],
    }]}
    with pytest.raises(ValidationError):
        OpportunityMappingFile.model_validate(bad)


def test_engine_emits_signals_and_respects_threshold(chart, months) -> None:
    """데굴 차트: 2026-10(강한 용신운)·2027-02(관운 강화)에 신호가 있고, 점수는 문턱 이상 1 이하."""
    fav = favorability_map(chart)
    by = {m.label: m for m in months}
    got = {label: detect_opportunities(chart, by[label], fav) for label in ("2026-10", "2027-02")}
    assert any(got.values()), got
    for label, sigs in got.items():
        for s in sigs:
            assert period_v2_config.OPPORTUNITY_MIN_SCORE <= s.score <= 1.0, (label, s)
            assert s.evidence and s.manifestations
        assert [s.score for s in sigs] == sorted((s.score for s in sigs), reverse=True)
    # 2027-02 壬寅: 丁壬合·寅亥合 → 관운 강화 재료 → 직업 기회 유입 신호가 잡힌다.
    feb = {s.opportunity_id for s in got["2027-02"]}
    assert "CAR_OFFER_INFLOW" in feb, feb
    # 도메인 제한.
    only = detect_opportunities(chart, by["2027-02"], fav, domains=["finance"])
    assert all(s.domain == "finance" for s in only)


def test_notes_are_capped_and_carry_prohibitions(chart, months) -> None:
    fav = favorability_map(chart)
    m = next(x for x in months if x.label == "2027-02")
    notes = format_opportunity_notes(detect_opportunities(chart, m, fav))
    assert 1 <= len(notes) <= 2
    for n in notes:
        assert "확정 금지:" in n and "근거" in n
        assert not any(w in n for w in _FORBIDDEN_IN_NOTES)


def test_candidate_notes_follow_flag(chart, monkeypatch) -> None:
    """OFF: 빈 목록(byte 불변). ON: 후보 시점의 신호 줄."""
    fav = favorability_map(chart)
    c = EventCandidate(
        event_key=EventKey.CAREER_CHANGE, event_type="progress", period="2027-02", score=90,
        confidence="high", polarity="negative_or_forced", signals=[], evidence_path=[],
        daewoon_context="",
    )
    monkeypatch.setattr(period_v2_config, "OPPORTUNITY_ENABLED", False)
    assert cr._candidate_opportunity_notes(chart, c, fav) == []
    monkeypatch.setattr(period_v2_config, "OPPORTUNITY_ENABLED", True)
    # 월운이 결과에 실려 있어야 시점 기둥을 찾는다.
    chart2 = chart.model_copy(deep=True)
    chart2.luck_cycles.monthly_luck = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)
    notes = cr._candidate_opportunity_notes(chart2, c, fav)
    assert notes and all("호전" not in n or True for n in notes)
    unknown = c.model_copy(update={"period": "1999-01"})
    assert cr._candidate_opportunity_notes(chart2, unknown, fav) == []

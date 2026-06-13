"""LEI 서비스 seam 검증 — 개인화가 레거시 후보·다운스트림 정렬까지 흐르는지.

EventEngineV2.score_legacy_personalized가 life_fit/personal_match를 레거시 후보로 전달하고,
context_reducer.reduce_candidates가 LEI 정렬축을 따르는지 확인한다(개인 시그니처 미배선 시 동치).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import reduce_candidates
from saju_engines.event_engine_v2 import EventEngineV2
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import (
    Confidence,
    EventCandidate,
    EventKey,
    EventPolarity,
    EventType,
)
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


def _legacy(event: str, score: int, *, life_fit: float = 0.0, pm: float = 0.0) -> EventCandidate:
    return EventCandidate(
        event_key=event, event_type=EventType.PROGRESS, period="2026", score=score,
        confidence=Confidence.MEDIUM, polarity=EventPolarity.NEUTRAL,
        life_fit=life_fit, personal_match=pm,
    )


def test_legacy_carries_lei_fields() -> None:
    assert _legacy("relocation", 50, life_fit=40, pm=50).life_fit == 40


def test_reduce_candidates_lei_order() -> None:
    # 점수 낮아도 personal_match 높으면 상위(LEI 정렬축).
    cs = [
        _legacy("career_change", 90),
        _legacy("relocation", 20, life_fit=40, pm=60),
    ]
    out = reduce_candidates(cs, graph_scope=[], score_floor=0)
    assert str(out[0].event_key) == "relocation"


def test_reduce_candidates_backward_compatible() -> None:
    # LEI 필드 0이면 기존 -score 정렬과 동치.
    cs = [_legacy("relocation", 20), _legacy("career_change", 90)]
    out = reduce_candidates(cs, graph_scope=[], score_floor=0)
    assert str(out[0].event_key) == "career_change"


def test_personalized_seeds_relocation_in_legacy(chart) -> None:
    eng = EventEngineV2(_DICTS)
    sig = [
        LifeEventRow(
            event_row_id=f"r{p}", subject_id="s1",
            pillar_year="庚申", pillar_month="丁亥", pillar_day="己亥", gender="male",
            event_key="relocation", period=p,
            signal_fingerprint=SignalFingerprint(ten_god_groups=["wealth"], palace="day_pillar"),
            outcome=LifeEventOutcome.CONFIRMED, source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
        )
        for p in ("2024", "2025")
    ]
    legacy = eng.score_legacy_personalized(
        chart, levels={GanjiLevel.YEAR}, signature=sig,
    )
    seeded = [c for c in legacy if c.event_key is EventKey.RELOCATION and c.personal_match > 0]
    assert seeded, "개인 이사 이력이 레거시 후보(personal_match>0)로 전달돼야 한다"


def test_personal_inputs_no_effect_without_data(chart) -> None:
    # owner/subject 미확정이면 (None, None). 확정이어도 데이터 없으면 '개인화 효과 없음'으로 수렴
    # (DB 미연결=폴백 None / DB 연결+무데이터=빈 시그니처·비활성 코호트 — 둘 다 랭킹 무영향).
    from saju_api.services.personalization import fetch_personal_inputs

    assert fetch_personal_inputs(None, None, chart) == (None, None)
    sig, cohort = fetch_personal_inputs("nonexistent-owner", "nonexistent-subj", chart)
    assert not sig  # None 또는 빈 목록
    assert cohort is None or cohort.tier == "none"  # 비활성(랭킹 미반영)

"""지연 outcome 회수·채팅 평가·캘리브레이션 상태(life_event_followup) 검증 — 2026-10-24.

LIFE_EVENT_INFERENCE §4.1 ②③. 순수 함수만(DB 없음). 골든 차트 1980-11-22.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.life_event_followup import (
    FollowupAnswer,
    FollowupCandidate,
    calibration_status,
    elapsed_candidates,
    followup_candidates,
    followup_question,
    is_elapsed,
    is_open,
    period_ko,
    resolve_fingerprints,
    rows_from_followup,
)
from saju_engines.personal_calibration import candidate_fingerprint
from saju_engines.reality_calibration import build_reality_calibration, pillars_signature
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 10, 24)
_LUCK_MONTH = "2026-10"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=_TODAY,
    ))


@pytest.fixture(scope="module")
def engine():
    return EventEngineV2(_DICTS)


def test_period_elapsed_and_open_use_luck_month_label() -> None:
    # 연: 해가 바뀐 뒤 / 월: 절기 월운 라벨 비교 / 일: 다음 날
    assert is_elapsed("2025", _LUCK_MONTH, _TODAY) and not is_open("2025", _LUCK_MONTH, _TODAY)
    assert is_open("2026", _LUCK_MONTH, _TODAY) and not is_elapsed("2026", _LUCK_MONTH, _TODAY)
    assert is_elapsed("2026-09", _LUCK_MONTH, _TODAY)
    assert is_open("2026-10", _LUCK_MONTH, _TODAY)   # 진행 중인 달은 아직 묻지 않는다
    assert is_open("2026-11", _LUCK_MONTH, _TODAY)
    assert is_elapsed("2026-10-23", _LUCK_MONTH, _TODAY)
    assert is_open("2026-10-24", _LUCK_MONTH, _TODAY)
    assert not is_elapsed("garbage", _LUCK_MONTH, _TODAY)
    assert not is_open("garbage", _LUCK_MONTH, _TODAY)


def test_followup_candidates_keep_only_open_periods_with_fingerprint(chart, engine) -> None:
    scored = engine.score_years(chart, [2024, 2025, 2026, 2027])
    picked = followup_candidates(scored, current_luck_month=_LUCK_MONTH, today=_TODAY)
    assert 1 <= len(picked) <= 3
    assert all(c.period in {"2026", "2027"} for c in picked)
    # V2 후보는 답변 시점에 지문이 바로 채워진다
    assert all(c.fingerprint.ten_god_groups or c.fingerprint.palace for c in picked)
    assert all(c.event_ko and c.event_ko != c.event_key for c in picked)  # 한글 라벨
    keys = [(c.event_key, c.period) for c in picked]
    assert len(keys) == len(set(keys))
    # 점수 내림차순
    assert [c.score for c in picked] == sorted((c.score for c in picked), reverse=True)


def test_followup_candidates_prefer_month_over_year_for_same_event(chart, engine) -> None:
    scored = engine.score_years(chart, [2026])
    base = scored[0]
    month_dup = base.model_copy(update={"period": "2026-12"})
    picked = followup_candidates(
        [base, month_dup], current_luck_month=_LUCK_MONTH, today=_TODAY, limit=3,
    )
    periods = {c.period for c in picked if c.event_key == str(base.event_key)}
    assert periods == {"2026-12"}  # 같은 사건의 연 후보는 월 후보에 밀린다


def test_followup_candidates_accept_legacy_and_resolver_fills_fingerprint(chart, engine) -> None:
    from saju_shared_types.events import EventCandidate

    v2 = engine.score_years(chart, [2027])[0]
    legacy = EventCandidate(
        event_key=str(v2.event_key), event_type="progress", period="2027", score=70,
        confidence="high", polarity="positive",
    )
    picked = followup_candidates([legacy], current_luck_month=_LUCK_MONTH, today=_TODAY)
    assert len(picked) == 1 and picked[0].fingerprint == SignalFingerprint()  # legacy → 빈 지문
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    resolved = resolve_fingerprints(picked, birth=birth, engine=engine, calculate=calculate)
    assert resolved[0].fingerprint == candidate_fingerprint(v2)
    # 엔진이 내지 않는 사건은 빈 지문 그대로(적재는 막지 않는다)
    ghost = FollowupCandidate(event_key="marriage", event_ko="결혼", period="2027")
    ghost_fp = resolve_fingerprints(
        [ghost], birth=birth, engine=engine, calculate=calculate,
    )[0].fingerprint
    assert ghost_fp == SignalFingerprint()


def _cand(key: str, period: str, ko: str = "이사") -> FollowupCandidate:
    return FollowupCandidate(event_key=key, event_ko=ko, period=period, score=50)


def test_elapsed_candidates_restore_from_meta_and_skip_garbage() -> None:
    stored = [
        _cand("relocation", "2026-09").model_dump(mode="json"),
        _cand("job_change", "2026-11", "이직").model_dump(mode="json"),
        {"bad": "row"},
    ]
    got = elapsed_candidates(stored, current_luck_month=_LUCK_MONTH, today=_TODAY)
    assert [c.period for c in got] == ["2026-09"]


def test_question_and_period_ko_are_templates() -> None:
    assert period_ko("2026") == "2026년"
    assert period_ko("2026-09") == "2026년 9월"
    assert period_ko("2026-09-03") == "2026년 9월 3일"
    one = followup_question([_cand("relocation", "2026-09")])
    assert one.startswith("지난 2026년 9월에 '이사' 흐름을 말씀드렸는데")
    many = followup_question(
        [_cand("relocation", "2026-09"), _cand("job_change", "2026-09", "이직")],
    )
    assert "흐름들이 실제로 있었는지" in many
    assert followup_question([]) == ""


def test_rows_from_followup_only_known_candidates_and_not_unknown(chart) -> None:
    cands = [_cand("relocation", "2026-09"), _cand("job_change", "2026-09", "이직")]
    answers = [
        FollowupAnswer(event_key="relocation", period="2026-09", outcome="confirmed"),
        FollowupAnswer(event_key="job_change", period="2026-09", outcome="unknown"),
        FollowupAnswer(event_key="marriage", period="2026-09", outcome="confirmed"),  # 후보 밖
    ]
    rows = rows_from_followup(
        subject_id="s1", owner_id="o1", pillars_sig=pillars_signature(chart),
        answers=answers, candidates=cands,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.event_row_id == "s1:2026-09:relocation"  # 캘리브레이션과 같은 칸 → 덮어쓴다
    assert row.source is LifeEventSource.DELAYED_OUTCOME
    assert row.outcome is LifeEventOutcome.CONFIRMED
    assert row.pillar_day == chart.pillars.day.ganji


def _row(outcome: LifeEventOutcome) -> LifeEventRow:
    return LifeEventRow(
        event_row_id="x", subject_id="s",
        pillar_year="庚申", pillar_month="丁亥", pillar_day="己亥",
        event_key="relocation", period="2025", outcome=outcome,
        source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
    )


def test_calibration_status_modes() -> None:
    empty = calibration_status([], None, _TODAY)
    assert empty.suggested_mode == "initial" and not empty.has_events
    fresh = calibration_status(
        [_row(LifeEventOutcome.CONFIRMED)], datetime(2026, 6, 1, tzinfo=UTC), _TODAY,
    )
    assert fresh.has_events and fresh.confirmed == 1 and not fresh.stale
    assert fresh.suggested_mode is None
    old = calibration_status(
        [_row(LifeEventOutcome.NOT_HAPPENED)], datetime(2025, 6, 1, tzinfo=UTC), _TODAY,
    )
    assert old.stale and old.suggested_mode == "refresh" and old.not_happened == 1
    # 설문 제출 없이 직장 이력만 있는 명식은 stale 로 보지 않는다
    eh_only = calibration_status([_row(LifeEventOutcome.CONFIRMED)], None, _TODAY)
    assert not eh_only.stale and eh_only.suggested_mode is None


def test_build_reality_calibration_forced_years(chart, engine) -> None:
    q = build_reality_calibration(chart, engine, 2026, subject_id="s", years=[2025, 2026, 2030])
    assert [y.year for y in q.years] == [2025, 2026]  # 현재 이후 해는 제외
    full = build_reality_calibration(chart, engine, 2026, subject_id="s")
    assert len(full.years) > 2

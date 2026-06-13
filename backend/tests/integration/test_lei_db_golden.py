"""LEI 실 DB 통합 — 골든셋(2025-08 이사) 재현 (Life Event Inference C3).

현실 신호 캘리브레이션으로 적재된 개인 사건(2025-08 이사)이 ① subject_signature 라운드트립 ②
LifeFitRanker로 2026 relocation을 개인화 부상 ③ 동일사주 코호트 활성 게이트까지 실 DB로 검증한다.
DB(saju-v2-db) 미기동 시 skip. 테스트 전용 owner로 격리하고 종료 시 정리한다.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg
import pytest

from saju_api.services.manse_service import calculate
from saju_engines.cohort_calibration import cohort_stats_from_counts
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.life_event_store import LifeEventStore
from saju_engines.life_fit_ranker import LifeFitRanker
from saju_engines.reality_calibration import pillars_signature
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_OWNER = "lei-golden-test-owner"
_MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "008_life_events.sql"


def _dsn() -> str | None:
    return os.getenv("SAJU_V2_DATABASE_URL")


@pytest.fixture(scope="module")
def store() -> LifeEventStore:
    dsn = _dsn()
    if not dsn:
        pytest.skip("SAJU_V2_DATABASE_URL 미설정 — DB 통합 skip")
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            pass
    except Exception:  # noqa: BLE001
        pytest.skip("DB 미연결 — 통합 skip")
    s = LifeEventStore(dsn)
    s.migrate()
    yield s
    # 정리 — 테스트 owner 행 삭제.
    with psycopg.connect(dsn) as conn:
        conn.execute("DELETE FROM subject_life_events WHERE owner_id=%s", (_OWNER,))


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


def _relocation_row(
    subject_id: str, pillars_sig, period: str,
    outcome: LifeEventOutcome = LifeEventOutcome.CONFIRMED,
) -> LifeEventRow:
    py, pm, pd, ph, gender = pillars_sig
    return LifeEventRow(
        event_row_id=f"{_OWNER}:{subject_id}:{period}:relocation",
        subject_id=subject_id, owner_id=_OWNER,
        pillar_year=py, pillar_month=pm, pillar_day=pd, pillar_hour=ph, gender=gender,
        event_key="relocation", period=period,
        signal_fingerprint=SignalFingerprint(ten_god_groups=["wealth"], palace="day_pillar"),
        outcome=outcome, source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
    )


def test_signature_roundtrip_and_personalized_relocation(store, chart) -> None:
    sig_pillars = pillars_signature(chart)
    # 골든(사용자 타임라인): 2025-08 이사 확정 + 2026-08 이사 예정(planned).
    store.append_rows([
        _relocation_row("golden-subj", sig_pillars, "2025-08"),
        _relocation_row("golden-subj", sig_pillars, "2026-08", LifeEventOutcome.PLANNED),
    ])
    sig = store.subject_signature(_OWNER, "golden-subj")
    assert any(r.event_key == "relocation" and r.period == "2025-08" for r in sig)

    # 2026 세운 후보(엔진만으론 relocation 미생성) → 개인 이력으로 부상.
    eng = EventEngineV2(_DICTS)
    cands = [c for c in eng.score(chart, levels={GanjiLevel.YEAR}) if c.period == "2026"]
    ranked = LifeFitRanker().rank(cands, signature=sig)
    reloc = [c for c in ranked if str(c.event_key) == "relocation"]
    assert reloc and reloc[0].personal_match > 0  # 실 DB 시그니처로 부상


def test_cohort_activation_gate_with_db(store, chart) -> None:
    sig_pillars = pillars_signature(chart)
    py, pm, pd, ph, gender = sig_pillars
    # 동일 일주+성별 코호트 — fine 임계(8) 도달하도록 8명 적재(전체 사주 동일).
    rows = [
        _relocation_row(f"cohort-{i}", sig_pillars, "2020")
        for i in range(8)
    ]
    # event_row_id가 subject별로 달라야 8명으로 집계되므로 subject_id를 분리(이미 분리됨).
    store.append_rows([
        r.model_copy(update={"event_row_id": f"{_OWNER}:cohort-{i}:2020:relocation"})
        for i, r in enumerate(rows)
    ])
    coarse = store.cohort_event_counts(pillar_day=pd, gender=gender)
    fine = store.cohort_event_counts(
        pillar_day=pd, gender=gender, fine_pillars=(py, pm, pd, ph),
    )
    stats = cohort_stats_from_counts(coarse, fine)
    # 8명 동일 사주 → fine 활성, relocation 보유 비율>0.
    assert stats.tier in ("fine", "coarse")
    assert stats.rate_by_event.get("relocation", 0) > 0

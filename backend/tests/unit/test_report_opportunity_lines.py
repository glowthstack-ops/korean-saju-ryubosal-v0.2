"""리포트 경로 '호전·기회 신호' 배선(P1 후속, 2026-09-18) — 채팅 패리티.

precise_candidate_clusters 가 시점마다 기회 엔진 신호를 후보 도메인에 한정해 상위 2개까지 싣는다.
플래그 OFF·용신 맵 부재면 기존 줄과 byte 동일.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import period_v2_config
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import favorability_map
from saju_engines.report_event_input import precise_candidate_clusters
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def chart():
    c = calculate(_birth())
    c.luck_cycles.monthly_luck = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)
    return c


@pytest.fixture(scope="module")
def feb_cands(chart):
    cands = EventEngineV2(_DICTS).score_legacy(chart, levels={GanjiLevel.MONTH})
    return [c for c in cands if c.period == "2027-02"]


def test_clusters_carry_opportunity_lines_only_when_flag_on(chart, feb_cands, monkeypatch):
    assert feb_cands
    fav = favorability_map(chart)
    monkeypatch.setattr(period_v2_config, "OPPORTUNITY_ENABLED", False)
    off = precise_candidate_clusters(chart, feb_cands, fav_map=fav)
    assert not any("호전·기회 신호" in ln for ln in off)
    monkeypatch.setattr(period_v2_config, "OPPORTUNITY_ENABLED", True)
    on = precise_candidate_clusters(chart, feb_cands, fav_map=fav)
    opp = [ln for ln in on if "호전·기회 신호" in ln]
    assert len(opp) == 1, on
    assert "확정 금지" in opp[0] and "근거" in opp[0]
    # 후보 도메인(직업·선발·재무·계약 등)에 한정 — 건강 회복 같은 무관 신호가 섞이지 않는다.
    assert "증상 호전" not in opp[0]
    # 기회 줄은 헤더(시점 간지 줄) 뒤·후보 줄('  - ') 앞에 온다.
    i_head = next(i for i, ln in enumerate(on) if ln.startswith("[2027-02"))
    i_opp = next(i for i, ln in enumerate(on) if "호전·기회 신호" in ln)
    i_cand = next(i for i, ln in enumerate(on) if ln.startswith("  - "))
    assert i_head < i_opp < i_cand
    # 용신 맵이 없으면 플래그가 켜져 있어도 싣지 않는다.
    assert not any("호전·기회 신호" in ln for ln in precise_candidate_clusters(chart, feb_cands))

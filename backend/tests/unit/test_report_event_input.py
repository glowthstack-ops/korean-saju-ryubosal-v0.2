"""리포트 전용 정밀 후보 입력 검증.

per-글자 십성(辛=식신/亥=정재)·관계 분해(運↔원국 충/자형/복음)·시점 클러스터를 확인한다.
LLM이 '辛亥=정재'·'재성 지지 충' 같은 부정확 표현을 짓지 못하도록 정밀 라벨이 입력에 박히는지 본다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.report_event_input import month_overview_lines, precise_candidate_clusters
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def chart_2031():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2031, 6, 11),
    ))


def _cands_2031(chart):
    cands = EventEngineV2(_DICTS).score_legacy(chart, levels={GanjiLevel.YEAR})
    return [c for c in cands if c.period == "2031"]


def test_per_character_ten_god_exposed(chart_2031) -> None:
    cands = _cands_2031(chart_2031)
    block = "\n".join(precise_candidate_clusters(chart_2031, cands))
    # 辛亥 세운: 천간 辛은 식신, 지지 亥는 정재 — '辛亥=정재' 환각 차단.
    assert "辛=식신" in block
    assert "亥=정재" in block
    # 시점 클러스터 헤더(운간지).
    assert "[2031 辛亥]" in block


def test_relation_breakdown_not_vague(chart_2031) -> None:
    cands = _cands_2031(chart_2031)
    block = "\n".join(precise_candidate_clusters(chart_2031, cands))
    # 관계는 글자 단위로 분해(運X↔원국Y 관계명) — vague 표현 아님.
    assert "運 亥↔원국" in block
    assert "자형" in block or "충" in block or "해" in block
    assert "복음" in block  # 亥亥 반복(伏吟) 표기


def test_clusters_merge_same_period(chart_2031) -> None:
    cands = _cands_2031(chart_2031)
    lines = precise_candidate_clusters(chart_2031, cands)
    # 같은 시점 헤더는 1회, 사건은 들여쓰기 항목으로 병합.
    headers = [ln for ln in lines if ln.startswith("[2031")]
    assert len(headers) == 1
    assert any(ln.startswith("  - ") for ln in lines)


def test_month_overview_surfaces_luck_grade_and_stars_strong_quality() -> None:
    """리포트 월별 흐름 — 각 달에 운 품질 등급〈…〉 노출 + '강한 용신운' 달은 ★주목(사건 적어도).

    己土 신약(용신 土) 차트: 2026-10 戊戌은 천간·지지 모두 용신(土)인 '강한 용신운' 달이다.
    이 달은 비겁운이라 사건은 적지만, 운 품질로 ★주목에 포함돼야 한다(길흉=용신/기신 우선).
    """
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.495, longitude=126.858,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 6, 16),
    ))
    scored = EventEngineV2(_DICTS).score_legacy(chart, levels={GanjiLevel.MONTH})
    lines = month_overview_lines(chart, scored)
    oct_line = next(ln for ln in lines if ln.startswith("2026-10"))
    assert "〈강한 용신운〉" in oct_line  # 운 품질 등급이 길흉 1차 기준으로 노출
    assert "★주목" in oct_line  # 사건이 적어도 운 품질로 주목
    # 모든 달이 운 품질 등급을 달고 나온다(빠짐없이).
    assert all("〈" in ln for ln in lines if ln.startswith("2026-"))

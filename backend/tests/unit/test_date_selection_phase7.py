"""Phase 7 택일·생활 운세 검증 (T7.1~T7.7 — docs/02 E10 + docs/08 G6 표현 제한)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saju_api.main import app
from saju_api.services.manse_service import calculate
from saju_engines.date_selection import DateSelectionEngine, hour_fits
from saju_engines.precompute import CompositeBuilder
from saju_engines.prediction import PredictionEngines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
client = TestClient(app)


@pytest.fixture(scope="module")
def composites():
    """기준 차트(1980) — 일운은 2026-06."""
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    return CompositeBuilder(_DICTS).build(
        chart, "본인", "1.0.0", "2026-06-11T00:00:00+00:00"
    )


@pytest.fixture(scope="module")
def engine() -> DateSelectionEngine:
    return DateSelectionEngine(_DICTS)


# ── T7.3 — 5단계 점수 + 목적별 가중 랭킹 ─────────────────────────


def test_relocation_ranking_with_part_scores(engine, composites) -> None:
    """이사 택일: 부분점수 5종 + 랭킹 + 손없는 날 보너스 반영."""
    result = engine.select(
        EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30",
    )
    assert result.candidates
    top = result.candidates[0]
    s = top.scores
    assert all(0 <= v <= 100 for v in (
        s.macro_flow, s.month_fit, s.day_execution, s.calendar_rule, s.reality_fit, s.final,
    ))
    finals = [c.scores.final for c in result.candidates]
    assert finals == sorted(finals, reverse=True)
    assert all(c.recommendation in ("recommended", "acceptable", "avoid")
               for c in result.candidates)


def test_purpose_changes_weighting(engine, composites) -> None:
    """목적이 다르면 가중이 달라 랭킹/점수가 달라질 수 있다(프로파일 사전)."""
    move = engine.select(EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30")
    contract = engine.select(EventKey.CONTRACT_DOCUMENT, composites, "2026-06-01", "2026-06-30")
    assert move.purpose is EventKey.RELOCATION
    assert contract.purpose is EventKey.CONTRACT_DOCUMENT
    # 동일 날짜의 최종 점수가 목적별 가중으로 달라진다(전부 동일하면 가중 미적용 의심).
    move_by_date = {c.date: c.scores.final for c in move.candidates}
    diff = [
        c for c in contract.candidates
        if c.date in move_by_date and c.scores.final != move_by_date[c.date]
    ]
    assert diff or len(move.candidates) != len(contract.candidates)


# ── T7.1 — Calendar Rule(손없는 날·공휴일·주말) ──────────────────


def test_calendar_flags(engine, composites) -> None:
    """후보에 손없는날/공휴일/주말 표시 동반."""
    result = engine.select(
        EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30", top_n=30,
    )
    assert any(c.son_eomneun_nal for c in result.candidates)  # 6월 내 존재(음력 9·0일)
    assert any(c.is_weekend for c in result.candidates)
    holiday = [c for c in result.candidates if c.date == "2026-06-06"]
    if holiday:  # 현충일이 후보에 살아남았다면 공휴일 표시
        assert holiday[0].is_holiday


# ── T7.2 — Risk Avoidance(금기일 필터) ───────────────────────────


def test_avoid_days_filtered_with_reason(engine, composites) -> None:
    """기신+충 등 금기일은 후보에서 제외되고 사유와 함께 회피 목록으로."""
    result = engine.select(
        EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30", top_n=30,
    )
    candidate_dates = {c.date for c in result.candidates}
    for avoid in result.avoid_dates:
        assert avoid["date"] not in candidate_dates
        assert avoid["reason"]


# ── T7.4 — Reality Constraint ────────────────────────────────────


def test_weekend_only_constraint(engine, composites) -> None:
    """'주말만 가능' → 가능한 날 중 가장 좋은 날만."""
    result = engine.select(
        EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30",
        reality_constraints=["주말만 가능"],
    )
    assert result.candidates
    assert all(date.fromisoformat(c.date).weekday() >= 5 for c in result.candidates)


# ── T7.7 — 시진(時辰) 적합도 ─────────────────────────────────────


def test_hour_fits_twelve_slots(engine, composites) -> None:
    """시진 요청 시 12칸 적합도 — 용신 시간대 1.0, 생용신 0.8."""
    result = engine.select(
        EventKey.WINDFALL, composites, "2026-06-01", "2026-06-30",
        yongsin_element="土", include_hour_fit=True,
    )
    assert result.candidates
    fits = result.candidates[0].hour_fits
    assert len(fits) == 12
    best = [f for f in fits if f.fit == 1.0]
    assert best and all("土" in f.note for f in best)
    assert any(f.fit == 0.8 for f in fits)  # 생용신(火) 시간대


def test_hour_fits_standalone() -> None:
    assert len(hour_fits("木")) == 12


# ── T7.6 — windfall/speculation 표현 제한(G6 포함) ───────────────


def test_windfall_volatility_warning_attached(engine, composites) -> None:
    """복권 목적: 일운 비중 축소 프로파일 + 변동성 경고 고정 첨부."""
    result = engine.select(
        EventKey.WINDFALL, composites, "2026-06-01", "2026-06-30",
    )
    assert any("당첨·수익 단정 불가" in c for c in result.cautions)
    assert all(any("투자 조언" in x for x in c.cautions) for c in result.candidates)


def test_lotto_number_request_still_refused() -> None:
    """로또 번호 직접 요청은 어떤 형태로도 거부(G6) — 날짜·방향 대안 제시."""
    res = client.post("/api/v2/chat", json={
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22",
            "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
        },
        "question": "로또 번호 좀 찍어줘", "today": "2026-06-11", "dry_run": True,
    })
    body = res.json()
    assert body["status"] == "policy" and "로또 번호 생성" in body["answer"]


def test_windfall_advice_disclaimer_fixed() -> None:
    """windfall 조언에는 투자 고지가 템플릿 레벨로 고정(docs/07 리스크 6)."""
    engines = PredictionEngines(_DICTS)
    advice = engines.advice(EventKey.WINDFALL, None)
    assert any("투자" in d for d in advice.disclaimers)


# ── Phase 3 — 재물(횡재) 방위 ──────────────────────────────────


def test_direction_fits_role_based() -> None:
    """역할 기반 — 재성(水)이 용신이면 북이 top, 재성이 기신이면 추천 어려움(가점 없음)."""
    from saju_engines.date_selection import direction_fits

    # 재성 水=용신, 식상 金=희신 → 북(재성·용신) > 서(식상·희신).
    good = direction_fits("水", {"水": "용신", "金": "희신", "木": "기신", "火": "구신"})
    assert good[0].direction == "북" and good[0].fit >= 0.9
    assert "재성" in good[0].note and "용신" in good[0].note

    # 재성 水가 기신이면 재물 방위라도 가점 없이 낮다 — 추천 어려움.
    bad = direction_fits("水", {"水": "기신", "土": "용신"})
    north = next(d for d in bad if d.direction == "북")
    assert north.fit <= 0.35 and "기신" in north.note
    assert bad[0].element == "土"  # 용신(土) 방위가 더 우선


def test_direction_penalizes_gusin_generating() -> None:
    """구신을 생하는 방위는 감점된다(흉신 강화) — 2026-06-16 사용자 지적."""
    from saju_engines.date_selection import direction_fits

    # 구신=火 → 火를 생하는 木(동) 방위 감점.
    fits = direction_fits("水", {"水": "용신", "火": "구신"})
    east = next(d for d in fits if d.direction == "동")  # 木 — 火(구신)를 생
    assert "구신 생" in east.note and east.fit < 0.55


def test_windfall_select_attaches_directions(engine, composites) -> None:
    """횡재 택일 — wealth_element 주면 역할 반영 방위가 fit 순으로 붙는다(Phase 3)."""
    result = engine.select(
        EventKey.WINDFALL, composites, "2026-06-01", "2026-06-30",
        wealth_element="水", favorability={"水": "용신", "金": "희신"},
    )
    assert result.directions and result.directions[0].direction == "북"
    # 방위 note에 '당첨 보장 아님' 류 중복 강조를 넣지 않는다(변동성 경고가 별도 전달).
    assert all("보장" not in d.note for d in result.directions)

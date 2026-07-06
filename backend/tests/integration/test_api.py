"""API-level checks for /health and /api/v2/manse/calculate.

Uses httpx's in-process ASGI transport driven by ``anyio.run`` rather than
Starlette's TestClient. TestClient spins up a background event-loop thread via an
anyio portal, which can block indefinitely in restricted sandboxes; the ASGI
transport runs the app inline on a single loop and is fully deterministic.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx
from httpx import ASGITransport

from saju_api.main import app


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def test_health() -> None:
    r = _request("GET", "/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_calculate_returns_full_schema() -> None:
    payload = {
        "calendar_type": "solar",
        "birth_date": "1980-11-22",
        "birth_time": "09:08",
        "birth_place_name": "서울",
        "gender": "male",
    }
    r = _request("POST", "/api/v2/manse/calculate", json=payload)
    assert r.status_code == 200
    body = r.json()
    for field in (
        "chart_id",
        "input_summary",
        "time_correction",
        "solar_term_basis",
        "pillars",
        "force_analysis",
        "structure_analysis",
        "geokguk",
        "yongsin_analysis",
        "luck_cycles",
        "calibration",
        "traditional_extras",
        "metadata",
        "trace",
    ):
        assert field in body
    assert body["pillars"]["day"]["ganji"] == "己亥"
    assert body["force_analysis"]["strength"]["band"] == "신약"
    assert body["structure_analysis"]["structure_modifier"] is not None
    assert isinstance(body["structure_analysis"]["interactions"], list)
    assert body["geokguk"]["main_structure"] == "정재격"
    assert body["yongsin_analysis"]["status"] == "candidate"
    assert body["yongsin_analysis"]["final"]["yongsin"] == "土"
    assert body["luck_cycles"]["direction"] == "forward"
    assert len(body["luck_cycles"]["daewoon_table"]) == 10
    assert body["traditional_extras"]["sinsal"]["full_list"]
    assert "천을귀인" in {s["name"] for s in body["traditional_extras"]["sinsal"]["full_list"]}


def test_calibration_feedback_endpoint() -> None:
    birth = {
        "calendar_type": "solar",
        "birth_date": "1980-11-22",
        "birth_time": "09:08",
        "birth_place_name": "서울",
        "gender": "male",
        "reference_date": "2015-06-15",
    }
    calc = _request("POST", "/api/v2/manse/calculate", json=birth).json()
    questions = calc["calibration"]["questions"]
    # CAL-P0/P1 규격: 채점 반영 기본 5문항(event_list) + 채점 비반영 probe 추가 문항 총합 ≤ 3.
    base = [q for q in questions if q["question_type"] == "event_list"]
    assert len(base) == 5
    assert len(questions) - len(base) <= 3
    answers = [
        {"question_id": q["id"], "overall_rating": "positive", "selected_events": ["직업"]}
        for q in base
    ]
    r = _request(
        "POST", "/api/v2/manse/calibration/feedback", json={"birth": birth, "answers": answers}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("calibrated", "probable", "uncertain")
    assert "model_scores" in body


def test_luck_months_endpoint() -> None:
    birth = {
        "calendar_type": "solar",
        "birth_date": "1980-11-22",
        "birth_time": "09:08",
        "birth_place_name": "서울",
        "gender": "male",
        "reference_date": "2015-06-15",
    }
    r = _request("POST", "/api/v2/manse/luck/months", json={"birth": birth, "year": 2015})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12  # 월운 12개
    assert body[0]["twelve_unseong"] and body[0]["stem"] and body[0]["branch"]


def test_unknown_location_returns_422() -> None:
    payload = {
        "calendar_type": "solar",
        "birth_date": "1990-01-01",
        "birth_time": "10:00",
        "birth_place_name": "Atlantis",
    }
    r = _request("POST", "/api/v2/manse/calculate", json=payload)
    assert r.status_code == 422


def test_calendar_month_endpoint() -> None:
    r = _request("GET", "/api/v2/calendar/2024/2")
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2024 and body["month"] == 2
    assert len(body["days"]) == 29
    assert any(t["name"] == "입춘" for t in body["solar_terms"])
    assert body["days"][0]["day_ganji"] and body["days"][0]["day_ganji_ko"]


def test_calendar_invalid_month_returns_422() -> None:
    r = _request("GET", "/api/v2/calendar/2024/13")
    assert r.status_code == 422

"""API-level checks for /health and /api/v2/manse/calculate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from saju_api.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
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
    r = client.post("/api/v2/manse/calculate", json=payload)
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


def test_unknown_location_returns_422() -> None:
    payload = {
        "calendar_type": "solar",
        "birth_date": "1990-01-01",
        "birth_time": "10:00",
        "birth_place_name": "Atlantis",
    }
    r = client.post("/api/v2/manse/calculate", json=payload)
    assert r.status_code == 422

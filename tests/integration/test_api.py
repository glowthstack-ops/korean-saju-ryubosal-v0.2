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


def test_unknown_location_returns_422() -> None:
    payload = {
        "calendar_type": "solar",
        "birth_date": "1990-01-01",
        "birth_time": "10:00",
        "birth_place_name": "Atlantis",
    }
    r = _request("POST", "/api/v2/manse/calculate", json=payload)
    assert r.status_code == 422

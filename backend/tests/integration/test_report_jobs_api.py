"""리포트 비동기 잡 API 검증 (v2.2 프론트 확장 Phase 6).

- 인증 게이트(401)는 DB 없이 검증한다.
- 잡 생성→폴링은 전용 DB(5433)가 떠 있을 때만 실행한다. LLM은 호출하지 않도록
  is_available를 False로 패치해 결정적으로 'failed'(키 미설정 안내) 경로를 검증한다.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.main import app
from saju_api.services import report_service
from saju_engines.precompute_store import default_dsn

_TEST_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"

_SPEC = {
    "product_code": "RPT_FOCUS",
    "subjects": [{"kind": "self", "label": "본인"}],
    "topic": "career",
    "period": {"start": "2020-01", "end": "2030-12"},
}
_BIRTH = {
    "calendar_type": "solar", "birth_date": "1990-05-05", "birth_time": "12:00",
    "birth_place_name": "서울", "gender": "male",
}


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def _db_available() -> bool:
    try:
        from saju_engines.report_job_store import ReportJobStore

        ReportJobStore(_TEST_DSN).migrate()
        return True
    except Exception:
        return False


def test_create_job_requires_auth() -> None:
    r = _request("POST", "/api/v2/report/jobs", json={"subject_id": "x", "spec": _SPEC})
    assert r.status_code == 401


pytestmark_db = pytest.mark.skipif(not _db_available(), reason="전용 DB(5433) 미기동 — skip")


@pytestmark_db
def test_job_lifecycle_fails_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    # LLM 미호출 강제 → 잡은 '키 미설정' 사유로 failed.
    monkeypatch.setattr(report_service.llm_client, "is_available", lambda: False)

    login_id = f"r{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    sid = _request(
        "POST", "/api/v2/subjects",
        headers=auth, json={"kind": "self", "label": "나", "birth": _BIRTH},
    ).json()["subject_id"]

    # 잡 생성 → 202 + sections_total=8(FOCUS).
    r = _request(
        "POST", "/api/v2/report/jobs", headers=auth, json={"subject_id": sid, "spec": _SPEC}
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    # 내 풀이 내역 목록에 방금 생성한 잡이 노출(테마·대상 메타 포함).
    listing = _request("GET", "/api/v2/report/jobs", headers=auth).json()
    mine = next((x for x in listing if x["job_id"] == job_id), None)
    assert mine is not None
    assert mine["product_code"] == "RPT_FOCUS"
    assert mine["topic"] == "career"
    assert mine["subject_labels"] == ["본인"]  # spec.subjects의 라벨 반영

    # 폴링 — 백그라운드 종료 후 failed(키 미설정).
    status = None
    for _ in range(10):
        body = _request("GET", f"/api/v2/report/jobs/{job_id}", headers=auth).json()
        status = body["status"]
        if status in ("completed", "failed"):
            break
    assert status == "failed"
    assert body["sections_total"] == 8
    assert body["error"] and "LLM" in body["error"]

    # 타 계정은 잡 조회 불가.
    other = _request(
        "POST", "/api/v2/auth/register",
        json={"login_id": f"o{uuid.uuid4().hex[:10]}", "pin": "111111"},
    ).json()["token"]
    r = _request(
        "GET", f"/api/v2/report/jobs/{job_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert r.status_code == 404

    _request("DELETE", f"/api/v2/subjects/{sid}", headers=auth)

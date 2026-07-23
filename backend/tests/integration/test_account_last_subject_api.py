"""재로그인 선택 사주 복원 — last-subject API 검증 (2026-07-23).

전용 DB(saju-v2-db) 기동 시에만 실행(없으면 skip). 저장→조회, 타인 소유 거부,
삭제된 사주 null 복원을 확인한다.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.deps import make_token
from saju_api.main import app
from saju_engines.precompute_store import default_dsn

_TEST_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:15432/saju_v2"
# API 계층 저장소는 env 의 DSN 을 쓴다 — 미설정이면 로컬 전용 DB 로 시드.
os.environ.setdefault("SAJU_V2_DATABASE_URL", _TEST_DSN)


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def _db_available() -> bool:
    try:
        from saju_engines.account_store import AccountSettingsStore
        from saju_engines.subject_store import SubjectStore

        SubjectStore(_TEST_DSN).migrate()
        AccountSettingsStore(_TEST_DSN).migrate()  # 005 + 015 적용
        return True
    except Exception:
        return False


_BIRTH = {
    "calendar_type": "solar",
    "is_leap_month": None,
    "birth_date": "1990-01-01",
    "birth_time": "12:00",
    "birth_time_unknown": False,
    "birth_place_name": "서울",
    "latitude": 37.57,
    "longitude": 126.98,
    "timezone": "Asia/Seoul",
    "gender": "male",
}


def _auth(owner: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(owner)}"}


def _create_subject(owner: str) -> str:
    res = _request(
        "POST",
        "/api/v2/subjects",
        json={"kind": "self", "label": f"t-{uuid.uuid4().hex[:6]}", "birth": _BIRTH,
              "gender": "male"},
        headers=_auth(owner),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["subject_id"]


@pytest.mark.skipif(not _db_available(), reason="전용 DB(saju-v2-db) 미기동")
def test_last_subject_roundtrip() -> None:
    owner = f"ls-{uuid.uuid4().hex[:8]}"
    subject_id = _create_subject(owner)

    # 초기값 null
    res = _request("GET", "/api/v2/account/last-subject", headers=_auth(owner))
    assert res.status_code == 200 and res.json()["subject_id"] is None
    # 저장 → 조회 복원
    res = _request(
        "PUT", "/api/v2/account/last-subject",
        json={"subject_id": subject_id}, headers=_auth(owner),
    )
    assert res.status_code == 200
    res = _request("GET", "/api/v2/account/last-subject", headers=_auth(owner))
    assert res.json()["subject_id"] == subject_id
    # 해제(null)
    res = _request(
        "PUT", "/api/v2/account/last-subject", json={"subject_id": None}, headers=_auth(owner)
    )
    assert res.status_code == 200
    assert _request("GET", "/api/v2/account/last-subject", headers=_auth(owner)).json()[
        "subject_id"
    ] is None


@pytest.mark.skipif(not _db_available(), reason="전용 DB(saju-v2-db) 미기동")
def test_last_subject_rejects_foreign_subject() -> None:
    owner_a = f"ls-{uuid.uuid4().hex[:8]}"
    owner_b = f"ls-{uuid.uuid4().hex[:8]}"
    subject_b = _create_subject(owner_b)
    res = _request(
        "PUT", "/api/v2/account/last-subject",
        json={"subject_id": subject_b}, headers=_auth(owner_a),
    )
    assert res.status_code == 403


@pytest.mark.skipif(not _db_available(), reason="전용 DB(saju-v2-db) 미기동")
def test_last_subject_deleted_subject_returns_null() -> None:
    owner = f"ls-{uuid.uuid4().hex[:8]}"
    subject_id = _create_subject(owner)
    _request(
        "PUT", "/api/v2/account/last-subject",
        json={"subject_id": subject_id}, headers=_auth(owner),
    )
    res = _request("DELETE", f"/api/v2/subjects/{subject_id}", headers=_auth(owner))
    assert res.status_code in (200, 204)
    # FK ON DELETE SET NULL + 조회측 소유·존재 검증 이중 방어
    res = _request("GET", "/api/v2/account/last-subject", headers=_auth(owner))
    assert res.json()["subject_id"] is None


def test_last_subject_requires_auth() -> None:
    res = _request("GET", "/api/v2/account/last-subject")
    assert res.status_code == 401

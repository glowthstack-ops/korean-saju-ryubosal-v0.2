"""계정/사주/프로필/페르소나 API 검증 (v2.2 프론트 확장 Phase 1).

- 토큰 서명·검증, PIN 해시는 DB 없이 단위 검증한다.
- 인증 게이트(401)는 DB 없이 검증한다.
- CRUD(등록→로그인→사주 생성→프로필 저장→페르소나)는 전용 DB(saju-v2-db, 5433)가
  떠 있을 때만 실행한다(없으면 skip). 토큰별 owner_id 격리를 함께 확인한다.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.deps import make_token, parse_token
from saju_api.main import app
from saju_engines.auth_store import _hash_pin, _verify_pin
from saju_engines.precompute_store import default_dsn

_TEST_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def _db_available() -> bool:
    """전용 DB 기동 여부 — 미기동 시 CRUD 테스트 skip."""
    try:
        from saju_engines.auth_store import AccountAuthStore

        AccountAuthStore(_TEST_DSN).migrate()
        return True
    except Exception:
        return False


# ── 토큰/해시 단위 검증 (DB 불필요) ─────────────────────────────


def test_token_roundtrip() -> None:
    token = make_token("alice")
    assert parse_token(token) == "alice"


def test_token_tampered_rejected() -> None:
    token = make_token("alice")
    body, _sig = token.split(".", 1)
    forged = f"{body}.deadbeef"
    assert parse_token(forged) is None
    assert parse_token("garbage") is None


def test_pin_hash_verifies() -> None:
    stored = _hash_pin("1234")
    assert stored.count("$") == 2
    assert _verify_pin("1234", stored)
    assert not _verify_pin("9999", stored)


# ── 인증 게이트 (DB 불필요) ─────────────────────────────────────


def test_subjects_requires_auth() -> None:
    r = _request("GET", "/api/v2/subjects")
    assert r.status_code == 401


def test_account_persona_requires_auth() -> None:
    r = _request("GET", "/api/v2/account/persona")
    assert r.status_code == 401


def test_credentials_validate_pin_format() -> None:
    # Credentials 모델: 숫자 4~12자만 허용, 영문/짧은 PIN은 거부(DB 비의존 계약 검증).
    from pydantic import ValidationError

    from saju_shared_types.account import Credentials

    Credentials(login_id="tester", pin="123456")  # ok
    for bad in ("abcd", "12", "123456789012345"):
        with pytest.raises(ValidationError):
            Credentials(login_id="tester", pin=bad)
    with pytest.raises(ValidationError):
        Credentials(login_id="no", pin="1234")  # login_id 3자 미만


# ── CRUD (전용 DB 필요 — 없으면 skip) ───────────────────────────

pytestmark_db = pytest.mark.skipif(not _db_available(), reason="전용 DB(5433) 미기동 — CRUD skip")

_BIRTH = {
    "calendar_type": "solar",
    "birth_date": "1990-05-05",
    "birth_time": "12:00",
    "birth_place_name": "서울",
    "gender": "male",
}


@pytestmark_db
def test_full_flow_register_subject_profile_persona() -> None:
    import uuid

    login_id = f"u{uuid.uuid4().hex[:10]}"
    # 등록 → 토큰
    r = _request("POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    # 재등록은 409
    assert _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).status_code == 409

    # 로그인 재검증
    r = _request("POST", "/api/v2/auth/login", json={"login_id": login_id, "pin": "123456"})
    assert r.status_code == 200
    assert r.json()["owner_id"] == login_id

    # 사주 생성
    r = _request(
        "POST", "/api/v2/subjects",
        headers=auth, json={"kind": "self", "label": "나", "birth": _BIRTH},
    )
    assert r.status_code == 201, r.text
    subject = r.json()
    sid = subject["subject_id"]
    assert subject["yongsin_registered"] is False
    assert subject["mulsang_registered"] is False

    # 목록에 노출(연속성)
    r = _request("GET", "/api/v2/subjects", headers=auth)
    assert r.status_code == 200
    assert any(s["subject_id"] == sid for s in r.json())

    # 프로필 저장(물상 + 확정 용신) → 인디케이터 True
    basic = {
        "birth_date": "1990-05-05", "calendar_type": "solar",
        "birth_place": {"city": "서울"}, "gender": "M", "display_name": "테스터",
    }
    extended = {"occupation": {"category_id": "O09"}}
    r = _request(
        "PUT", f"/api/v2/profile/{sid}",
        headers=auth,
        json={"basic": basic, "extended": extended, "confirmed_yongsin": "水"},
    )
    assert r.status_code == 200, r.text

    r = _request("GET", f"/api/v2/subjects/{sid}", headers=auth)
    assert r.json()["yongsin_registered"] is True
    assert r.json()["mulsang_registered"] is True

    # 확정 용신 전용 엔드포인트 — 프로필 행 없는 사주에서도 등록·목록 반영(만세력 검증 확정).
    sid2 = _request(
        "POST", "/api/v2/subjects", headers=auth,
        json={"kind": "self", "label": "용신만",
              "birth": {"calendar_type": "solar", "birth_date": "1988-08-08",
                        "birth_time": "08:08", "birth_place_name": "서울", "gender": "male"}},
    ).json()["subject_id"]
    # 프로필 저장 전인데 — yongsin 엔드포인트만으로 등록.
    r = _request("PUT", f"/api/v2/profile/{sid2}/yongsin", headers=auth,
                 json={"confirmed_yongsin": "木"})
    assert r.status_code == 200, r.text
    assert r.json()["confirmed_yongsin"] == "木"
    sub2 = _request("GET", f"/api/v2/subjects/{sid2}", headers=auth).json()
    assert sub2["yongsin_registered"] is True
    prof2 = _request("GET", f"/api/v2/profile/{sid2}", headers=auth).json()
    assert prof2["confirmed_yongsin"] == "木"
    # 해제(None)도 동작.
    _request("PUT", f"/api/v2/profile/{sid2}/yongsin", headers=auth,
             json={"confirmed_yongsin": None})
    sub2b = _request("GET", f"/api/v2/subjects/{sid2}", headers=auth).json()
    assert sub2b["yongsin_registered"] is False
    # 타 계정은 접근 불가(404).
    other_login = f"oy{uuid.uuid4().hex[:8]}"
    other = _request("POST", "/api/v2/auth/register",
                     json={"login_id": other_login, "pin": "111111"}).json()["token"]
    forbidden = _request("PUT", f"/api/v2/profile/{sid2}/yongsin",
                         headers={"Authorization": f"Bearer {other}"},
                         json={"confirmed_yongsin": "金"})
    assert forbidden.status_code == 404

    # 페르소나(계정 전역) 저장/조회
    r = _request(
        "PUT", "/api/v2/account/persona",
        headers=auth, json={"difficulty": "easy"},
    )
    assert r.status_code == 200
    assert r.json()["difficulty"] == "easy"

    # 무효 조합(호칭 '자네'=하게체 전용 + 반말체)은 저장 전 422로 거부되고
    # 기존 저장값은 유지된다(2026-08-21 실측 500 회귀 방지).
    r = _request(
        "PUT", "/api/v2/account/persona",
        headers=auth,
        json={
            "speech": {"politeness": "banmal", "style": "banmal_chae"},
            "user_honorific": {"type": "preset", "preset_id": "jane"},
        },
    )
    assert r.status_code == 422
    assert "페르소나 조합 무효" in r.json()["detail"]
    r = _request("GET", "/api/v2/account/persona", headers=auth)
    assert r.status_code == 200
    assert r.json()["difficulty"] == "easy"
    assert r.json()["user_honorific"]["preset_id"] != "jane"

    # 타 계정은 이 사주에 접근 불가(owner 격리)
    other = _request(
        "POST", "/api/v2/auth/register",
        json={"login_id": f"o{uuid.uuid4().hex[:10]}", "pin": "111111"},
    ).json()["token"]
    r = _request("GET", f"/api/v2/subjects/{sid}", headers={"Authorization": f"Bearer {other}"})
    assert r.status_code == 404

    # 정리: 삭제
    assert _request("DELETE", f"/api/v2/subjects/{sid}", headers=auth).status_code == 204

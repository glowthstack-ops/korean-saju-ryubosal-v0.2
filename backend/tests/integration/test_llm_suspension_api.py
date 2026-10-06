"""LLM 비용 소진 일시 중단 — 라우터 레벨 (2026-10-06, doc/v2_2/LLM_SERVICE_SUSPENSION.md).

- 채팅: 중단 중 새 질문은 pending 없이 즉시 status='suspended' 안내.
- 리포트 잡: 중단 중 신규 생성은 503(안내문), 잡 미생성.
- 관리자: 상태 조회·프로브 거부(409)·재개(200)·수동 중단.
- 공개 상태 엔드포인트(/api/v2/service/status) — 프론트 배너용.

DB 가 필요한 경로(인증·subjects·admin)는 테스트 DB 가 있을 때만 돈다. 상태 저장소는
메모리 백엔드로 격리해 운영/테스트 DB 의 상태 행을 건드리지 않는다.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.main import app
from saju_api.services import chat_service, llm_client, llm_service_state, report_service

_DB = pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"), reason="테스트 DB 미구성 — skip",
)

_BIRTH = {
    "calendar_type": "solar", "birth_date": "1990-05-05", "birth_time": "12:00",
    "birth_place_name": "서울", "gender": "male",
}
_SPEC = {
    "product_code": "RPT_FOCUS",
    "subjects": [{"kind": "self", "label": "본인"}],
    "topic": "career",
    "period": {"start": "2020-01", "end": "2030-12"},
}


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=120,
        ) as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


@pytest.fixture(autouse=True)
def _memory_state(monkeypatch: pytest.MonkeyPatch):
    llm_client.load_config(force=True)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    llm_service_state.use_memory_backend()
    yield
    llm_service_state.use_memory_backend()


def _probe(role: str, provider: str, ok: bool, kind: str | None = None) -> dict:
    return {"role": role, "provider": provider, "model": provider[0], "ok": ok,
            "kind": kind, "detail": "d" if not ok else ""}


def _register(prefix: str) -> tuple[str, dict[str, str]]:
    login_id = f"{prefix}{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"},
    ).json()["token"]
    return login_id, {"Authorization": f"Bearer {token}"}


def test_public_service_status_reflects_suspension() -> None:
    assert _request("GET", "/api/v2/service/status").json()["llm_service"]["state"] == "active"
    llm_service_state.suspend("quota_exhausted")
    body = _request("GET", "/api/v2/service/status").json()["llm_service"]
    assert body["state"] == "suspended" and body["reason"] == "quota_exhausted"
    assert set(body) == {"state", "reason", "suspended_at"}  # 공개 최소 필드


@_DB
def test_chat_while_suspended_returns_immediate_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """중단 중 비로그인 채팅 — pending 없이 suspended 안내, 공급자 호출 0건."""
    monkeypatch.setattr(chat_service.llm_client, "is_available", lambda: True)
    calls: list[str] = []

    def _no_call(*_a: Any, **_k: Any) -> str:
        calls.append("x")
        return "불가"

    monkeypatch.setattr(chat_service.llm_client, "generate_reading", _no_call)
    llm_service_state.suspend("quota_exhausted")
    r = _request("POST", "/api/v2/chat", json={
        "birth": _BIRTH, "question": "올해 이직운이 어때?", "today": "2026-10-06",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "suspended"
    assert body["answer"] == llm_service_state.SUSPENDED_USER_MESSAGE
    assert calls == []


@_DB
def test_chat_transition_during_sync_call_is_handled(monkeypatch: pytest.MonkeyPatch) -> None:
    """검사 시점엔 active 였으나 호출에서 중단이 전이된 경우도 같은 안내로 마감(500 아님)."""
    monkeypatch.setattr(chat_service.llm_client, "is_available", lambda: True)

    def _transition(*_a: Any, **_k: Any) -> str:
        llm_service_state.suspend("quota_exhausted")
        raise llm_client.LLMServiceSuspended("now")

    monkeypatch.setattr(chat_service.llm_client, "generate_reading", _transition)
    r = _request("POST", "/api/v2/chat", json={
        "birth": _BIRTH, "question": "올해 이직운이 어때?", "today": "2026-10-06",
    })
    assert r.status_code == 200 and r.json()["status"] == "suspended"


@_DB
def test_report_job_rejected_while_suspended(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_service.llm_client, "is_available", lambda: True)
    _login, auth = _register("s")
    sid = _request(
        "POST", "/api/v2/subjects",
        headers=auth, json={"kind": "self", "label": "나", "birth": _BIRTH},
    ).json()["subject_id"]
    try:
        llm_service_state.suspend("quota_exhausted")
        r = _request(
            "POST", "/api/v2/report/jobs", headers=auth, json={"subject_id": sid, "spec": _SPEC},
        )
        assert r.status_code == 503, r.text
        assert r.json()["detail"] == llm_service_state.SUSPENDED_REPORT_DETAIL
        listing = _request("GET", "/api/v2/report/jobs", headers=auth).json()
        assert listing == []  # 잡 미생성
    finally:
        _request("DELETE", f"/api/v2/subjects/{sid}", headers=auth)


@_DB
def test_admin_state_resume_and_suspend_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from saju_engines.auth_store import AccountAuthStore

    login_id, auth = _register("a")
    assert AccountAuthStore().set_admin(login_id, True)
    _other, user_auth = _register("u")

    # 비관리자 403.
    assert _request("GET", "/api/v2/admin/llm/state", headers=user_auth).status_code == 403

    llm_service_state.suspend("quota_exhausted")
    state = _request("GET", "/api/v2/admin/llm/state", headers=auth).json()
    assert state["state"] == "suspended" and "pending" in state and "providers_configured" in state

    # 프로브 전부 실패 → 409, 상태 유지.
    monkeypatch.setattr(llm_client, "probe_all", lambda: [
        _probe("primary", "gemini", False, "quota"),
    ])
    r = _request("POST", "/api/v2/admin/llm/resume", headers=auth)
    assert r.status_code == 409 and r.json()["detail"]["probes"][0]["kind"] == "quota"
    assert llm_service_state.current(force=True).is_suspended

    # 프로브 통과 → 200 재개, 응답에 클레임 레코드 원본은 포함하지 않는다.
    monkeypatch.setattr(llm_client, "probe_all", lambda: [
        _probe("primary", "gemini", True),
    ])
    r = _request("POST", "/api/v2/admin/llm/resume", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resumed"] is True and "claimed_jobs" not in body
    assert body["state"]["state"] == "active" and body["state"]["resumed_by"] == login_id
    assert not llm_service_state.current(force=True).is_suspended

    # 수동 중단.
    r = _request("POST", "/api/v2/admin/llm/suspend", headers=auth, json={"reason": "manual"})
    assert r.status_code == 200 and r.json()["suspended"] is True
    assert llm_service_state.current(force=True).reason == "manual"

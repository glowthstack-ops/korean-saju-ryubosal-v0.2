"""AI채팅상담 대화 영속화 API 검증 (목록·열람·삭제·권한).

- 인증 게이트(401)는 DB 없이 검증.
- 기록→목록→열람→삭제는 전용 DB(5433)가 있을 때만(없으면 skip). LLM은 호출하지 않고
  ChatHistoryStore로 턴을 직접 기록한 뒤 API로 조회/삭제한다.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.main import app
from saju_engines.precompute_store import default_dsn

_TEST_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def _db_available() -> bool:
    try:
        from saju_engines.chat_history_store import ChatHistoryStore

        ChatHistoryStore(_TEST_DSN).migrate()
        return True
    except Exception:
        return False


def test_threads_require_auth() -> None:
    assert _request("GET", "/api/v2/chat/threads").status_code == 401
    assert _request("GET", "/api/v2/chat/threads/x").status_code == 401
    assert _request("DELETE", "/api/v2/chat/threads/x").status_code == 401


pytestmark_db = pytest.mark.skipif(not _db_available(), reason="전용 DB(5433) 미기동 — skip")


@pytestmark_db
def test_thread_record_list_get_delete() -> None:
    import uuid

    from saju_engines.chat_history_store import ChatHistoryStore

    login_id = f"c{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    thread_id = f"t-{uuid.uuid4().hex[:8]}"
    store = ChatHistoryStore(_TEST_DSN)
    store.record_turn(login_id, thread_id, "본인", "올해 이직운 어때?", "변화 에너지가…",
                      meta={"status": "answered"})
    store.record_turn(login_id, thread_id, "본인", "그럼 하반기는?", "하반기에는…")

    # 목록
    threads = _request("GET", "/api/v2/chat/threads", headers=auth).json()
    mine = next((t for t in threads if t["thread_id"] == thread_id), None)
    assert mine is not None
    assert mine["title"] == "올해 이직운 어때?"
    assert mine["subject_label"] == "본인"
    assert mine["message_count"] == 4  # 2턴 × (user+assistant)

    # 열람(시간순, 역할 보존)
    msgs = _request("GET", f"/api/v2/chat/threads/{thread_id}", headers=auth).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["text"] == "올해 이직운 어때?"

    # 타 계정 접근 불가
    other = _request(
        "POST", "/api/v2/auth/register",
        json={"login_id": f"o{uuid.uuid4().hex[:10]}", "pin": "111111"},
    ).json()["token"]
    assert _request(
        "GET", f"/api/v2/chat/threads/{thread_id}",
        headers={"Authorization": f"Bearer {other}"},
    ).status_code == 404

    # 삭제 → 사라짐
    assert _request("DELETE", f"/api/v2/chat/threads/{thread_id}", headers=auth).status_code == 204
    threads2 = _request("GET", "/api/v2/chat/threads", headers=auth).json()
    assert all(t["thread_id"] != thread_id for t in threads2)


@pytestmark_db
def test_thread_partner_persisted_cross_device() -> None:
    """궁합 첨부가 스레드 상태에 미러링되어 GET /partner로 복원된다(크로스 디바이스)."""
    import uuid

    from saju_engines.chat_history_store import ChatHistoryStore

    login_id = f"p{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    thread_id = f"tp-{uuid.uuid4().hex[:8]}"
    # 소유 인식을 위해 히스토리에 1턴 시드(실사용의 비-dry_run 턴에 대응).
    ChatHistoryStore(_TEST_DSN).record_turn(login_id, thread_id, "본인", "q", "a")

    birth = {
        "calendar_type": "solar", "birth_date": "1980-11-22",
        "birth_time": "09:08", "birth_place_name": "서울", "gender": "male",
    }
    # 상대 첨부 + dry-run 턴(LLM 미호출) → 상태에 partner 미러링.
    r = _request("POST", "/api/v2/chat", headers=auth, json={
        "birth": birth, "question": "이 사람과 궁합 어때?", "today": "2026-06-11",
        "dry_run": True, "thread_id": thread_id,
        "partner_inline": {"date": "1985-03-15", "time": "14:30", "gender": "F"},
        "partner_label": "그사람",
    })
    assert r.status_code == 200, r.text

    got = _request("GET", f"/api/v2/chat/threads/{thread_id}/partner", headers=auth)
    assert got.status_code == 200, got.text
    partner = got.json()["partner"]
    assert partner is not None
    assert partner["mode"] == "inline" and partner["label"] == "그사람"
    assert partner["birth"]["date"] == "1985-03-15"

    # 타 계정은 접근 불가(404).
    other = _request(
        "POST", "/api/v2/auth/register",
        json={"login_id": f"o{uuid.uuid4().hex[:10]}", "pin": "111111"},
    ).json()["token"]
    assert _request(
        "GET", f"/api/v2/chat/threads/{thread_id}/partner",
        headers={"Authorization": f"Bearer {other}"},
    ).status_code == 404

    # 첨부 해제(상대 없이 1턴) → partner=None으로 미러링.
    r2 = _request("POST", "/api/v2/chat", headers=auth, json={
        "birth": birth, "question": "올해 재물운은?", "today": "2026-06-11",
        "dry_run": True, "thread_id": thread_id,
    })
    assert r2.status_code == 200, r2.text
    got2 = _request("GET", f"/api/v2/chat/threads/{thread_id}/partner", headers=auth)
    assert got2.json()["partner"] is None

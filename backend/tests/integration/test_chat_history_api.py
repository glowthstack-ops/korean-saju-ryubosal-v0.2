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


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return anyio.run(_run)


def _db_available() -> bool:
    try:
        from saju_engines.chat_history_store import ChatHistoryStore

        ChatHistoryStore().migrate()
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
    store = ChatHistoryStore()
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
def test_background_turn_pending_complete_seen() -> None:
    """백그라운드 생성 수명주기: start_turn(pending·미열람) → complete_turn(done) → 열람.

    클라이언트 이탈 후에도 답변이 서버에서 채워지고, 재진입(GET)으로 복구·열람되며
    미열람 완료 답변은 unseen_count/뱃지로 노출된다.
    """
    import uuid

    from saju_engines.chat_history_store import ChatHistoryStore

    login_id = f"b{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    thread_id = f"tb-{uuid.uuid4().hex[:8]}"
    store = ChatHistoryStore()
    msg_id = store.start_turn(login_id, thread_id, "본인", "올해 이직운 어때?",
                              meta={"candidate_count": 3})

    # 생성 중 — pending·미열람. 목록/카운트에 반영.
    pending = store.get_messages(thread_id)
    assert [m["role"] for m in pending] == ["user", "assistant"]
    assert pending[1]["status"] == "pending" and pending[1]["text"] == ""
    assert store.unseen_count(login_id) == 0  # pending은 아직 미열람 뱃지 대상 아님

    # 백그라운드 완료 → 본문·done.
    store.complete_turn(msg_id, "변화 에너지가 활성화되는 흐름이에요.", status="done")
    done = store.get_messages(thread_id)
    assert done[1]["status"] == "done"
    assert done[1]["text"].startswith("변화 에너지")
    assert done[1]["seen"] is False

    # 이탈 중이라 미열람 → 뱃지 카운트 1, 목록 has_unseen.
    assert store.unseen_count(login_id) == 1
    threads = _request("GET", "/api/v2/chat/threads", headers=auth).json()
    mine = next(t for t in threads if t["thread_id"] == thread_id)
    assert mine["has_unseen"] is True and mine["pending"] is False

    # 전역 뱃지 엔드포인트.
    assert _request("GET", "/api/v2/chat/unseen", headers=auth).json()["count"] == 1

    # 재진입(GET 스레드) → 열람 처리 → 뱃지 해제.
    msgs = _request("GET", f"/api/v2/chat/threads/{thread_id}", headers=auth).json()
    assert msgs[1]["status"] == "done"
    assert store.unseen_count(login_id) == 0
    assert _request("GET", "/api/v2/chat/unseen", headers=auth).json()["count"] == 0

    store.delete_thread(thread_id)


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
    ChatHistoryStore().record_turn(login_id, thread_id, "본인", "q", "a")

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

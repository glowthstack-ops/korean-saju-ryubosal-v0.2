"""POST /chat 접근 검증(보안 점검 S2·S3·S4) + 채팅 평가·지연 outcome 회수 API — 2026-10-24.

- 인증 게이트는 DB 없이 검증.
- 나머지는 전용 DB가 있을 때만(없으면 skip). LLM은 호출하지 않는다(dry_run / 직접 기록).
"""

from __future__ import annotations

import uuid
from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.main import app

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
        from saju_engines.chat_history_store import ChatHistoryStore

        ChatHistoryStore().migrate()
        return True
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(not _db_available(), reason="전용 DB 미기동 — skip")


def _register() -> tuple[str, dict[str, str]]:
    login_id = f"c{uuid.uuid4().hex[:10]}"
    token = _request(
        "POST", "/api/v2/auth/register", json={"login_id": login_id, "pin": "123456"}
    ).json()["token"]
    return login_id, {"Authorization": f"Bearer {token}"}


def _subject(auth: dict[str, str], label: str = "나") -> str:
    r = _request(
        "POST", "/api/v2/subjects", headers=auth,
        json={"kind": "self", "label": label, "birth": _BIRTH},
    )
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def test_followup_and_feedback_require_auth() -> None:
    assert _request("GET", "/api/v2/chat/followups?subject_id=x").status_code == 401
    assert _request("POST", "/api/v2/chat/followups/1", json={"subject_id": "x"}).status_code == 401
    assert _request(
        "POST", "/api/v2/chat/messages/1/feedback", json={"rating": "up"}
    ).status_code == 401


@pytestmark_db
def test_chat_rejects_foreign_subject_and_thread() -> None:
    from saju_engines.chat_history_store import ChatHistoryStore

    owner_a, auth_a = _register()
    sid_a = _subject(auth_a)
    _owner_b, auth_b = _register()
    thread_a = f"t-{uuid.uuid4().hex[:8]}"
    ChatHistoryStore().record_turn(
        owner_a, thread_a, "나", "올해 이직운?", "변화 에너지가…", subject_id=sid_a,
    )
    body = {"birth": _BIRTH, "question": "올해 이직운 어때?", "dry_run": True}

    # S3: 다른 소유자의 subject_id → 404 (비로그인도 404)
    r = _request("POST", "/api/v2/chat", headers=auth_b, json={**body, "subject_id": sid_a})
    assert r.status_code == 404, r.text
    r = _request("POST", "/api/v2/chat", json={**body, "subject_id": sid_a})
    assert r.status_code == 404, r.text
    # S2: 다른 소유자의 thread_id → 404 (비로그인도 404)
    r = _request("POST", "/api/v2/chat", headers=auth_b, json={**body, "thread_id": thread_a})
    assert r.status_code == 404, r.text
    r = _request("POST", "/api/v2/chat", json={**body, "thread_id": thread_a})
    assert r.status_code == 404, r.text
    # 소유자 본인은 통과(dry_run)
    r = _request(
        "POST", "/api/v2/chat", headers=auth_a,
        json={**body, "thread_id": thread_a, "subject_id": sid_a},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dry_run"


@pytestmark_db
def test_chat_rejects_thread_bound_to_other_subject() -> None:
    """S4: 같은 계정이라도 스레드가 다른 명식에 묶여 있으면 409."""
    from saju_engines.chat_history_store import ChatHistoryStore

    owner, auth = _register()
    sid_x = _subject(auth, "나")
    sid_y = _subject(auth, "아이")
    thread = f"t-{uuid.uuid4().hex[:8]}"
    ChatHistoryStore().record_turn(owner, thread, "나", "질문", "답", subject_id=sid_x)
    body = {"birth": _BIRTH, "question": "올해 이직운 어때?", "dry_run": True, "thread_id": thread}
    r = _request("POST", "/api/v2/chat", headers=auth, json={**body, "subject_id": sid_y})
    assert r.status_code == 409, r.text
    r = _request("POST", "/api/v2/chat", headers=auth, json={**body, "subject_id": sid_x})
    assert r.status_code == 200, r.text
    # 목록에 바인딩 명식이 실린다(프론트 이어보기 복원 근거)
    threads = _request("GET", "/api/v2/chat/threads", headers=auth).json()
    mine = next(t for t in threads if t["thread_id"] == thread)
    assert mine["subject_id"] == sid_x


@pytestmark_db
def test_followup_prompt_submit_and_feedback() -> None:
    from saju_engines.chat_history_store import ChatHistoryStore
    from saju_engines.life_event_store import LifeEventStore

    owner, auth = _register()
    sid = _subject(auth)
    thread = f"t-{uuid.uuid4().hex[:8]}"
    store = ChatHistoryStore()
    followup = [
        {"event_key": "relocation", "event_ko": "이사", "period": "2024-01", "score": 60,
         "fingerprint": {"ten_god_groups": ["wealth"], "palace": "day_pillar"}},
        {"event_key": "job_change", "event_ko": "이직", "period": "2099", "score": 40,
         "fingerprint": {}},
    ]
    store.record_turn(
        owner, thread, "나", "이사 언제?", "2024년 1월에…",
        meta={"status": "answered", "subject_id": sid, "followup": followup}, subject_id=sid,
    )
    msgs = _request("GET", f"/api/v2/chat/threads/{thread}", headers=auth).json()
    assert all(isinstance(m["id"], int) for m in msgs)
    assistant_id = msgs[-1]["id"]

    # 평가(소스 ②) — 메타에만 기록
    r = _request(
        "POST", f"/api/v2/chat/messages/{assistant_id}/feedback", headers=auth,
        json={"rating": "up", "note": " 실제로 이사했어요 "},
    )
    assert r.status_code == 204, r.text
    msgs = _request("GET", f"/api/v2/chat/threads/{thread}", headers=auth).json()
    assert msgs[-1]["meta"]["feedback"]["rating"] == "up"
    assert msgs[-1]["meta"]["feedback"]["note"] == "실제로 이사했어요"
    # 타 계정은 평가 불가
    _o, auth_b = _register()
    assert _request(
        "POST", f"/api/v2/chat/messages/{assistant_id}/feedback", headers=auth_b,
        json={"rating": "down"},
    ).status_code == 404

    # 후속 확인(소스 ③) — 지난 기간(2024-01)만 묻고 2099는 아직 열려 있어 제외
    r = _request("GET", f"/api/v2/chat/followups?subject_id={sid}", headers=auth)
    assert r.status_code == 200, r.text
    prompt = r.json()
    assert prompt["message_id"] == assistant_id
    assert [c["period"] for c in prompt["candidates"]] == ["2024-01"]
    assert "2024년 1월" in prompt["question"] and "'이사'" in prompt["question"]
    # 타 계정의 명식으로는 404
    assert _request(
        "GET", f"/api/v2/chat/followups?subject_id={sid}", headers=auth_b
    ).status_code == 404

    r = _request(
        "POST", f"/api/v2/chat/followups/{assistant_id}", headers=auth,
        json={"subject_id": sid, "answers": [
            {"event_key": "relocation", "period": "2024-01", "outcome": "confirmed"},
            # 열린 기간(2099)은 아직 묻지 않으므로 무시된다
            {"event_key": "job_change", "period": "2099", "outcome": "confirmed"},
        ]},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"stored": 1, "confirmed": 1, "not_happened": 0}
    rows = LifeEventStore().subject_signature(owner, sid)
    assert [(x.event_key, x.period, str(x.source), str(x.outcome)) for x in rows] == [
        ("relocation", "2024-01", "delayed_outcome", "confirmed"),
    ]
    assert rows[0].signal_fingerprint.ten_god_groups == ["wealth"]
    # 응답 후에는 다시 묻지 않는다
    assert _request(
        "GET", f"/api/v2/chat/followups?subject_id={sid}", headers=auth
    ).json()["message_id"] is None

    # 수집 상태(P2·P3 근거)
    st = _request("GET", f"/api/v2/reality-calibration/{sid}/status", headers=auth).json()
    assert st["has_events"] is True and st["confirmed"] == 1 and st["suggested_mode"] is None


@pytestmark_db
def test_subject_delete_purges_dependent_rows() -> None:
    """S7: 명식 삭제 시 프로필·확정 용신·사건 행이 함께 지워진다."""
    from saju_engines.life_event_store import LifeEventStore
    from saju_engines.profile_store import ProfileStore

    owner, auth = _register()
    sid = _subject(auth)
    basic = {
        "birth_date": "1990-05-05", "calendar_type": "solar",
        "birth_place": {"city": "서울"}, "gender": "M", "display_name": "테스터",
    }
    r = _request(
        "PUT", f"/api/v2/profile/{sid}", headers=auth,
        json={"basic": basic, "extended": {"occupation": {"category_id": "O09"}}},
    )
    assert r.status_code in (200, 201), r.text
    assert _request(
        "PUT", f"/api/v2/profile/{sid}/yongsin", headers=auth, json={"element": "fire"}
    ).status_code in (200, 204)
    store = LifeEventStore()
    from saju_shared_types.life_event import (
        LifeEventOutcome,
        LifeEventRow,
        LifeEventSource,
    )
    store.append_rows([LifeEventRow(
        event_row_id=f"{sid}:2024:relocation", subject_id=sid, owner_id=owner,
        pillar_year="庚午", pillar_month="辛巳", pillar_day="甲子", event_key="relocation",
        period="2024", outcome=LifeEventOutcome.CONFIRMED,
        source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
    )])
    assert ProfileStore().load(sid) is not None
    assert _request("DELETE", f"/api/v2/subjects/{sid}", headers=auth).status_code == 204
    assert ProfileStore().load(sid) is None
    assert ProfileStore().get_yongsin(sid) is None
    assert store.subject_signature(owner, sid) == []

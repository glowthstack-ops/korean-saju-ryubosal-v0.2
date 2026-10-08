"""답변 후처리 경로 통일 회귀(2026-10-01) — 동기·비동기(백그라운드)·비로그인 경로가 같은 후처리를
거친다.

배경: 로그인 베타(백그라운드)·비로그인 경로는 라우터가 LLM을 직접 호출해 chat_service 의 후처리
(커리어
출력 감사·관계 주장 패치·월 커버리지·정책 문구 제거·간지 병기·겉/속 거짓 역접 재작성)를 전혀 거치지
않았다. prep(dry-run) 응답에 `postprocess` 맥락(비직렬화)을 실어 라우터가 `finalize_answer_full` 로
넘기도록 통일했다.
"""

from __future__ import annotations

import inspect
from datetime import date, time

from saju_api.routers import chat as chat_router
from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time=time(9, 8), birth_place_name="서울", gender="male",
)
_T = date(2026, 10, 1)


def _prep() -> chat_service.ChatResponse:
    res = chat_service.chat(_BIRTH, "내 10월 금전 운세는 어때?", _T, dry_run=True)
    assert res.status == "dry_run"
    return res


def test_dry_run_carries_postprocess_context_but_never_serializes_it() -> None:
    res = _prep()
    assert res.postprocess is not None
    assert res.postprocess.payload.event_candidates  # 월 커버리지·관계 패치가 읽는 payload
    assert res.postprocess.prompt_text == (res.prompt_preview or "")
    dumped = res.model_dump()
    assert "postprocess" not in dumped  # 클라이언트 응답에 내부 맥락 미노출


def test_finalize_full_without_context_equals_text_only() -> None:
    text = "己亥 일주는 겉으로는 다정하지만 내면에는 영리함을 갖춘 구조입니다."
    full = chat_service.finalize_answer_full(text, None, "t")
    assert full == chat_service.finalize_answer_text(text, "t")


def test_finalize_full_with_real_context_runs_all_audits() -> None:
    res = _prep()
    text = (
        "데굴님, 10월의 금전운은 유리한 흐름입니다. 데굴님의 己亥(기해) 일주는 겉으로는 다정하고 "
        "부드럽지만 내면에는 실속을 갖춘 구조입니다."
    )
    out = chat_service.finalize_answer_full(text, res.postprocess, res.thread_id)
    assert "부드럽고, 내면에는" in out  # 텍스트 후처리까지 도달
    assert "10월의 금전운은 유리한 흐름" in out  # 감사가 본문을 깨지 않음


def test_router_paths_call_full_postprocess() -> None:
    """라우터의 백그라운드·비로그인 경로가 모두 finalize_answer_full 을 호출한다(회귀 가드)."""
    bg = inspect.getsource(chat_router._run_chat_answer)
    assert "finalize_answer_full(answer, postprocess, thread_id)" in bg
    sync = inspect.getsource(chat_router.chat)
    assert "finalize_answer_full(answer, prep.postprocess, req.thread_id)" in sync
    assert "prep.postprocess," in sync  # 백그라운드 태스크 인자로 전달

"""대화형 통변 엔드포인트 (v2.2 — 단일 질문 → 풀이 + 대화 영속화).

로그인 사용자의 대화는 스레드별로 자동 저장되어 목록 열람·이어가기·삭제가 가능하다
(비로그인 호출은 저장하지 않음). 저장은 라우터(서비스 부수효과 계층)에서 수행한다.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.chat_history_store import ChatHistoryStore
from saju_engines.conversation_store import ConversationStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.profile import PersonaConfig

from ..deps import get_chat_history_store, optional_owner, require_owner
from ..services import chat_service

router = APIRouter(prefix="/api/v2/chat", tags=["chat"])

OwnerId = Annotated[str, Depends(require_owner)]
OptionalOwner = Annotated[str | None, Depends(optional_owner)]
History = Annotated[ChatHistoryStore, Depends(get_chat_history_store)]


class ChatRequest(BaseModel):
    """질문 + 대상 출생 정보. dry_run=True면 LLM 미호출(입력 본문 미리보기)."""

    birth: BirthInput
    question: str = Field(min_length=1, max_length=2_000)
    today: date | None = None
    dry_run: bool = False
    thread_id: str | None = None  # 지정 시 멀티턴(스레드 상태 복원·갱신)
    persona: PersonaConfig | None = None  # 문체 전용(docs/11 — 점수·판정 불변)
    subject_label: str | None = None  # 대화 기준 사주 별명(저장 표시용)
    subject_id: str | None = None  # 저장된 사주 id — 개인화(현실 신호 시그니처·코호트, 소유자 검증)


class ChatThreadSummary(BaseModel):
    """대화 스레드 목록 항목."""

    thread_id: str
    subject_label: str | None = None
    title: str | None = None
    updated_at: str | None = None
    message_count: int


class ChatMessage(BaseModel):
    """저장된 메시지 1건."""

    role: str
    text: str
    meta: dict | None = None
    created_at: str | None = None


@router.post("", response_model=chat_service.ChatResponse)
def chat(
    req: ChatRequest,
    owner_id: OptionalOwner,
    history: History,
) -> chat_service.ChatResponse:
    """단일 질문 풀이 — 파서→플래너→스코어링→그래프→축소→LLM(또는 dry-run).

    로그인 사용자 + 실제 답변(dry-run 아님)일 때 질문/답변을 스레드에 자동 저장한다.
    """
    res = chat_service.chat(
        req.birth, req.question, req.today, req.dry_run,
        thread_id=req.thread_id, persona=req.persona,
        owner_id=owner_id, subject_id=req.subject_id,
    )
    if owner_id and not req.dry_run and req.thread_id and res.answer:
        try:
            history.record_turn(
                owner_id, req.thread_id, req.subject_label, req.question, res.answer,
                meta={"status": res.status, "candidate_count": res.candidate_count},
            )
        except Exception:  # noqa: BLE001 — 저장 실패가 응답을 막지 않도록
            pass
    return res


@router.get("/threads", response_model=list[ChatThreadSummary])
def list_threads(owner_id: OwnerId, history: History) -> list[ChatThreadSummary]:
    """내 대화 목록(최신순)."""
    return [ChatThreadSummary(**t) for t in history.list_threads(owner_id)]


@router.get("/threads/{thread_id}", response_model=list[ChatMessage])
def get_thread(thread_id: str, owner_id: OwnerId, history: History) -> list[ChatMessage]:
    """스레드 메시지 전문(이어가기·열람용, 소유자 한정)."""
    if history.owner_of(thread_id) != owner_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return [ChatMessage(**m) for m in history.get_messages(thread_id)]


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str, owner_id: OwnerId, history: History) -> None:
    """스레드 삭제(메시지 + 오케스트레이터 상태). 소유자 한정."""
    if history.owner_of(thread_id) != owner_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    history.delete_thread(thread_id)
    try:
        ConversationStore().delete(thread_id)
    except Exception:  # noqa: BLE001 — 상태 삭제 실패는 무시(전문은 이미 삭제)
        pass

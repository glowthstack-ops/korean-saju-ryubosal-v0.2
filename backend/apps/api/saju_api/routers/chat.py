"""대화형 통변 엔드포인트 (v2.2 MVP — 단일 질문 → 풀이)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from saju_shared_types.birth_input import BirthInput

from ..services import chat_service

router = APIRouter(prefix="/api/v2/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """질문 + 대상 출생 정보. dry_run=True면 LLM 미호출(입력 본문 미리보기)."""

    birth: BirthInput
    question: str = Field(min_length=1, max_length=2_000)
    today: date | None = None
    dry_run: bool = False
    thread_id: str | None = None  # 지정 시 멀티턴(스레드 상태 복원·갱신)


@router.post("", response_model=chat_service.ChatResponse)
def chat(req: ChatRequest) -> chat_service.ChatResponse:
    """단일 질문 풀이 — 파서→플래너→스코어링→그래프→축소→LLM(또는 dry-run)."""
    return chat_service.chat(
        req.birth, req.question, req.today, req.dry_run, thread_id=req.thread_id
    )

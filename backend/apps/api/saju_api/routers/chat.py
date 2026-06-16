"""대화형 통변 엔드포인트 (v2.2 — 단일 질문 → 풀이 + 대화 영속화).

로그인 사용자의 대화는 스레드별로 자동 저장되어 목록 열람·이어가기·삭제가 가능하다
(비로그인 호출은 저장하지 않음). 저장은 라우터(서비스 부수효과 계층)에서 수행한다.
"""

from __future__ import annotations

import contextlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.chat_history_store import ChatHistoryStore
from saju_engines.conversation_store import ConversationStore
from saju_engines.profile_store import ProfileStore
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth
from saju_shared_types.profile import PersonaConfig

from ..deps import get_chat_history_store, get_subject_store, optional_owner, require_owner
from ..services import chat_service
from ..services.partner_resolve import inline_to_birth

router = APIRouter(prefix="/api/v2/chat", tags=["chat"])

OwnerId = Annotated[str, Depends(require_owner)]
OptionalOwner = Annotated[str | None, Depends(optional_owner)]
History = Annotated[ChatHistoryStore, Depends(get_chat_history_store)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]


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
    # 궁합(pairwise) — 상대 첨부. 등록 동반자(id) 또는 즉석 입력 중 하나.
    partner_subject_id: str | None = None
    partner_inline: InlineBirth | None = None
    partner_label: str | None = None


class ChatThreadSummary(BaseModel):
    """대화 스레드 목록 항목."""

    thread_id: str
    subject_label: str | None = None
    title: str | None = None
    updated_at: str | None = None
    message_count: int
    has_unseen: bool = False  # 미열람 완료 답변 존재(이탈 후 복구 뱃지)
    pending: bool = False  # 생성 중인 답변 존재


class ChatMessage(BaseModel):
    """저장된 메시지 1건."""

    role: str
    text: str
    meta: dict | None = None
    created_at: str | None = None
    status: str = "done"  # 'done' | 'pending' | 'error'
    seen: bool = True


class UnseenCount(BaseModel):
    """미열람 완료 답변이 있는 스레드 수(전역 뱃지용)."""

    count: int


def _resolve_chat_partner(
    req: ChatRequest, subjects: SubjectStore, owner_id: str | None,
) -> BirthInput | None:
    """채팅 궁합 — 첨부 상대를 BirthInput으로 해석(즉석 입력 우선, 등록 동반자는 소유자 검증)."""
    if req.partner_inline is not None:
        return inline_to_birth(req.partner_inline)
    if req.partner_subject_id and owner_id:
        rec = subjects.get(req.partner_subject_id)
        if rec is not None and rec.owner_id == owner_id:
            return rec.birth
    return None


def _partner_ref(req: ChatRequest) -> dict | None:
    """첨부 상대를 프론트 ChatPartner 형태 dict로 — 스레드 상태 미러링(재개 복원용)."""
    if req.partner_inline is not None:
        return {
            "mode": "inline", "label": req.partner_label or "상대",
            "birth": req.partner_inline.model_dump(mode="json"),
        }
    if req.partner_subject_id:
        return {
            "mode": "registered", "subjectId": req.partner_subject_id,
            "label": req.partner_label or "상대",
        }
    return None


def _employment_form(subject_id: str | None) -> str | None:
    """대상 사주의 고용형태(2단계 프로필, 선택) — '직장운' 취업 포함 판정용. 부재·무DB면 None.

    프로필은 선택 입력이므로(규칙11) 조회 실패는 조용히 None으로 강등한다.
    """
    if not subject_id:
        return None
    with contextlib.suppress(Exception):
        profile = ProfileStore().load(subject_id)
        if profile and profile.extended and profile.extended.occupation:
            return profile.extended.occupation.employment_form
    return None


def _run_chat_answer(
    history: ChatHistoryStore,
    message_id: int,
    owner_id: str,
    thread_id: str,
    prompt: str,
    call_type: str,
    system: str | None,
) -> None:
    """백그라운드 LLM 생성 → 예약된 pending 답변에 본문 채움(연결 독립).

    클라이언트가 질문 직후 이탈/새로고침해도 답변은 끝까지 생성·영속된다.
    생성된 Gemini 결과를 버리지 않으며(비용 낭비 방지), 실패 시 status='error'로 안내문 저장.
    """
    try:
        answer = chat_service.llm_client.generate_reading(
            prompt, call_type=call_type, system=system,
            owner_id=owner_id, surface="chat", ref_id=thread_id,
        )
        history.complete_turn(message_id, answer, status="done")
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 사용자 안내문으로 마감
        history.complete_turn(
            message_id,
            "답변 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.",
            status="error",
            meta={"error": str(exc)[:300]},
        )


@router.post("", response_model=chat_service.ChatResponse)
def chat(
    req: ChatRequest,
    owner_id: OptionalOwner,
    history: History,
    subjects: Subjects,
    background: BackgroundTasks,
) -> chat_service.ChatResponse:
    """단일 질문 풀이 — 파서→플래너→스코어링→그래프→축소→LLM(또는 dry-run).

    로그인 사용자의 LLM 답변은 **백그라운드로 생성**한다(status='pending' 반환). 클라이언트가
    질문 직후 이탈해도 답변은 서버에서 끝까지 만들어 스레드에 저장되며, 프론트는 폴링으로
    복구하고 미열람 완료 답변은 뱃지로 알린다. 정책·범위 응답(즉시) 및 비로그인은 동기 처리.
    상대(궁합)가 첨부되면 두 명식 궁합 신호를 입력에 더해 pairwise로 답한다.
    """
    partner_birth = _resolve_chat_partner(req, subjects, owner_id)

    def _classify(dry: bool) -> chat_service.ChatResponse:
        return chat_service.chat(
            req.birth, req.question, req.today, dry,
            thread_id=req.thread_id, persona=req.persona,
            owner_id=owner_id, subject_id=req.subject_id,
            subject_label=req.subject_label or "회원",
            partner_birth=partner_birth, partner_label=req.partner_label or "상대",
            partner_ref=_partner_ref(req),
            employment_form=_employment_form(req.subject_id),
        )

    # 미리보기 요청은 예전처럼 동기 dry-run(LLM 미호출).
    if req.dry_run:
        return _classify(True)

    # 빠른 분류·프롬프트 구성(LLM 미호출) — 이후 생성은 prep을 재사용(파이프라인 중복 없음).
    prep = _classify(True)
    llm_ready = chat_service.llm_client.is_available()
    is_llm_path = prep.status == "dry_run"  # 정책/범위/need_subject는 이미 answer 보유

    # 로그인 + 스레드 + LLM 경로 → 백그라운드 생성 + 폴링 복구.
    if owner_id and req.thread_id and is_llm_path and llm_ready:
        message_id = history.start_turn(
            owner_id, req.thread_id, req.subject_label, req.question,
            meta={"candidate_count": prep.candidate_count},
        )
        background.add_task(
            _run_chat_answer, history, message_id, owner_id, req.thread_id,
            prep.prompt_preview or "", prep.call_type or "chat_single", prep.system_prompt,
        )
        return chat_service.ChatResponse(
            status="pending", thread_id=req.thread_id, message_id=message_id,
            intents=prep.intents, candidate_count=prep.candidate_count,
            turn_no=prep.turn_no,
        )

    # 비로그인/스레드 없음 — prep을 재사용해 동기 생성(영속화 불가).
    if is_llm_path and llm_ready:
        answer = chat_service.llm_client.generate_reading(
            prep.prompt_preview or "", call_type=prep.call_type or "chat_single",
            system=prep.system_prompt, owner_id=owner_id, surface="chat",
            ref_id=req.thread_id,
        )
        prep = prep.model_copy(update={"status": "answered", "answer": answer})

    # 정책/범위/need_subject(즉시 응답) — 로그인+스레드면 동기 영속화.
    if owner_id and req.thread_id and prep.answer:
        try:
            history.record_turn(
                owner_id, req.thread_id, req.subject_label, req.question, prep.answer,
                meta={"status": prep.status, "candidate_count": prep.candidate_count},
            )
        except Exception:  # noqa: BLE001 — 저장 실패가 응답을 막지 않도록
            pass
    return prep


@router.get("/threads", response_model=list[ChatThreadSummary])
def list_threads(owner_id: OwnerId, history: History) -> list[ChatThreadSummary]:
    """내 대화 목록(최신순)."""
    return [ChatThreadSummary(**t) for t in history.list_threads(owner_id)]


@router.get("/unseen", response_model=UnseenCount)
def unseen(owner_id: OwnerId, history: History) -> UnseenCount:
    """미열람 완료 답변이 있는 스레드 수(전역 뱃지) — 이탈 후 재진입 알림용."""
    return UnseenCount(count=history.unseen_count(owner_id))


@router.get("/threads/{thread_id}", response_model=list[ChatMessage])
def get_thread(thread_id: str, owner_id: OwnerId, history: History) -> list[ChatMessage]:
    """스레드 메시지 전문(이어가기·폴링·열람용, 소유자 한정).

    조회 시 완료된 미열람 답변을 열람 처리한다(뱃지 해제). pending은 그대로 두어
    프론트가 폴링을 계속하게 한다.
    """
    if history.owner_of(thread_id) != owner_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    messages = [ChatMessage(**m) for m in history.get_messages(thread_id)]
    with contextlib.suppress(Exception):
        history.mark_seen(thread_id)
    return messages


class ChatPartnerResponse(BaseModel):
    """스레드의 궁합 상대 첨부 상태(크로스 디바이스 재개 복원용)."""

    partner: dict | None = None


@router.get("/threads/{thread_id}/partner", response_model=ChatPartnerResponse)
def get_thread_partner(
    thread_id: str, owner_id: OwnerId, history: History,
) -> ChatPartnerResponse:
    """스레드에 첨부된 궁합 상대(있으면) — 다른 기기에서 이어볼 때 칩 복원용(소유자 한정)."""
    if history.owner_of(thread_id) != owner_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    try:
        state = ConversationStore().load(thread_id)
    except Exception:  # noqa: BLE001 — DB 미가용 등은 미첨부로 강등
        return ChatPartnerResponse(partner=None)
    return ChatPartnerResponse(partner=state.partner if state else None)


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

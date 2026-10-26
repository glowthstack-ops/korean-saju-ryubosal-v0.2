"""대화형 통변 엔드포인트 (v2.2 — 단일 질문 → 풀이 + 대화 영속화).

로그인 사용자의 대화는 스레드별로 자동 저장되어 목록 열람·이어가기·삭제가 가능하다
(비로그인 호출은 저장하지 않음). 저장은 라우터(서비스 부수효과 계층)에서 수행한다.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.chat_history_store import ChatHistoryStore
from saju_engines.companion_alias import AliasEntry, build_companion_alias_index
from saju_engines.conversation_store import ConversationStore
from saju_engines.life_event_followup import (
    FollowupAnswer,
    FollowupCandidate,
    elapsed_candidates,
    followup_question,
    resolve_fingerprints,
    rows_from_followup,
)
from saju_engines.life_event_store import LifeEventStore
from saju_engines.llm_guard import TokenBudgetExceeded
from saju_engines.profile_engine import profile_event_signals
from saju_engines.reality_calibration import pillars_signature
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import InlineBirth
from saju_shared_types.life_event import LifeEventOutcome
from saju_shared_types.profile import PersonaConfig

from ..deps import (
    get_chat_history_store,
    get_chat_history_store_optional,
    get_life_event_store,
    get_subject_store,
    get_subject_store_optional,
    optional_owner,
    require_owner,
)
from ..location import LocationResolveError
from ..services import chat_service, llm_service_state
from ..services.llm_client import LLMServiceSuspended
from ..services.manse_service import calculate
from ..services.partner_resolve import inline_to_birth

router = APIRouter(prefix="/api/v2/chat", tags=["chat"])

OwnerId = Annotated[str, Depends(require_owner)]
OptionalOwner = Annotated[str | None, Depends(optional_owner)]
History = Annotated[ChatHistoryStore, Depends(get_chat_history_store)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]
# POST /chat 전용 — DSN 미설정 배포에서도 dry-run·정책·익명 채팅이 동작하도록 optional.
# (로그인 데이터 경로 /threads 등은 위 엄격 버전을 그대로 사용해 DB 없으면 503.)
OptionalHistory = Annotated[ChatHistoryStore | None, Depends(get_chat_history_store_optional)]
OptionalSubjects = Annotated[SubjectStore | None, Depends(get_subject_store_optional)]


class ChatRequest(BaseModel):
    """질문 + 대상 출생 정보. dry_run=True면 LLM 미호출(입력 본문 미리보기)."""

    birth: BirthInput
    question: str = Field(min_length=1, max_length=2_000)
    today: date | None = None
    dry_run: bool = False
    thread_id: str | None = None  # 지정 시 멀티턴(스레드 상태 복원·갱신)
    persona: PersonaConfig | None = None  # 문체 전용(docs/11 — 점수·판정 불변)
    subject_label: str | None = None  # 대화 기준 사주 별명(저장 표시용)
    # 저장된 사주 id — 개인화(현실 신호 시그니처·코호트). 소유자 검증은 _assert_chat_access.
    subject_id: str | None = None
    # 궁합(pairwise) — 상대 첨부. 등록 동반자(id) 또는 즉석 입력 중 하나.
    partner_subject_id: str | None = None
    partner_inline: InlineBirth | None = None
    partner_label: str | None = None


class ChatThreadSummary(BaseModel):
    """대화 스레드 목록 항목."""

    thread_id: str
    subject_label: str | None = None
    subject_id: str | None = None  # 바인딩 명식(021) — 이어보기 시 프론트가 선택 명식을 복원
    title: str | None = None
    updated_at: str | None = None
    message_count: int
    has_unseen: bool = False  # 미열람 완료 답변 존재(이탈 후 복구 뱃지)
    pending: bool = False  # 생성 중인 답변 존재


class ChatMessage(BaseModel):
    """저장된 메시지 1건. `id`는 평가·후속 확인(delayed outcome)의 키."""

    id: int | None = None
    role: str
    text: str
    meta: dict | None = None
    created_at: str | None = None
    status: str = "done"  # 'done' | 'pending' | 'error'
    seen: bool = True


class UnseenCount(BaseModel):
    """미열람 완료 답변이 있는 스레드 수(전역 뱃지용)."""

    count: int


def _assert_chat_access(
    req: ChatRequest, owner_id: str | None,
    history: ChatHistoryStore | None, subjects: SubjectStore | None,
) -> None:
    """POST /chat 의 thread_id·subject_id 소유 검증(보안 점검 S2·S3·S4, 2026-10-24).

    - subject_id: 비로그인이거나 다른 소유자의 명식이면 404(프로필·확정 용신·캘리브레이션
      힌트가 타인 풀이에 적용되던 경로 차단).
    - thread_id: 다른 소유자의 스레드(비로그인→로그인 스레드 포함)면 404(상대 대화 상태·직전
      답이 프롬프트에 주입되고 내 턴이 상대 스레드에 기록되던 경로 차단).
    - 스레드가 다른 명식에 묶여 있으면 409(같은 계정에서 명식을 바꾼 뒤 이어보기 — 다른
      명식의 사용자 제공 사실이 주입되던 경로 차단). 미바인딩(레거시) 스레드는 이 턴에 묶인다.
    """
    if req.subject_id:
        if not owner_id or subjects is None:
            raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
        rec = subjects.get(req.subject_id)
        if rec is None or rec.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    if req.thread_id and history is not None:
        try:
            info = history.thread_info(req.thread_id)
        except Exception:  # noqa: BLE001 — 조회 실패는 서비스 계층의 상태 소유 검사에 맡긴다
            info = None
        if info is not None:
            if info["owner_id"] != owner_id:
                raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
            bound = info.get("subject_id")
            if bound and req.subject_id and bound != req.subject_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "이 대화는 다른 사주로 시작됐어요. "
                        "그 사주를 선택하거나 새 대화로 이어가 주세요."
                    ),
                )


def _resolve_chat_partner(
    req: ChatRequest, subjects: SubjectStore | None, owner_id: str | None,
) -> BirthInput | None:
    """채팅 궁합 — 첨부 상대를 BirthInput으로 해석(즉석 입력 우선, 등록 동반자는 소유자 검증).

    subjects가 None(무DB 배포)이면 등록 동반자 조회는 조용히 생략한다 — 즉석 입력(inline)은
    DB 없이도 동작하며, 전체 요청을 503으로 막지 않는다.
    """
    if req.partner_inline is not None:
        return inline_to_birth(req.partner_inline)
    if req.partner_subject_id and owner_id and subjects is not None:
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


def _user_meta(req: ChatRequest) -> dict | None:
    """질문(user) 메시지에 저장할 메타 — 첨부 동반자를 기록해 UI에서 질문별 표시.

    현재는 단일 동반자(partner)이나, n명 확장을 위해 companions 리스트도 함께 둔다.
    """
    ref = _partner_ref(req)
    if ref is None:
        return None
    return {"partner": ref, "companions": [ref.get("label", "상대")]}


def _followup_meta(prep: chat_service.ChatResponse, req: ChatRequest) -> dict:
    """답변 메시지 메타에 남길 후속 확인 후보(LIFE_EVENT_INFERENCE §4.1 ③).

    저장된 명식(subject_id)이 있어야 나중에 사건 행을 붙일 수 있다. 후보가 없으면 빈 dict.
    """
    ctx = prep.postprocess
    if not req.subject_id or ctx is None or not ctx.followup:
        return {}
    return {"subject_id": req.subject_id, "followup": ctx.followup}


def _last_assistant_answer(history: ChatHistoryStore | None, thread_id: str) -> str | None:
    """스레드의 가장 최근 완료된 assistant 답변 본문(없으면 None) — '그래 봐줘' 제안 이어보기용."""
    if history is None:
        return None
    try:
        msgs = history.get_messages(thread_id)
    except Exception:  # noqa: BLE001 — 이력 조회 실패가 답변을 막지 않도록
        return None
    for m in reversed(msgs):
        if (m.get("role") == "assistant" and m.get("status") == "done"
                and (m.get("text") or "").strip()):
            return m["text"]
    return None


def _run_chat_answer(
    history: ChatHistoryStore,
    message_id: int,
    owner_id: str,
    thread_id: str,
    prompt: str,
    call_type: str,
    system: str | None,
    postprocess: chat_service.ChatPostprocessContext | None = None,
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
        # 후처리 전체(커리어 출력 감사·관계 주장 패치·월 커버리지·텍스트 후처리) — 동기 경로와
        # 동일 계약. 이 경로는 chat_service 의 후처리를 전혀 지나지 않았다(2026-10-01 경로 통일).
        answer = chat_service.finalize_answer_full(answer, postprocess, thread_id)
        history.complete_turn(message_id, answer, status="done")
        # 답변 끝 제안(offer)을 스레드 상태에 반영 — 다음 턴 offer-slot 링킹의 근거.
        # 동기 경로 전용이던 갱신이 비동기 경로에서 누락돼 후속이 too_broad로 끊기던
        # 결함 교정(2026-07-21).
        chat_service.update_thread_offer(
            thread_id, answer,
            engine_slots=(postprocess.entry_slots_engine if postprocess is not None else None),
        )
    except TokenBudgetExceeded as exc:
        # 입력 상한 초과(2026-09-11 실로그 #650~654: 일반 오류문으로 3회 연속 종료) —
        # 오류가 아니라 범위 좁히기 안내로 마감한다. 한도 상수는 바꾸지 않는다(절대원칙 9).
        history.complete_turn(
            message_id, chat_service.TOKEN_BUDGET_ANSWER, status="done",
            meta={"error": str(exc)[:300]},
        )
        chat_service.update_thread_offer(thread_id, "")
    except LLMServiceSuspended as exc:
        # 비용 소진 일시 중단 — 중단 시점에 생성 중이던 답변은 재개 시 되살리지 않는다
        # (며칠 뒤 답해 봐야 사용자는 떠났다 — 데굴님 결정 2026-10-06). 사유를 meta 에 남긴다.
        history.complete_turn(
            message_id, llm_service_state.SUSPENDED_PENDING_MESSAGE, status="error",
            meta={"error": str(exc)[:300], "reason": "llm_suspended"},
        )
        chat_service.update_thread_offer(thread_id, "")
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 사용자 안내문으로 마감
        history.complete_turn(
            message_id,
            "답변 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.",
            status="error",
            meta={"error": str(exc)[:300]},
        )
        chat_service.update_thread_offer(thread_id, "")  # 이전 턴 offer 잔존 만료


@router.post("", response_model=chat_service.ChatResponse)
def chat(
    req: ChatRequest,
    owner_id: OptionalOwner,
    history: OptionalHistory,
    subjects: OptionalSubjects,
    background: BackgroundTasks,
) -> chat_service.ChatResponse:
    """단일 질문 풀이 — 파서→플래너→스코어링→그래프→축소→LLM(또는 dry-run).

    로그인 사용자의 LLM 답변은 **백그라운드로 생성**한다(status='pending' 반환). 클라이언트가
    질문 직후 이탈해도 답변은 서버에서 끝까지 만들어 스레드에 저장되며, 프론트는 폴링으로
    복구하고 미열람 완료 답변은 뱃지로 알린다. 정책·범위 응답(즉시) 및 비로그인은 동기 처리.
    상대(궁합)가 첨부되면 두 명식 궁합 신호를 입력에 더해 pairwise로 답한다.
    """
    _assert_chat_access(req, owner_id, history, subjects)
    partner_birth = _resolve_chat_partner(req, subjects, owner_id)

    # 등록 동반자 별칭 인덱스 — 발화 속 별명/관계어를 companion subject_id로 해소(P0).
    # owner isolation: owner_id 한정 조회 결과만 인덱스에 들어간다. 무DB 배포/비로그인은 빈 인덱스.
    alias_index: dict[str, list[AliasEntry]] = {}
    companion_births: dict[str, BirthInput] = {}
    if subjects is not None and owner_id:
        _records = subjects.list_all(owner_id)
        alias_index = build_companion_alias_index(_records, base_subject_id=req.subject_id)
        # P2a — 동반자 공동 풀이용 birth 맵(owner 한정). 현 FE 사주목록은 모든 사주를
        # kind='self'로 등록하므로(companion 등록 플로 미사용) kind로 거르지 않고 '기준
        # 사주 제외 전부'를 동반자 후보로 삼는다(2026-07-22 실측: 남편 레코드가 kind='self'
        # 라 birth 맵에서 빠져, 칩 첨부 부부 질문이 need_subject로 거부되던 결함).
        companion_births = {
            r.subject_id: r.birth
            for r in _records
            if r.subject_id != req.subject_id
        }

    form, occ_status, rel_status, occ_category = profile_event_signals(req.subject_id)

    # 직전 답변 — '그래 봐줘' 류 수락 시 LLM이 제시했던 제안을 이어 답하도록 전달(스레드 한정).
    prior_answer = _last_assistant_answer(history, req.thread_id) if req.thread_id else None

    def _classify(dry: bool) -> chat_service.ChatResponse:
        try:
            return _run_chat(dry)
        except chat_service.ThreadAccessDenied as exc:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.") from exc
        except LocationResolveError as exc:
            # 시드 미등록 지명 + 좌표 없음 — 입력 문제라 500이 아니라 422(2026-10-26).
            raise HTTPException(
                status_code=422,
                detail=f"출생지 '{req.birth.birth_place_name}'의 좌표를 확정할 수 없습니다. "
                "출생지 목록에서 선택하거나 위도·경도·시간대를 함께 보내 주세요.",
            ) from exc

    def _run_chat(dry: bool) -> chat_service.ChatResponse:
        return chat_service.chat(
            req.birth, req.question, req.today, dry,
            thread_id=req.thread_id, persona=req.persona,
            owner_id=owner_id, subject_id=req.subject_id,
            subject_label=req.subject_label or "회원",
            partner_birth=partner_birth, partner_label=req.partner_label or "상대",
            partner_ref=_partner_ref(req),
            employment_form=form,
            occupation_status=occ_status,
            relationship_status=rel_status,
            occupation_category=occ_category,
            prior_answer=prior_answer,
            companion_alias_index=alias_index,
            companion_births=companion_births,
        )

    # 미리보기 요청은 예전처럼 동기 dry-run(LLM 미호출).
    if req.dry_run:
        return _classify(True)

    # 빠른 분류·프롬프트 구성(LLM 미호출) — 이후 생성은 prep을 재사용(파이프라인 중복 없음).
    prep = _classify(True)
    llm_ready = chat_service.llm_client.is_available()
    is_llm_path = prep.status == "dry_run"  # 정책/범위/need_subject는 이미 answer 보유

    # 비용 소진 일시 중단 — pending 을 만들지 않고 즉시 안내한다(중단 중 질문은 큐에 넣지
    # 않는다 — 데굴님 결정 2026-10-06). 아래 즉시 응답 영속화 블록이 질문·안내문을 스레드에
    # 남긴다(정책 응답과 같은 경로).
    if is_llm_path and llm_ready and chat_service.llm_client.is_suspended():
        return _finish_immediate(
            prep.model_copy(update={
                "status": "suspended", "answer": llm_service_state.SUSPENDED_USER_MESSAGE,
            }),
            req, owner_id, history,
        )

    # 로그인 + 스레드 + LLM 경로 → 백그라운드 생성 + 폴링 복구(영속화엔 history 필수).
    if owner_id and req.thread_id and is_llm_path and llm_ready and history is not None:
        message_id = history.start_turn(
            owner_id, req.thread_id, req.subject_label, req.question,
            meta={"candidate_count": prep.candidate_count, **_followup_meta(prep, req)},
            user_meta=_user_meta(req),
            subject_id=req.subject_id,
        )
        background.add_task(
            _run_chat_answer, history, message_id, owner_id, req.thread_id,
            prep.prompt_preview or "", prep.call_type or "chat_single", prep.system_prompt,
            prep.postprocess,
        )
        return chat_service.ChatResponse(
            status="pending", thread_id=req.thread_id, message_id=message_id,
            intents=prep.intents, candidate_count=prep.candidate_count,
            turn_no=prep.turn_no,
        )

    # 비로그인/스레드 없음 — prep을 재사용해 동기 생성(영속화 불가).
    if is_llm_path and llm_ready:
        try:
            answer = chat_service.llm_client.generate_reading(
                prep.prompt_preview or "", call_type=prep.call_type or "chat_single",
                system=prep.system_prompt, owner_id=owner_id, surface="chat",
                ref_id=req.thread_id,
            )
        except LLMServiceSuspended:
            # 이 호출로 중단이 전이된 경우(직전 검사는 active 였다) — 같은 안내로 마감.
            return _finish_immediate(
                prep.model_copy(update={
                    "status": "suspended", "answer": llm_service_state.SUSPENDED_USER_MESSAGE,
                }),
                req, owner_id, history,
            )
        answer = chat_service.finalize_answer_full(answer, prep.postprocess, req.thread_id)
        prep = prep.model_copy(update={"status": "answered", "answer": answer})
        # 이 경로는 라우터가 답변을 직접 생성하므로 chat_service 의 offer 저장
        # 지점을 지나지 않는다 — 스레드가 있으면 여기서 갱신해야 다음 턴의
        # 되물음 답변이 링킹된다(2026-08-04: 배경 경로와 동일 계약).
        # 대화 상태 자체는 prep 단계에서 이미 영속화되어 있다(history 만 없다).
        if req.thread_id:
            chat_service.update_thread_offer(
                req.thread_id, answer,
                engine_slots=(
                    prep.postprocess.entry_slots_engine if prep.postprocess is not None else None
                ),
            )

    # 정책/범위/need_subject(즉시 응답) — 로그인+스레드+DB면 동기 영속화.
    return _finish_immediate(prep, req, owner_id, history)


def _finish_immediate(
    prep: chat_service.ChatResponse, req: ChatRequest, owner_id: str | None,
    history: ChatHistoryStore | None,
) -> chat_service.ChatResponse:
    """즉시 응답(정책/범위/need_subject/suspended/동기 생성) 마감 — 로그인+스레드+DB면 영속화."""
    if owner_id and req.thread_id and prep.answer and history is not None:
        try:
            history.record_turn(
                owner_id, req.thread_id, req.subject_label, req.question, prep.answer,
                meta={"status": prep.status, "candidate_count": prep.candidate_count},
                user_meta=_user_meta(req),
                subject_id=req.subject_id,
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


# ── 수집 소스 ②③(LIFE_EVENT_INFERENCE §4.1, 2026-10-24) — 채팅 평가 + 지연 outcome 회수 ──

LifeEvents = Annotated[LifeEventStore, Depends(get_life_event_store)]


class MessageFeedback(BaseModel):
    """답변 평가(👍/👎) + 선택 한 줄 메모 — 메시지 메타에만 기록(사건 행 없음)."""

    rating: Literal["up", "down"]
    note: str | None = Field(default=None, max_length=300)


class FollowupPrompt(BaseModel):
    """기간이 지난 답변 후보에 대한 후속 확인 질문(없으면 message_id=None)."""

    message_id: int | None = None
    thread_id: str | None = None
    asked_at: str | None = None
    title: str | None = None
    question: str = ""
    candidates: list[FollowupCandidate] = Field(default_factory=list)


class FollowupSubmission(BaseModel):
    """후속 확인 답 — 후보별 있었음/없었음/모름."""

    subject_id: str
    answers: list[FollowupAnswer] = Field(default_factory=list)


class FollowupSubmitResult(BaseModel):
    """적재 결과."""

    stored: int
    confirmed: int
    not_happened: int


def _calibration_engine():
    """지문 산출용 V2 엔진 — 캘리브레이션 라우터와 같은 인스턴스(싱글턴, 채점 전용)."""
    from .reality_calibration import _get_engine

    return _get_engine()


def _owned_message_thread(history: ChatHistoryStore, message_id: int, owner_id: str) -> str:
    """메시지 → 스레드 id(소유자 일치 강제, 아니면 404)."""
    thread_id = history.message_thread(message_id)
    if thread_id is None or history.owner_of(thread_id) != owner_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    return thread_id


@router.post("/messages/{message_id}/feedback", status_code=204)
def message_feedback(
    message_id: int, body: MessageFeedback, owner_id: OwnerId, history: History,
) -> None:
    """답변 평가 저장(소스 ②). 점수에는 쓰지 않고 후속 확인 우선순위·감수 자료로만 쓴다."""
    _owned_message_thread(history, message_id, owner_id)
    history.merge_message_meta(message_id, {
        "feedback": {
            "rating": body.rating,
            "note": (body.note or "").strip() or None,
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    })


@router.get("/followups", response_model=FollowupPrompt)
def next_followup(
    subject_id: str, owner_id: OwnerId, history: History, subjects: Subjects,
) -> FollowupPrompt:
    """이 명식의 답변 중 기간이 지난 후보가 있는 가장 최근 답변 1건의 후속 확인 질문(소스 ③).

    👍 평가가 있는 답변을 먼저 묻고, 그다음 최근 순. 후보 기간 판정은 절기 월운 라벨 기준.
    """
    rec = subjects.get(subject_id)
    if rec is None or rec.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    today = date.today()
    luck_month = chat_service._current_luck_month(today)
    rows = history.followup_messages(owner_id, subject_id)
    rows.sort(key=lambda r: 0 if (r["meta"].get("feedback") or {}).get("rating") == "up" else 1)
    for r in rows:
        cands = elapsed_candidates(
            list(r["meta"].get("followup") or []), current_luck_month=luck_month, today=today,
        )
        if cands:
            return FollowupPrompt(
                message_id=r["id"], thread_id=r["thread_id"], asked_at=r["created_at"],
                title=r["title"], question=followup_question(cands), candidates=cands,
            )
    return FollowupPrompt()


@router.post("/followups/{message_id}", response_model=FollowupSubmitResult)
def submit_followup(
    message_id: int, body: FollowupSubmission, owner_id: OwnerId, history: History,
    subjects: Subjects, life_events: LifeEvents,
) -> FollowupSubmitResult:
    """후속 확인 답을 `delayed_outcome` 행으로 적재하고 메시지를 응답 완료로 표시한다."""
    rec = subjects.get(body.subject_id)
    if rec is None or rec.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    thread_id = _owned_message_thread(history, message_id, owner_id)
    msg = next((m for m in history.get_messages(thread_id) if m.get("id") == message_id), None)
    meta = (msg or {}).get("meta") or {}
    if meta.get("subject_id") != body.subject_id:
        raise HTTPException(status_code=409, detail="이 답변은 다른 사주의 것이에요.")
    today = date.today()
    luck_month = chat_service._current_luck_month(today)
    cands = elapsed_candidates(
        list(meta.get("followup") or []), current_luck_month=luck_month, today=today,
    )
    chart = calculate(rec.birth.model_copy(update={"reference_date": today}))
    # 채팅 후보는 legacy 라 지문이 비어 있다 — 캘리브레이션 제출과 같은 규칙으로 여기서 산출.
    cands = resolve_fingerprints(
        cands, birth=rec.birth, engine=_calibration_engine(), calculate=calculate,
    )
    rows = rows_from_followup(
        subject_id=body.subject_id, owner_id=owner_id, pillars_sig=pillars_signature(chart),
        answers=body.answers, candidates=cands,
    )
    stored = life_events.append_rows(rows)
    history.merge_message_meta(message_id, {
        "followup_answered": {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "answers": [a.model_dump(mode="json") for a in body.answers],
        },
    })
    return FollowupSubmitResult(
        stored=stored,
        confirmed=sum(1 for r in rows if r.outcome is LifeEventOutcome.CONFIRMED),
        not_happened=sum(1 for r in rows if r.outcome is LifeEventOutcome.NOT_HAPPENED),
    )

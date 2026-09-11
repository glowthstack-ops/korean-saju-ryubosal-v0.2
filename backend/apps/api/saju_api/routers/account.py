"""계정 전역 설정(페르소나) 엔드포인트 (v2.2 프론트 확장 Phase 1).

페르소나는 계정당 1개(문체 전용, docs/11 5장). 미설정 시 기본값을 반환한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from saju_engines.account_store import AccountSettingsStore
from saju_engines.subject_store import SubjectStore
from saju_shared_types.profile import PersonaConfig

from ..deps import get_account_store, get_subject_store, require_owner

router = APIRouter(prefix="/api/v2/account", tags=["account"])

OwnerId = Annotated[str, Depends(require_owner)]
Accounts = Annotated[AccountSettingsStore, Depends(get_account_store)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]


class LastSubjectDTO(BaseModel):
    """마지막 선택 사주 — 없거나 무효면 null."""

    subject_id: str | None


@router.get("/persona", response_model=PersonaConfig)
def get_persona(owner_id: OwnerId, store: Accounts) -> PersonaConfig:
    """계정 페르소나 조회 — 미설정 시 기본값."""
    return store.get_persona(owner_id) or PersonaConfig()


@router.put("/persona", response_model=PersonaConfig)
def put_persona(persona: PersonaConfig, owner_id: OwnerId, store: Accounts) -> PersonaConfig:
    """계정 페르소나 저장/갱신 — 5-2 조합 제약(호칭↔politeness·style)을 저장 전에 검증한다.

    무효 조합을 그대로 저장하면 이후 모든 채팅이 build_block 에서 500이 난다
    (2026-08-21 실측: 'jane'+banmal_chae). 무효면 422로 거부한다.
    """
    from ..services.chat_service import _get_persona_engine

    validation = _get_persona_engine().validate(persona)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=f"페르소나 조합 무효: {validation.errors}")
    store.save_persona(owner_id, persona)
    return persona


@router.get("/last-subject", response_model=LastSubjectDTO)
def get_last_subject(
    owner_id: OwnerId, store: Accounts, subjects: Subjects
) -> LastSubjectDTO:
    """재로그인 복원용 마지막 선택 사주 — 삭제·타 소유 등 무효면 null."""
    subject_id = store.get_last_subject(owner_id)
    if subject_id is None:
        return LastSubjectDTO(subject_id=None)
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        return LastSubjectDTO(subject_id=None)
    return LastSubjectDTO(subject_id=subject_id)


@router.put("/last-subject", response_model=LastSubjectDTO)
def put_last_subject(
    body: LastSubjectDTO, owner_id: OwnerId, store: Accounts, subjects: Subjects
) -> LastSubjectDTO:
    """마지막 선택 사주 저장 — 본인 소유 사주만 허용(null=선택 해제)."""
    if body.subject_id is not None:
        record = subjects.get(body.subject_id)
        if record is None or record.owner_id != owner_id:
            raise HTTPException(status_code=403, detail="본인 소유 사주가 아닙니다")
    store.save_last_subject(owner_id, body.subject_id)
    return body

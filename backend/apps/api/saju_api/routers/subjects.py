"""대상(사주) CRUD 엔드포인트 (v2.2 프론트 확장 Phase 1).

로그인 사용자(owner_id)별 n개 사주를 관리한다. 목록 응답에는 사주별 '용신/물상 등록여부'
인디케이터를 ProfileStore 조회로 부여한다. 모든 접근은 소유자(owner_id) 일치를 강제한다.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from saju_engines.profile_store import ProfileStore
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.subject import SubjectRecord

from ..deps import get_profile_store, get_subject_store, require_owner
from ..services import precompute_service

router = APIRouter(prefix="/api/v2/subjects", tags=["subjects"])

OwnerId = Annotated[str, Depends(require_owner)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]
Profiles = Annotated[ProfileStore, Depends(get_profile_store)]


class SubjectUpsert(BaseModel):
    """사주 생성/수정 입력 — subject_id·owner_id는 서버가 부여."""

    kind: str = Field(default="self", pattern=r"^(self|companion)$")
    label: str = Field(min_length=1, max_length=30)
    birth: BirthInput
    gender: str | None = None
    relation_to_user: str | None = None
    aliases: list[str] = Field(default_factory=list)
    is_minor: bool = False
    subscribed: bool = False


class SubjectSummary(BaseModel):
    """목록/단건 응답 — 등록여부 인디케이터 포함."""

    subject_id: str
    owner_id: str
    kind: str
    label: str
    aliases: list[str]
    relation_to_user: str | None
    birth: BirthInput
    gender: str | None
    is_minor: bool
    subscribed: bool
    yongsin_registered: bool
    mulsang_registered: bool


def _registration_flags(profiles: ProfileStore, subject_id: str) -> tuple[bool, bool]:
    """(용신 등록, 물상 등록) — ProfileStore 조회. DB 미설정 등 실패 시 (False, False)."""
    try:
        yongsin = profiles.get_yongsin(subject_id) is not None
        profile = profiles.load(subject_id)
    except Exception:
        return (False, False)
    mulsang = bool(
        profile
        and profile.extended
        and any(
            getattr(profile.extended, f) is not None
            for f in ("occupation", "residence", "marital_status", "children")
        )
    )
    return (yongsin, mulsang)


def _to_summary(record: SubjectRecord, profiles: ProfileStore) -> SubjectSummary:
    """SubjectRecord → 등록여부가 부여된 응답."""
    yongsin, mulsang = _registration_flags(profiles, record.subject_id)
    return SubjectSummary(
        subject_id=record.subject_id,
        owner_id=record.owner_id,
        kind=record.kind,
        label=record.label,
        aliases=record.aliases,
        relation_to_user=record.relation_to_user,
        birth=record.birth,
        gender=record.gender,
        is_minor=record.is_minor,
        subscribed=record.subscribed,
        yongsin_registered=yongsin,
        mulsang_registered=mulsang,
    )


def _owned(store: SubjectStore, subject_id: str, owner_id: str) -> SubjectRecord:
    """소유 검증 후 레코드 반환 — 없거나 타 소유자면 404."""
    record = store.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="사주를 찾을 수 없습니다.")
    return record


@router.get("", response_model=list[SubjectSummary])
def list_subjects(
    owner_id: OwnerId, store: Subjects, profiles: Profiles
) -> list[SubjectSummary]:
    """소유자의 전체 사주 목록."""
    return [_to_summary(r, profiles) for r in store.list_all(owner_id)]


@router.get("/{subject_id}", response_model=SubjectSummary)
def get_subject(
    subject_id: str, owner_id: OwnerId, store: Subjects, profiles: Profiles
) -> SubjectSummary:
    """단건 조회(소유자 한정)."""
    return _to_summary(_owned(store, subject_id, owner_id), profiles)


@router.post("", response_model=SubjectSummary, status_code=201)
def create_subject(
    body: SubjectUpsert, owner_id: OwnerId, store: Subjects, profiles: Profiles
) -> SubjectSummary:
    """신규 사주 등록 — subject_id 부여 후 저장."""
    record = SubjectRecord(
        subject_id=uuid.uuid4().hex,
        owner_id=owner_id,
        kind=body.kind,
        label=body.label,
        aliases=body.aliases,
        relation_to_user=body.relation_to_user,
        birth=body.birth,
        gender=body.gender,
        is_minor=body.is_minor,
        subscribed=body.subscribed,
    )
    store.upsert(record)
    # T0 사전계산 — 출생정보가 확정된 시점에 운 복합조합을 미리 쌓는다(docs/09).
    precompute_service.on_subject_upsert(record)
    return _to_summary(record, profiles)


@router.put("/{subject_id}", response_model=SubjectSummary)
def update_subject(
    subject_id: str, body: SubjectUpsert, owner_id: OwnerId, store: Subjects, profiles: Profiles
) -> SubjectSummary:
    """사주 수정(소유자 한정) — last_interaction_at은 보존."""
    existing = _owned(store, subject_id, owner_id)
    record = SubjectRecord(
        subject_id=subject_id,
        owner_id=owner_id,
        kind=body.kind,
        label=body.label,
        aliases=body.aliases,
        relation_to_user=body.relation_to_user,
        birth=body.birth,
        gender=body.gender,
        is_minor=body.is_minor,
        subscribed=body.subscribed,
        last_interaction_at=existing.last_interaction_at,
    )
    store.upsert(record)
    # T0 무효화 + 재계산 — 출생정보가 바뀌었는데 옛 사전계산이 남으면 다른 사람의
    # 운을 보여주는 것과 같다(docs/09 무효화 규칙).
    precompute_service.on_subject_upsert(record)
    return _to_summary(record, profiles)


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: str, owner_id: OwnerId, store: Subjects) -> None:
    """사주 삭제(소유자 한정)."""
    _owned(store, subject_id, owner_id)
    store.delete(subject_id)
    # 삭제된 대상의 사전계산이 남으면 안 된다.
    _target = precompute_service.store()
    if _target is not None:
        with contextlib.suppress(Exception):
            _target.invalidate_subject(subject_id)

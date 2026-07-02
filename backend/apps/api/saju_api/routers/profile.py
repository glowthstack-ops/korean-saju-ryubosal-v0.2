"""사주별 프로필(물상·용신·basic) 엔드포인트 (v2.2 프론트 확장 Phase 1).

user_profiles를 subject_id로 키잉한다(D-PROFILE-KEY). 물상해석(ExtendedProfile)·확정 용신은
사주별이며, NOT NULL인 persona 컬럼에는 계정 전역 페르소나 스냅샷을 채운다(정본은
account_settings). 모든 접근은 해당 사주의 소유자(owner_id) 일치를 강제한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from saju_engines.account_store import AccountSettingsStore
from saju_engines.profile_store import ProfileStore
from saju_engines.subject_store import SubjectStore
from saju_shared_types.profile import BasicProfile, ExtendedProfile, PersonaConfig, UserProfile

from ..deps import get_account_store, get_profile_store, get_subject_store, require_owner

router = APIRouter(prefix="/api/v2/profile", tags=["profile"])

_EXTENDED_FIELDS = {"occupation", "residence", "marital_status", "children"}

OwnerId = Annotated[str, Depends(require_owner)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]
Profiles = Annotated[ProfileStore, Depends(get_profile_store)]
Accounts = Annotated[AccountSettingsStore, Depends(get_account_store)]


class ProfileUpsert(BaseModel):
    """사주별 프로필 저장 입력 — 물상·용신은 선택."""

    basic: BasicProfile
    extended: ExtendedProfile | None = None
    extended_completed_at: str | None = None
    confirmed_yongsin: str | None = None


class ProfileResponse(BaseModel):
    """사주별 프로필 응답 — 페르소나는 계정 전역(/account/persona)에서 별도 조회."""

    subject_id: str
    basic: BasicProfile | None
    extended: ExtendedProfile | None
    extended_completed_at: str | None
    confirmed_yongsin: str | None


def _assert_owned(subjects: SubjectStore, subject_id: str, owner_id: str) -> None:
    """사주 소유 검증 — 없거나 타 소유자면 404."""
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="사주를 찾을 수 없습니다.")


@router.get("/{subject_id}", response_model=ProfileResponse)
def get_profile(
    subject_id: str, owner_id: OwnerId, subjects: Subjects, profiles: Profiles
) -> ProfileResponse:
    """사주별 프로필 조회(없으면 빈 필드)."""
    _assert_owned(subjects, subject_id, owner_id)
    profile = profiles.load(subject_id)
    return ProfileResponse(
        subject_id=subject_id,
        basic=profile.basic if profile else None,
        extended=profile.extended if profile else None,
        extended_completed_at=profile.extended_completed_at if profile else None,
        confirmed_yongsin=profiles.get_yongsin(subject_id),
    )


@router.put("/{subject_id}", response_model=ProfileResponse)
def put_profile(
    subject_id: str,
    body: ProfileUpsert,
    owner_id: OwnerId,
    subjects: Subjects,
    profiles: Profiles,
    accounts: Accounts,
) -> ProfileResponse:
    """사주별 프로필 저장 — persona 컬럼은 계정 페르소나 스냅샷으로 채운다."""
    _assert_owned(subjects, subject_id, owner_id)
    persona: PersonaConfig = accounts.get_persona(owner_id) or PersonaConfig()
    profiles.save(
        UserProfile(
            user_id=subject_id,
            basic=body.basic,
            extended=body.extended,
            persona=persona,
            extended_completed_at=body.extended_completed_at,
        )
    )
    profiles.set_yongsin(subject_id, body.confirmed_yongsin)
    return ProfileResponse(
        subject_id=subject_id,
        basic=body.basic,
        extended=body.extended,
        extended_completed_at=body.extended_completed_at,
        confirmed_yongsin=body.confirmed_yongsin,
    )


class YongsinUpsert(BaseModel):
    """확정 용신 저장 — 만세력 페이지 용신 검증 확정용(프로필 행 없어도 동작).

    calibration: 검증 Q&A(답변·결과) — 주어지면 함께 저장해 다른 기기에서도 수정 프리필한다.
    """

    confirmed_yongsin: str | None = None
    calibration: dict | None = None


class YongsinResponse(BaseModel):
    """확정 용신 + 검증 답변 응답."""

    subject_id: str
    confirmed_yongsin: str | None
    calibration: dict | None = None


@router.get("/{subject_id}/yongsin", response_model=YongsinResponse)
def get_yongsin(
    subject_id: str, owner_id: OwnerId, subjects: Subjects, profiles: Profiles
) -> YongsinResponse:
    """확정 용신 + 저장된 검증 답변 조회 — 재검증 시 수정 모드 프리필용(교차 기기)."""
    _assert_owned(subjects, subject_id, owner_id)
    return YongsinResponse(
        subject_id=subject_id,
        confirmed_yongsin=profiles.get_yongsin(subject_id),
        calibration=profiles.get_yongsin_calibration(subject_id),
    )


@router.put("/{subject_id}/yongsin", response_model=YongsinResponse)
def put_yongsin(
    subject_id: str,
    body: YongsinUpsert,
    owner_id: OwnerId,
    subjects: Subjects,
    profiles: Profiles,
) -> YongsinResponse:
    """확정 용신 저장(사주별) — 만세력 페이지 용신 검증 확정을 DB에 영속.

    basic/persona가 필요한 전체 프로필 저장과 달리, 용신 검증만 마친 단계(프로필 행 없음)에서도
    동작하도록 전용 테이블에 UPSERT한다. calibration이 오면 검증 답변까지 함께 저장한다.
    """
    _assert_owned(subjects, subject_id, owner_id)
    if body.calibration is not None:
        profiles.set_yongsin_calibration(subject_id, body.confirmed_yongsin, body.calibration)
    else:
        profiles.set_yongsin(subject_id, body.confirmed_yongsin)
    return YongsinResponse(
        subject_id=subject_id,
        confirmed_yongsin=body.confirmed_yongsin,
        calibration=body.calibration,
    )


@router.delete("/{subject_id}/extended/{field}", status_code=204)
def delete_extended_field(
    subject_id: str, field: str, owner_id: OwnerId, subjects: Subjects, profiles: Profiles
) -> None:
    """2단계 필드 개별 삭제(물상해석 일부 제거)."""
    if field not in _EXTENDED_FIELDS:
        raise HTTPException(status_code=400, detail=f"삭제할 수 없는 필드: {field}")
    _assert_owned(subjects, subject_id, owner_id)
    profiles.delete_extended_field(subject_id, field)

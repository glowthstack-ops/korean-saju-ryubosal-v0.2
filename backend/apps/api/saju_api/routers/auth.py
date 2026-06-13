"""계정(ID+PIN) 인증 엔드포인트 (v2.2 프론트 확장 Phase 1).

OAuth 도입 전 임시 본인 확인 수단. 같은 login_id+PIN으로 재로그인하면 같은 owner_id를
복원해 사주목록의 연속성을 보장한다. 검증 성공 시 상태 없는 서명 토큰을 발급한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from saju_engines.auth_store import AccountAuthStore, AccountExistsError
from saju_shared_types.account import AccountRecord, AuthToken, Credentials

from ..deps import get_auth_store, make_token, require_owner

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])

Auth = Annotated[AccountAuthStore, Depends(get_auth_store)]
OwnerId = Annotated[str, Depends(require_owner)]


@router.post("/register", response_model=AuthToken)
def register(creds: Credentials, store: Auth) -> AuthToken:
    """신규 계정 등록 → 토큰 발급. 중복 ID는 409."""
    try:
        account = store.register(creds.login_id, creds.pin)
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 ID입니다.") from exc
    return AuthToken(
        token=make_token(account.owner_id),
        owner_id=account.owner_id,
        login_id=account.login_id,
    )


@router.post("/login", response_model=AuthToken)
def login(creds: Credentials, store: Auth) -> AuthToken:
    """login_id+PIN 검증 → 토큰 발급. 실패는 401."""
    account = store.verify(creds.login_id, creds.pin)
    if account is None:
        raise HTTPException(status_code=401, detail="ID 또는 PIN이 올바르지 않습니다.")
    return AuthToken(
        token=make_token(account.owner_id),
        owner_id=account.owner_id,
        login_id=account.login_id,
    )


@router.get("/me", response_model=AccountRecord)
def me(owner_id: OwnerId, store: Auth) -> AccountRecord:
    """토큰으로 현재 계정을 조회한다."""
    account = store.get(owner_id)
    if account is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    return account

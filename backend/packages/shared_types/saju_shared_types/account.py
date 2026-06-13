"""계정(ID+PIN 경량 인증) schema (v2.2 프론트 확장 Phase 1).

ID+PIN은 OAuth 도입 전 임시 본인 확인 수단이다. 같은 login_id+PIN으로 재로그인하면
같은 owner_id를 복원해 사주목록의 연속성을 보장한다. PIN 원문은 보관하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# 로그인 ID/PIN 형식 — 영숫자·언더스코어 3~30자 / 숫자 4~12자.
LOGIN_ID_PATTERN = r"^[A-Za-z0-9_]{3,30}$"
PIN_PATTERN = r"^[0-9]{4,12}$"


class AccountRecord(BaseModel):
    """저장된 계정 1건 — (owner_id) 기본키. pin_hash는 응답에 노출하지 않는다."""

    owner_id: str
    login_id: str
    created_at: datetime | None = None


class Credentials(BaseModel):
    """등록/로그인 입력 — login_id + PIN."""

    login_id: str = Field(pattern=LOGIN_ID_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)


class AuthToken(BaseModel):
    """발급 토큰 응답 — 클라이언트가 Authorization 헤더로 재전송."""

    token: str
    owner_id: str
    login_id: str

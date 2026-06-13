"""계정 전역 설정(페르소나) 엔드포인트 (v2.2 프론트 확장 Phase 1).

페르소나는 계정당 1개(문체 전용, docs/11 5장). 미설정 시 기본값을 반환한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from saju_engines.account_store import AccountSettingsStore
from saju_shared_types.profile import PersonaConfig

from ..deps import get_account_store, require_owner

router = APIRouter(prefix="/api/v2/account", tags=["account"])

OwnerId = Annotated[str, Depends(require_owner)]
Accounts = Annotated[AccountSettingsStore, Depends(get_account_store)]


@router.get("/persona", response_model=PersonaConfig)
def get_persona(owner_id: OwnerId, store: Accounts) -> PersonaConfig:
    """계정 페르소나 조회 — 미설정 시 기본값."""
    return store.get_persona(owner_id) or PersonaConfig()


@router.put("/persona", response_model=PersonaConfig)
def put_persona(persona: PersonaConfig, owner_id: OwnerId, store: Accounts) -> PersonaConfig:
    """계정 페르소나 저장/갱신."""
    store.save_persona(owner_id, persona)
    return persona

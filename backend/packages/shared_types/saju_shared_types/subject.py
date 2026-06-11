"""대상(self/동반자) 영속화 schema (v2.2 Phase 2.5 — docs/02 E14의 최소 부분집합).

Subject Manager(E14)의 전체 기능(별칭 학습·인라인 임시 인물·쌍둥이 변형 전환)은
Phase 4에서 확장한다. 여기서는 사전계산 스케줄러(T2.5.4)가 요구하는 식별·출생정보·
활성 판정 필드만 정의한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from .birth_input import BirthInput

ACTIVE_WINDOW_DAYS = 30  # 활성 대상 기준(docs/09 1장): 최근 30일 내 대화 이력


class SubjectRecord(BaseModel):
    """저장된 대상 1명 — (subject_id) 기본키."""

    subject_id: str
    owner_id: str = "default"
    kind: str  # 'self' | 'companion'
    label: str
    aliases: list[str] = Field(default_factory=list)
    relation_to_user: str | None = None
    birth: BirthInput
    gender: str | None = None
    is_minor: bool = False
    subscribed: bool = False  # 일일운세 구독 → 항상 활성
    last_interaction_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """활성 대상 여부 — 구독 중이거나 최근 30일 내 대화 이력."""
        if self.subscribed:
            return True
        if self.last_interaction_at is None:
            return False
        return now - self.last_interaction_at <= timedelta(days=ACTIVE_WINDOW_DAYS)

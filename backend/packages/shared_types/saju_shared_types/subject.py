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


#: 명식별 '나와의 관계' 키(2026-10-14 데굴님 승인, 17종). 별칭 해소
#: (companion_alias.RELATION_SYNONYMS) 키와 같게 맞춰 "남편"·"엄마" 지칭이 등록 동반자로 바로
#: 해소된다. 자유 문자열은 받지 않는다.
RELATION_TO_USER_KEYS: tuple[str, ...] = (
    "self", "spouse", "husband", "wife", "father", "mother", "child", "son", "daughter",
    "brother", "sister", "lover", "friend", "coworker", "boss", "business_partner", "other",
)
RELATION_TO_USER_KO: dict[str, str] = {
    "self": "본인", "spouse": "배우자", "husband": "남편", "wife": "아내", "father": "아버지",
    "mother": "어머니", "child": "자녀", "son": "아들", "daughter": "딸", "brother": "형제",
    "sister": "자매", "lover": "연인", "friend": "친구", "coworker": "동료", "boss": "상사",
    "business_partner": "동업자", "other": "기타",
}


def kind_for_relation(relation: str | None, fallback: str) -> str:
    """관계 키 → kind. 본인=self, 그 외 관계=companion, 관계 미설정이면 기존 kind 유지."""
    if relation is None:
        return fallback
    return "self" if relation == "self" else "companion"


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

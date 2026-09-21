"""민속 흉방(Folk Taboo Direction) 레이어 타입 — docs/19 §5 (2026-09-21 데굴님 승인).

개인 사주·사용 목적과 무관하게 **그해(삼살방·대장군방·태세방·세파방)·그날(손방)** 공통으로 적용되는
방위 금기. 개인 12신살 방향(`sinsal_direction`)과 별개 레이어이며 서로 덮어쓰지 않는다.

원칙:
- 기원 분리 — 삼살방(그해 지지)과 12신살 겁·재·천(출생 연지)은 표가 같아 보여도 같은 객체가 아니다.
- 적용 범위 — 이사·개업·증축·터파기 등 큰 공간 변동. 바라보기·머리·위치·출입구 배치에는 판정하지
  않는다.
- 표현 — "민속에서는 ○쪽은 ○○한 이유로 피하는 방향으로 본다"는 추가 정보. 흉사 확정 금지.
- 서술 전용(inert) — 점수·판정·날짜·간지 파이프라인 불변.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

#: 4방 라벨(sinsal_direction.Cardinal4 와 동일 표기).
Cardinal4 = Literal["동", "남", "서", "북"]

#: 계산 기준 — 그해 지지 삼합 / 그해 지지 방합 / 그해 지지 자체 / 그해 지지의 충 / 음력 일.
TabooBasis = Literal[
    "annual_trine", "annual_directional", "annual_branch", "annual_clash", "lunar_day"
]

#: 민속 흉방 등급 2단계 — 연간 흉방 2종 이상 중첩이면 강한 주의.
FolkGrade = Literal["FOLK_TABOO", "STRONG_FOLK_TABOO"]


class FolkTabooEntry(BaseModel):
    """흉방 1종의 사전 항목."""

    key: str
    name_ko: str
    hanja: str
    basis: TabooBasis
    period: Literal["year", "year3", "day"]
    table: dict[str, Cardinal4] = Field(default_factory=dict)  # basis 별 키(삼합/방합/음력 끝자리)
    reason_ko: str  # "…한 자리라" — 문구 템플릿 {reasons} 에 들어가는 이유 구
    character_ko: str
    avoid_actions: list[str] = Field(min_length=1)
    importance: Literal["very_high", "high", "optional"]

    @model_validator(mode="after")
    def _table_matches_basis(self) -> FolkTabooEntry:
        """표 키가 기준(basis)에 맞아야 한다 — 삼합 4·방합 4·음력 끝자리 8, 지지/충은 계산."""
        expected: dict[str, set[str]] = {
            "annual_trine": {"寅午戌", "巳酉丑", "申子辰", "亥卯未"},
            "annual_directional": {"亥子丑", "寅卯辰", "巳午未", "申酉戌"},
            "lunar_day": {str(i) for i in range(1, 9)},
            "annual_branch": set(),
            "annual_clash": set(),
        }
        if set(self.table) != expected[self.basis]:
            raise ValueError(f"{self.key}: basis {self.basis} 표 키 불일치 — {sorted(self.table)}")
        return self


class FolkTabooDict(BaseModel):
    """`dictionaries/folk_taboo_direction.json` 루트."""

    schema_version: str = Field(alias="schema")
    version: str
    reviewed: bool
    notes: list[str] = Field(default_factory=list)
    phrase_template: str  # {direction}·{reasons}·{names} 치환
    scope_note: str
    applies_actions: list[str] = Field(min_length=1)
    grades: dict[FolkGrade | str, str]
    taboos: list[FolkTabooEntry] = Field(min_length=5, max_length=5)
    excluded: list[str] = Field(default_factory=list)
    forbidden_framings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def taboo(self, key: str) -> FolkTabooEntry:
        """키 → 항목."""
        for t in self.taboos:
            if t.key == key:
                return t
        raise KeyError(key)


# ── 계산 결과 ────────────────────────────────────────────────────────────────


class FolkTabooHit(BaseModel):
    """흉방 1건의 적중 — 어느 4방(세부 지지)이 왜."""

    key: str
    name_ko: str
    direction: Cardinal4
    # 세부 지지(삼살·대장군=3, 태세·세파=1, 손방=0)
    branches: list[str] = Field(default_factory=list)
    reason_ko: str
    period: Literal["year", "year3", "day"]
    basis_ko: str  # '2026 丙午년' / '음력 8월 11일'


class FolkDirectionNote(BaseModel):
    """4방 1칸의 민속 흉방 요약 — 연간 흉방 중첩 등급 + 손방 표시."""

    direction: Cardinal4
    hits: list[FolkTabooHit] = Field(default_factory=list)  # 연간(삼살·대장군·태세·세파)
    son_today: bool = False  # 그날 손방이 이 방향인가
    grade: FolkGrade = "FOLK_TABOO"


class FolkTabooSummary(BaseModel):
    """기준 연도(·그날)의 민속 흉방 전체 요약 — 세운 카드·프롬프트·택일이 공유."""

    year: int
    year_ganji: str
    notes: list[FolkDirectionNote] = Field(default_factory=list)  # 적중 방향만
    son: FolkTabooHit | None = None  # 그날 손방(손 없는 날이면 None)
    son_free_day: bool | None = None  # 그날이 손 없는 날인가(날짜 없으면 None)
    lunar_label: str | None = None

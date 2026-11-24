"""민속 흉방(Folk Taboo Direction) 레이어 타입 — docs/19 §5 (2026-09-21 데굴님 승인).

개인 사주·사용 목적과 무관하게 **그해(삼살방·대장군방·태세방·세파방)·그날(손방)** 공통으로 적용되는
방위 금기. 개인 12신살 방향(`sinsal_direction`)과 별개 레이어이며 서로 덮어쓰지 않는다.

원칙:
- 기원 분리 — 삼살방(그해 지지)과 12신살 겁·재·천(출생 연지)은 표가 같아 보여도 같은 객체가 아니다.
- 적용 범위 — 이사·개업·증축·터파기 등 큰 공간 변동. 바라보기·머리·위치·출입구 배치에는 판정하지
  않는다.
- 표현 — "민속에서는 ○쪽은 ○○한 이유로 피하는 방향으로 본다"는 추가 정보. 흉사 확정 금지.
- 서술 전용(inert) — 점수·판정·날짜·간지 파이프라인 불변.
- 범위 표기(2026-11-24 데굴님 승인, docs/19 §5-6) — 판정 묶음은 4방(`direction`) 그대로 두고,
  각 흉방이 실제로 걸치는 8방위·24방위 구간을 따로 싣는다(`direction8`·`mountains`·`spans8`·
  `range_ko`). 4방 한 글자로 뭉개지던 표기의 보완이며 판정·중첩 등급은 불변.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from saju_shared_types.compass24 import Direction8

#: 4방 라벨(sinsal_direction.Cardinal4 와 동일 표기).
Cardinal4 = Literal["동", "남", "서", "북"]

#: 계산 기준 — 그해 지지 삼합 / 그해 지지 방합 / 그해 지지 자체 / 그해 지지의 충 / 음력 일.
TabooBasis = Literal[
    "annual_trine", "annual_directional", "annual_branch", "annual_clash", "lunar_day"
]

#: 민속 흉방 등급 2단계 — 이사 판정층(MOVE) 흉방 2종 이상 중첩이면 강한 주의.
FolkGrade = Literal["FOLK_TABOO", "STRONG_FOLK_TABOO"]

#: 계층(2026-09-22 데굴님 승인, 검색 근거 docs/19 §5-4)
#: - MOVE = 이사·이동 판정(삼살·대장군·손방, 한국 실무 3종)
#: - GROUND = 동토·좌향 참고(태세·세파) — 이사 판정에 넣지 않고 건축·터파기·집 좌향 질문에만
#:   한 문장.
TabooTier = Literal["MOVE", "GROUND"]

#: 24방위 범위 규칙(2026-11-24 데굴님 승인, docs/19 §5-6)
#: - branch_arc = 그 방향 지지 3구간과 사이 칸을 이은 연속 범위(삼살: 亥~丑 다섯 칸)
#: - cardinal_palace = 8방위 정방 한 칸(대장군: 甲·卯·乙 세 칸, 왕지 중심)
#: - single_branch = 지지 한 칸(태세·세파)
#: - none = 24방위 범위 없음(손방 — 4방 그대로)
ExtentRule = Literal["branch_arc", "cardinal_palace", "single_branch", "none"]

#: 범위 문구 템플릿 키 — single_branch 는 정방 가운데 칸 / 간방 가장자리 칸 두 문형.
RANGE_TEMPLATE_KEYS: tuple[str, ...] = (
    "branch_arc", "cardinal_palace", "single_branch_cardinal", "single_branch_inter",
)


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
    tier: TabooTier  # MOVE(이사 판정) / GROUND(동토·좌향 참고)
    extent: ExtentRule  # 24방위 범위 규칙(표기 전용 — 판정 묶음은 4방 그대로)
    # 좌향 완화 문구("三煞可向不可坐"·"太歲可坐不可向") — 답에 그대로 병기해 강도를 낮춘다.
    # 없으면 빈 문자열.
    mitigation_ko: str = ""

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
    # 원거리 고지(2026-09-22) — 전통 문헌: 120보 이내 근거리 이사만 방위를 가린다.
    # 이사 전체 블록에 한 줄.
    distance_note: str
    applies_actions: list[str] = Field(min_length=1)
    grades: dict[FolkGrade | str, str]
    tiers: dict[TabooTier | str, str] = Field(default_factory=dict)  # 계층 라벨(표시용)
    # 24방위 범위 문구 템플릿(2026-11-24) — 키는 RANGE_TEMPLATE_KEYS. 엔진이 치환만 한다.
    range_templates: dict[str, str]
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


class FolkSpan8(BaseModel):
    """흉방 범위가 걸치는 8방위 한 칸 — 전체(세 칸 모두)인지 일부인지와 해당 24방위 칸."""

    direction: Direction8
    coverage: Literal["full", "partial"]
    mountains: list[str] = Field(min_length=1, max_length=3)


class FolkTabooHit(BaseModel):
    """흉방 1건의 적중 — 어느 4방(세부 지지)이 왜, 8·24방위로는 어디까지."""

    key: str
    name_ko: str
    direction: Cardinal4  # 판정 묶음용 4방(중첩 등급·택일 근거 — 표기는 direction8·range_ko)
    # 세부 지지(삼살=3, 대장군=1(왕지), 태세·세파=1, 손방=0)
    branches: list[str] = Field(default_factory=list)
    # ── 8·24방위 범위(표기 전용, docs/19 §5-6) ──
    direction8: Direction8 | None = None  # 중심 8방위(未 태세 = 남서)
    center_mountain: str = ""  # 중심 24방위 칸(손방은 빈 문자열)
    mountains: list[str] = Field(default_factory=list)  # 차지하는 24방위 칸(시계 방향)
    spans8: list[FolkSpan8] = Field(default_factory=list)  # 걸치는 8방위(전체/일부)
    degree_from: float | None = None  # 시작 각(정북 0°·시계 방향)
    degree_to: float | None = None  # 끝 각 — 정북을 넘으면 시작 각보다 작다
    range_ko: str = ""  # 사전 템플릿으로 만든 범위 문구('북 전체(壬·子·癸)와 북서쪽 亥 구간…')
    reason_ko: str
    period: Literal["year", "year3", "day"]
    basis_ko: str  # '2026 丙午년' / '음력 8월 11일'
    tier: TabooTier = "MOVE"
    mitigation_ko: str = ""
    span_ko: str = ""  # 대장군방 3년 고정 구간('2025~2027') — 그 외 빈 문자열


class FolkDirectionNote(BaseModel):
    """4방 1칸의 민속 흉방 요약 — 연간 흉방 중첩 등급 + 손방 표시."""

    direction: Cardinal4
    hits: list[FolkTabooHit] = Field(default_factory=list)  # 이사 판정층(MOVE: 삼살·대장군)
    ground_hits: list[FolkTabooHit] = Field(default_factory=list)  # 참고층(GROUND: 태세·세파)
    son_today: bool = False  # 그날 손방이 이 방향인가
    grade: FolkGrade = "FOLK_TABOO"  # MOVE 층 중첩으로만 결정(참고층·손방은 안 센다)


class FolkTabooSummary(BaseModel):
    """기준 연도(·그날)의 민속 흉방 전체 요약 — 세운 카드·프롬프트·택일이 공유."""

    year: int
    year_ganji: str
    notes: list[FolkDirectionNote] = Field(default_factory=list)  # 적중 방향만
    son: FolkTabooHit | None = None  # 그날 손방(손 없는 날이면 None)
    son_free_day: bool | None = None  # 그날이 손 없는 날인가(날짜 없으면 None)
    lunar_label: str | None = None

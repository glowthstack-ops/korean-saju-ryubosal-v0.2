"""직업 분야(십성 기능) 사전·근거 스키마 (2026-09-10 데굴님 제공 자료, docs/08 career_field).

십성은 직업명이 아니라 '어떤 기능과 방식으로 일하는가'에 연결한다. 이 모델은 사전
(`dictionaries/career_fields.json`)의 런타임 검증과, 엔진이 명식에서 뽑은 근거
(`CareerFieldFacts`)의 계약이다. 점수·판정이 아니라 **서술 근거**다(LLM 계산 금지 원칙 준수).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

TEN_GOD_KO: tuple[str, ...] = (
    "비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인",
)


class TenGodField(BaseModel):
    """십성 1종의 직업 기능 표."""

    model_config = ConfigDict(extra="forbid")
    hanja: str
    traits: str
    job_groups: list[str] = Field(min_length=1)
    distinction: str
    conditions: str
    favorable_roles: list[str] = Field(min_length=1)
    caution: str


class JudgmentFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factor: str
    look_at: str
    apply: str
    avoid: str


class Combination(BaseModel):
    """배합(식신생재 등) — 구조 패턴 id 가 있으면 감지기 결과로, 없으면 derived_rule 로 판정."""

    model_config = ConfigDict(extra="forbid")
    name: str
    pattern_id: str | None = None
    derived_rule: str | None = None
    condition: str
    mechanism: str
    jobs: list[str] = Field(min_length=1)


class YongsinModifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    condition: str
    reading: str


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = ""
    strong_pct: float = 25.0
    excess_pct: float = 30.0
    prominent_pct: float = 10.0
    prominent_top_n: int = 3


class CareerFieldDict(BaseModel):
    """`dictionaries/career_fields.json` 전체."""

    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(alias="schema")
    version: str
    reviewed: bool
    runtime_status: str
    review_status: str
    review_note: str = ""
    principles: list[str]
    ten_gods: dict[str, TenGodField]
    judgment_factors: list[JudgmentFactor]
    combinations: list[Combination]
    yongsin_modifiers: list[YongsinModifier]
    thresholds: Thresholds = Field(default_factory=Thresholds)


class ProminentTenGod(BaseModel):
    """명식에서 두드러진 십성 1건 — 비중·역할·직업군."""

    ten_god: str
    percent: float
    role: str = ""  # 용신/희신/기신/구신/한신/""
    job_groups: list[str]
    distinction: str
    caution: str


class CombinationHit(BaseModel):
    name: str
    strength: float
    mechanism: str
    jobs: list[str]
    condition: str


class IncomingChannel(BaseModel):
    """현재 운(세운·월운) 천간 십성 — '제안·기회가 들어오는 통로'."""

    label: str  # "2026" / "2026-09"
    ten_god: str
    role: str = ""
    job_groups: list[str]


class CareerFieldFacts(BaseModel):
    """직업 분야 근거 묶음 — 프롬프트 블록 직렬화 입력."""

    day_master: str = ""
    strength_band: str = ""
    geokguk: str = ""
    prominent: list[ProminentTenGod] = Field(default_factory=list)
    combinations: list[CombinationHit] = Field(default_factory=list)
    modifiers: list[YongsinModifier] = Field(default_factory=list)
    incoming: list[IncomingChannel] = Field(default_factory=list)
    principles: list[str] = Field(default_factory=list)

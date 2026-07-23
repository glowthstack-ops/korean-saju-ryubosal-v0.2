"""구조 패턴(Structure Pattern) 계층 타입.

십성 관계 구조 라벨(식신생재·상관견관·재극인·관인상생 등)을 도메인 무관 단일
사전(`dictionaries/structure_patterns.json`)으로 정의하고, 감지 결과를 담는다.

설계: `doc/v2_2/docs/13_STRUCTURE_PATTERNS.md`.

불변 원칙(설계 §9):
- 이 계층은 **구조**만 다룬다. 최종 길흉은 용신/기신/operability 계층이,
  사건은 EventEngineV2가 부여한다(절대원칙 1·3·4).
- `DetectedPattern`은 길흉을 확정하지 않는다. `polarity_mode`(구조적 방향 성향)만
  사전에서 승계하고, 사건 라벨 대신 `domain_hints`(EventKeyV2 후보)만 제공한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 사전 polarity_mode 허용값 (설계 §3).
PolarityMode = Literal[
    "favorable", "unfavorable", "depends_on_yonggi_and_control", "context_only"
]
PatternScope = Literal["natal", "luck", "natal_luck"]


class StructurePatternEntry(BaseModel):
    """`structure_patterns.json` 의 패턴 1건 정의(사전 원본 미러).

    감지 로직이 아니라 '무엇을 어떻게 설명할지'를 담는다. 성립 강도·최종 길흉은
    엔진이 계산하며 이 엔트리에는 저장하지 않는다.
    """

    pattern_id: str
    name_ko: str
    name_hanja: str
    family: list[str]
    structure: str  # 정규화 관계식 ('->' 상생, 'X' 극, '+' 병존)
    ten_god_chain: list[str] = Field(default_factory=list)  # TenGod 로마자 enum
    evidence: list[str] = Field(default_factory=list)
    domain_hints: list[str] = Field(default_factory=list)  # EventKeyV2(21종) 후보
    polarity_mode: PolarityMode
    severity_inputs: list[str] = Field(default_factory=list)
    detector_source: str  # 'adapter:<기존 감지기>' | 'new:<규칙>'
    llm_usage: str = "explanation_tag_only"
    llm_tag: str  # 압축 설명(120자 이내) — LLM 그대로 전달
    # 전통 해석 문구('~해석하기도 한다' 형, 220자 이내) — 사고수 확장(2026-07-23).
    # LLM 3층 출력(전통 해석층) 전용. 단정·질병명·사건 확정 금지. 없으면 llm_tag만 사용.
    classical_note: str | None = None


class StructurePatternDict(BaseModel):
    """`structure_patterns.json` 전체."""

    schema_version: str = Field(alias="schema")
    reviewed: bool = False
    purpose: str = ""
    notes: dict[str, str] = Field(default_factory=dict)
    patterns: list[StructurePatternEntry] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class DetectedPattern(BaseModel):
    """감지된 구조 패턴 1건 (inert 확장 — 기존 수치 파이프라인 불변).

    `strength` 는 '패턴 성립 강도'(0~1)일 뿐 favorability/confidence/길흉을 바꾸지
    않는다. 길흉 확정을 피하기 위해 `favorability` 는 기본 None 이며, 필요 시
    상위(용신) 계층이 읽은 역할을 주석용으로만 채운다.
    """

    pattern_id: str
    name_ko: str
    family: list[str] = Field(default_factory=list)
    strength: float = Field(ge=0.0, le=1.0)
    scope: PatternScope = "natal"
    polarity_mode: PolarityMode
    favorability: str | None = None  # 용신 역할 주석(길흉 확정 아님) — P0 미채움
    domain_hints: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    llm_tag: str = ""
    classical_note: str | None = None  # 전통 해석층 문구(사전 승계, 사고수 확장)

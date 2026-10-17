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
    # 별칭(동의어·이표기, 2026-09-17 용어 감사). 같은 구조를 다른 이름으로 부르는 고전·학파
    # 표현을 라벨에 병기해 풀이가 어느 이름으로 물어도 같은 패턴을 짚게 한다. 감지 조건 불변.
    aliases: list[str] = Field(default_factory=list)


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
    name_hanja: str = ""  # 한자명(사전 승계) — 만세력 화면 한글·한자 병기용(2026-10-17)
    family: list[str] = Field(default_factory=list)
    strength: float = Field(ge=0.0, le=1.0)
    scope: PatternScope = "natal"
    polarity_mode: PolarityMode
    favorability: str | None = None  # 용신 역할 주석(길흉 확정 아님) — P0 미채움
    domain_hints: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    llm_tag: str = ""
    classical_note: str | None = None  # 전통 해석층 문구(사전 승계, 사고수 확장)
    aliases: list[str] = Field(default_factory=list)  # 별칭(사전 승계) — 표기 전용
    #: P0 세력 보정 2중 판정 근거(억부 6종만) — "표면 29%·보정 세력 37%·신약 — 뚜렷한 성립".
    #: 화면 줄 끝과 llm_line 끝에 붙는다. 길흉이 아니라 성립 강도의 근거다(2026-10-17).
    basis_note: str = ""

    @property
    def llm_line(self) -> str:
        """LLM 주입 한 줄 = llm_tag + 별칭 병기 + P0 근거.

        둘 다 없으면 llm_tag 그대로(기존 바이트 불변).
        """
        line = self.llm_tag
        if self.aliases:
            line = f"{line} [별칭: {'·'.join(self.aliases)}]"
        if self.basis_note:
            line = f"{line} [근거: {self.basis_note}]"
        return line


# ── 운 적용 구조 상태(F8-P1, 2026-10-17) ────────────────────────────────────
PatternTransitStatus = Literal["new", "strengthened", "weakened", "resolved", "unchanged"]
PatternTransitType = Literal["T1", "T2", "T3", "T4", "T5"]


class PatternState(BaseModel):
    """운 한 층(대운·세운·월운)에서 본 구조 배합 1건의 상태 — 성립과 작동을 분리한다.

    `natal_established` 는 원국 감지(P0 포함)로 고정, `operating` 은 그 층까지 누적한 운 적용
    세력으로 판정. 상태는 길흉이 아니다(favorability 없음, 점수 불변). 월운 층은 'resolved' 를
    쓰지 않는다(최대 weakened). SSOT: doc/v2_2/PATTERN_TRANSIT_STATES.md §2.
    """

    pattern_id: str
    name_ko: str
    transit_type: PatternTransitType
    natal_established: bool
    operating: bool
    status_vs_natal: PatternTransitStatus
    status_vs_parent: PatternTransitStatus
    strength_natal: float = Field(ge=0.0, le=1.0, default=0.0)
    strength_operating: float = Field(ge=0.0, le=1.0, default=0.0)
    activation_sources: list[str] = Field(default_factory=list)  # daewoon|year|month
    evidence: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # burden|over_control|competition|broken


class PatternTimelineCell(BaseModel):
    """타임라인 한 칸 — 그 층에서의 상태(직전 층 대비)와 작동 여부, 유형별 어휘."""

    status: PatternTransitStatus
    operating: bool
    label: str  # 신규 성립/강화/완화/해소/변동 없음(유형별 어휘)


class PatternTimelineRow(BaseModel):
    """패턴 1건의 원국 → 대운 → 세운 → 1~12월 흐름(선택 연도 기준). 성립≠길흉."""

    pattern_id: str
    name_ko: str
    name_hanja: str = ""
    transit_type: PatternTransitType
    natal_established: bool
    daewoon: PatternTimelineCell | None = None
    year: PatternTimelineCell | None = None
    months: list[PatternTimelineCell | None] = Field(default_factory=list)  # 12칸(없으면 None)
    flags: list[str] = Field(default_factory=list)
    summary: str = ""  # "원국 성립 → 대운 완화 → 세운 해소 → 2·3월 재활성" (사전 어휘 치환)


class PatternTimeline(BaseModel):
    """선택 연도의 구조 배합 흐름 종합(만세력 페이지 단일 영역, F8-P1 종합 뷰 — 2026-10-17)."""

    year: int
    hour_unknown: bool = False
    daewoon_ganji: str | None = None
    year_ganji: str | None = None
    month_labels: list[str] = Field(default_factory=list)
    month_ganji: list[str] = Field(default_factory=list)
    rows: list[PatternTimelineRow] = Field(default_factory=list)
    note: str = ""

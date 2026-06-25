"""신살 schemas (Phase 5).

정책: 계산 가능한 신살을 모두 표시하되, 신강약·용신·격국 결정의 핵심 근거로 직접 쓰지 않는다
(use_for_yongsin_decision=False). 해석 태그·사건 분야 힌트로만 활용.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SinsalItem(BaseModel):
    name: str
    category: str
    position: str  # year / month / day / hour
    basis: str
    palace: str | None = None
    ten_god_context: str | None = None
    element_context: str | None = None
    intensity: str = "low"  # low / medium / high / very_high
    repeated: bool = False
    activated_by_relations: list[str] = Field(default_factory=list)
    interpretation_tags: list[str] = Field(default_factory=list)
    caution_tags: list[str] = Field(default_factory=list)
    use_for_yongsin_decision: bool = False


class LuckSinsal(BaseModel):
    """운(대운/세운/월운/일운)이 불러오는 신살 한 항목 — 카드 표시용 경량 모델.

    운의 간지를 새로운 자리(位)로 보고 원국 기준점(일간·월지·년지·일지)에 대조해 산출한다.
    원국 4기둥 신살(SinsalItem)과 달리 위치·강도 등 상세는 생략하고 표시용 최소 정보만 담는다.
    """

    name: str
    polarity: str = "neutral"  # positive(길신) / caution(흉성) / neutral(신살)


class LlmSinsalModifier(BaseModel):
    """LLM 노출용 신살 보정 태그(SINSAL_MODIFIER_SPEC §9-2).

    내부 수치(internal_weight 등)는 제외하고 한글 강도어·효과 태그만 담는다 — LLM이 숫자를
    점수로 오해·과반영하지 않도록(§9). 신살은 보조 레이어(단독 사건 생성 금지).
    """

    star: str  # 신살명(역마살 등)
    position: str  # year | month | day | hour (원국 자리 또는 운 발동 자리)
    source: str = "natal"  # natal | daewoon | yearly | monthly | daily
    polarity: str = "neutral"  # positive | caution | neutral
    domain_match: bool = False  # 질문 intent ∩ 궁성 정렬(§7)
    activation_status: str = "background"  # latent | background | activated | strongly_activated
    llm_strength: str = "보조"  # 약함 | 보조 | 강함 | 매우 강함
    effect_tags: list[str] = Field(default_factory=list)  # 한글 효과 태그(숫자 없음)
    palace_tags: list[str] = Field(default_factory=list)  # GENERAL 흡수용 궁성/서브도메인


class SinsalModifier(BaseModel):
    """신살 파생 해석(SINSAL_MODIFIER_SPEC §3) — 원천 SinsalItem 비파괴, 질문·운·생애단계 반영.

    위치(궁성)·도메인·운층·생애단계·재활성화를 합성한 보정 결과. internal_* 는 LLM 미노출
    (debug/shadow 전용). Phase A 에서는 event_score 를 바꾸지 않는다(태그 enrichment 전용).
    """

    name: str
    polarity: str  # positive | caution | neutral
    position: str  # year | month | day | hour
    source: str = "natal"  # natal | daewoon | yearly | monthly | daily
    scope: list[str] = Field(default_factory=list)  # §4 작동 도메인 키
    palace_tags: list[str] = Field(default_factory=list)  # §7 GENERAL 흡수 태그
    domain_match: bool = False
    activation_status: str = "background"  # latent | background | activated | strongly_activated
    life_stage: str = "middle"  # childhood | youth | middle | late
    life_stage_mode: str = "direct"  # seed | emerging | direct | background | accumulated
    effect_tags: list[str] = Field(default_factory=list)
    llm_strength: str = "보조"
    # 내부 전용(LLM 미노출) — debug/shadow 로그.
    internal_weight: float = 0.0
    internal_factors: list[str] = Field(default_factory=list)

    def to_llm(self) -> LlmSinsalModifier:
        """LLM 노출 subset 으로 변환(internal_* 제외, §9)."""
        return LlmSinsalModifier(
            star=self.name, position=self.position, source=self.source,
            polarity=self.polarity, domain_match=self.domain_match,
            activation_status=self.activation_status, llm_strength=self.llm_strength,
            effect_tags=self.effect_tags, palace_tags=self.palace_tags,
        )


class SinsalSummary(BaseModel):
    repeated: list[str] = Field(default_factory=list)
    major_positive: list[str] = Field(default_factory=list)
    major_caution: list[str] = Field(default_factory=list)
    palace_sensitive: list[str] = Field(default_factory=list)
    structure_overlapped: list[str] = Field(default_factory=list)


class SinsalAnalysis(BaseModel):
    scope: str = "natal_chart_only"
    display_policy: str = "show_all"
    summary: SinsalSummary = Field(default_factory=SinsalSummary)
    by_pillar: dict[str, list[str]] = Field(default_factory=dict)
    by_category: dict[str, list[str]] = Field(default_factory=dict)
    full_list: list[SinsalItem] = Field(default_factory=list)
    # 천을귀인 대상 지지(일간 기준, 한자) — 원국 성립 여부와 무관하게 항상 제공.
    # 프론트가 동일 표를 하드코딩 중복하지 않도록 응답에 포함한다.
    cheoneul_targets: list[str] = Field(default_factory=list)
    hour_unknown: bool = False
    catalog_version: str = "default-2024.1"
    warnings: list[str] = Field(default_factory=list)


class TraditionalExtras(BaseModel):
    sinsal: SinsalAnalysis | None = None
    naeum: dict[str, str | None] = Field(default_factory=dict)  # position -> 납음

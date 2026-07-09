"""능동 제안(Direction Suggestion) 계층 타입.

십성군(비겁/식상/재성/관성/인성)의 과다·부족 상태에 작동성(operational)·용신
역할·구조패턴·충파·신강약 신호를 조합해 "이런 방향도 고려해볼 만하다" 수준의
방향 제안을 엔진이 판정하기 위한 사전(`dictionaries/direction_suggestions.json`)
스키마와 판정 결과 타입. E8 Advice Engine(docs/02 §E8, 로드맵 T5.5)의 실구현이다.

설계: `doc/v2_2/docs/15_DIRECTION_SUGGESTIONS.md`.

불변 원칙:
- LLM은 판정하지 않는다 — trigger/channel/guard 매칭은 전부 엔진 계산(절대원칙 1).
- guard 매칭은 차단이 아니라 **서술 반전**: recommend → caution 모드 전환.
- 단정 금지(절대원칙 3): direction 문구는 "고려" 수준, `forbidden_framings`로 차단.
- 십성 단독 판정 금지: 룰별 조건 축(kind) 2종 이상을 lint로 강제(다요소 원칙).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# 십성군 상태 (원국+운 합산 판정 — 설계 §2).
GroupStateValue = Literal[
    "natal_excess",  # 원국 과다 (합산 비중 >= 35%)
    "luck_excess_onset",  # 원국 정상 → 운 유입으로 임계 돌파
    "excess_intensified",  # 원국 과다 + 운 동일군 유입 (심화)
    "natal_deficient",  # 원국 부족 (< 9% 또는 본기 무존재)
    "deficient_persistent",  # 원국 부족 + 운 보충 없음
    "luck_replenished",  # 원국 부족 + 운 유입 — 경고가 아니라 기회 창
    "luck_inflow",  # 임계 무관 운 유입 (보조 조건 전용)
]

# 십성 상태 — active/inactive는 작동 계층(operational) 판정, present/absent는 존재.
TenGodStatusValue = Literal["present", "absent", "active", "inactive", "not_active"]
ConditionKind = Literal[
    "group_state", "ten_god_status", "yongsin_role", "strength_band", "pattern", "conflict"
]
MatchMode = Literal["any", "all"]
SuggestionMode = Literal["recommend", "caution"]

# kind별 필수 필드 (모델 검증 + lint 공용 규격).
_REQUIRED_BY_KIND: dict[str, tuple[str, ...]] = {
    "group_state": ("group", "states"),
    "ten_god_status": ("ten_gods", "status"),
    "yongsin_role": ("target", "roles"),
    "strength_band": ("bands",),
    "pattern": ("pattern_ids",),
    "conflict": ("group", "conflict_kinds"),
}


class SuggestionCondition(BaseModel):
    """판정 조건 1건 — kind가 사용 필드를 결정하는 태그드 유니언.

    엔진(Phase B)이 각 kind를 기존 계산 결과에 매핑한다:
    group_state=합산 과다/부족, ten_god_status=존재/작동성, yongsin_role=용희기구한,
    strength_band=신강약 9단계, pattern=구조패턴 감지, conflict=해당 군 지지 충형파해.
    """

    kind: ConditionKind
    group: str | None = None  # TenGodGroup 값 (group_state / conflict)
    states: list[GroupStateValue] = Field(default_factory=list)  # any-of
    ten_gods: list[str] = Field(default_factory=list)  # 로마자 TenGod enum
    status: TenGodStatusValue | None = None
    match: MatchMode = "any"  # ten_gods 다건일 때 any/all
    target: str | None = None  # yongsin_role: 로마자 십성 또는 십성군 값
    roles: list[str] = Field(default_factory=list)  # 용신/희신/기신/구신/한신
    bands: list[str] = Field(default_factory=list)  # StrengthBand 한글값 (any-of)
    pattern_ids: list[str] = Field(default_factory=list)  # structure_patterns id (any-of)
    conflict_kinds: list[str] = Field(default_factory=list)  # 충/형/파/해 (any-of)

    @model_validator(mode="after")
    def _check_kind_fields(self) -> SuggestionCondition:
        """kind별 필수 필드가 채워졌는지 검증한다."""
        for field_name in _REQUIRED_BY_KIND[self.kind]:
            value = getattr(self, field_name)
            if value is None or value == [] or value == "":
                raise ValueError(f"kind={self.kind} 조건에 {field_name} 필수")
        return self


class DirectionText(BaseModel):
    """권장 서술 재료 — LLM은 이 재료를 '고려' 톤으로 재서술만 한다."""

    headline: str  # 한 줄 방향 (단정 표현 금지)
    actions: list[str] = Field(min_length=1)  # 해볼 만한 방식
    avoid: list[str] = Field(default_factory=list)  # 피하는 게 좋은 방식


class SuggestionChannel(BaseModel):
    """출구 통로 1건 — trigger 성립 후 작동 십성 등 추가 조건으로 분기한다.

    조건(AND)이 하나도 성립하는 통로가 없으면 룰은 제안을 내지 않는다.
    """

    channel_id: str
    name_ko: str
    conditions: list[SuggestionCondition] = Field(min_length=1)  # AND
    direction: DirectionText


class SuggestionSupport(BaseModel):
    """강화 조건 — 매칭 시 제안 강도(strength)를 올린다. 모드는 바꾸지 않는다."""

    condition: SuggestionCondition
    note: str = ""


class SuggestionGuard(BaseModel):
    """위험 조건 — 매칭 시 차단이 아니라 caution 모드로 서술을 반전한다."""

    guard_id: str
    conditions: list[SuggestionCondition] = Field(min_length=1)  # AND
    note: str  # 반전 시 LLM에 전달할 주의 해석


class DirectionRule(BaseModel):
    """`direction_suggestions.json` 의 제안 룰 1건 (십성군 x 과다/부족 base rule).

    발화 의미: trigger(AND) 성립 + channel 1개 이상 성립 → 제안 후보.
    guard 매칭 시 mode=caution 으로 반전하고 caution_headline + 매칭 guard note가
    권장 서술보다 앞선다. support 매칭은 강도만 올린다.
    """

    suggestion_id: str
    name_ko: str
    group: str  # 주 판정 대상 TenGodGroup 값
    reality_note: str  # 상태의 현실 해석 (예: 재성 과다 = 돈보다 책임이 커진 상태)
    trigger: list[SuggestionCondition] = Field(min_length=1)  # AND
    channels: list[SuggestionChannel] = Field(min_length=1)
    supports: list[SuggestionSupport] = Field(default_factory=list)
    guards: list[SuggestionGuard] = Field(default_factory=list)
    caution_headline: str = ""  # guards 존재 시 필수 (lint 강제)
    forbidden_framings: list[str] = Field(default_factory=list)  # 금지 표현
    llm_tag: str  # 압축 설명(120자 이내) — LLM 그대로 전달


class DirectionSuggestionDict(BaseModel):
    """`direction_suggestions.json` 전체."""

    schema_version: str = Field(alias="schema")
    reviewed: bool = False
    purpose: str = ""
    notes: dict[str, str] = Field(default_factory=dict)
    rules: list[DirectionRule] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class DirectionFacts(BaseModel):
    """판정 엔진 입력 사실 집합 (Phase B).

    어댑터(`saju_engines.direction_suggestion.build_direction_facts`)가 기존 계산
    결과(ManseV2Result)에서 조립한다. 평가기는 이 사실만 보고 판정하므로 순수
    함수성이 보장된다. 누락 계층(None)은 빈 값으로 두며, 빈 값은 조건 불일치로
    처리된다(제안을 안 하는 쪽이 안전 — 절대원칙 3).
    """

    group_states: dict[str, list[GroupStateValue]] = Field(default_factory=dict)
    ten_god_present: list[str] = Field(default_factory=list)  # 로마자 — 원국(지장간 포함)+운
    ten_god_active: list[str] = Field(default_factory=list)  # 로마자 — 작동 판정
    yongsin_roles: dict[str, str] = Field(default_factory=dict)  # 십성·군 → 용희기구한
    strength_band: str = ""
    pattern_ids: list[str] = Field(default_factory=list)
    group_conflicts: dict[str, list[str]] = Field(default_factory=dict)  # 군 → 충/형/파/해


class DirectionSuggestion(BaseModel):
    """엔진 판정 결과 1건 (Phase B 출력 — E8 AdviceResult 호환 형태).

    docs/02 §E8의 advice(action/rationale)·cautions에 대응한다. `strength`는
    support 매칭 수 기반 제안 강도(0~1)일 뿐 사건 점수·길흉을 바꾸지 않는다.
    """

    suggestion_id: str
    name_ko: str
    group: str
    group_state: GroupStateValue
    mode: SuggestionMode
    strength: float = Field(ge=0.0, le=1.0)
    channel_id: str
    headline: str  # mode에 따라 direction.headline 또는 caution_headline
    actions: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    reality_note: str = ""
    cautions: list[str] = Field(default_factory=list)  # 매칭 guard note
    matched_guards: list[str] = Field(default_factory=list)
    matched_supports: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # 근거 경로 (조건 매칭 내역)
    forbidden_framings: list[str] = Field(default_factory=list)
    llm_tag: str = ""

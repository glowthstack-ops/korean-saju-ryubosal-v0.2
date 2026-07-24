"""구조 패턴 → 관계 modifier 어댑터 — P1-4 (RELATIONSHIP_EVENT_SYSTEM 부록 D §9).

쟁합·합거·합반·관살혼잡·다중 관계 압박을 관계 벡터의 **파생 modifier**로 변환한다.
구조 패턴은 **독립 발생 원인이 아니다** — 만남·연애 시작을 생성하거나 독립 원인 수·
root trigger 수를 늘리지 않는다(승인 조건). 합성기(P1-5)가 다음처럼 소비한다:

  쟁합       → ambiguity 증가 + stability support 약화(합 결속의 재분류)
  합거       → realization blocker 후보
  합반       → realization 지연·불완전
  관살혼잡   → 선택 복잡성·관계 모호성 보조(만남 발생 원인 아님)
  다중 압박  → 집중 분산·ambiguity 보조

natal 정적 패턴(관살혼잡 등)에는 가짜 transit trigger를 만들지 않는다 —
`structural_context_id = natal:{PATTERN}` + trigger 없음. 운 파생 패턴은
`derived_from_evidence_ids`로 기저 evidence를 역추적한다(§9).
shadow 전용 — 점수·후보·가드 어디에도 관여하지 않는다(부록 D-3).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from saju_shared_types.structure_patterns import DetectedPattern


class StructureModifierEffect(StrEnum):
    """modifier 효과 종류 — 합성기 소비 어휘(발생 원인 아님)."""

    AMBIGUITY_INCREASE = "ambiguity_increase"
    REALIZATION_BLOCKER = "realization_blocker"
    REALIZATION_DELAY = "realization_delay"
    STABILITY_SUPPORT_WEAKEN = "stability_support_weaken"
    SELECTION_COMPLEXITY = "selection_complexity"
    FOCUS_DILUTION = "focus_dilution"


# modifier가 제한적으로 작용할 수 있는 축(P1-5 승인 §3) — ambiguity·선택 복잡성·
# 집중 분산은 7축이 아니라 modifier_kind이며, **숨은 8번째 축으로 수치화 금지**.
# 최종 벡터 반영은 여기 열거된 기존 축에만 허용된다(합성기 소관).
_PATTERN_AFFECTS: dict[str, tuple[str, ...]] = {
    "JAENGHAP": ("stability", "realization"),        # activation 직접 상승 금지
    "HAPGEO": ("realization",),
    "HAPBAN": ("realization",),
    "GWANSAL_HONJAP": ("stability",),                # 만남·결혼 발생 원인 아님
    "MULTI_RELATION_STRESS": ("stability",),
}


class RelationshipStructureModifier(BaseModel):
    """관계 modifier 1건 — 독립 원인·root trigger 수에 불포함."""

    pattern_id: str
    effects: list[StructureModifierEffect]
    # 작용 허용 축(7축 어휘 한정) — 이 밖의 축·신규 수치 축 생성 금지.
    affects_axes: list[str] = Field(default_factory=list)
    strength: float = 0.0               # 패턴 성립 강도(0~1) — 길흉·발생 아님
    # natal 정적 출처(가짜 transit trigger 금지) — 운 파생이면 None.
    structural_context_id: str | None = None
    # 운 파생 패턴의 기저 evidence 역추적(§9) — natal 정적이면 빈 목록.
    derived_from_evidence_ids: list[str] = Field(default_factory=list)


# 관계 소관 패턴 → 효과 매핑(승인 §9 표). 표 밖 패턴은 관계 modifier를 만들지 않는다.
_PATTERN_EFFECTS: dict[str, list[StructureModifierEffect]] = {
    "JAENGHAP": [
        StructureModifierEffect.AMBIGUITY_INCREASE,
        StructureModifierEffect.STABILITY_SUPPORT_WEAKEN,
    ],
    "HAPGEO": [StructureModifierEffect.REALIZATION_BLOCKER],
    "HAPBAN": [StructureModifierEffect.REALIZATION_DELAY],
    "GWANSAL_HONJAP": [
        StructureModifierEffect.SELECTION_COMPLEXITY,
        StructureModifierEffect.AMBIGUITY_INCREASE,
    ],
    "MULTI_RELATION_STRESS": [
        StructureModifierEffect.FOCUS_DILUTION,
        StructureModifierEffect.AMBIGUITY_INCREASE,
    ],
}
# natal 정적 구조(운 자극 전에는 성향·구조 — 사건 원인 아님).
_NATAL_STATIC = frozenset({"GWANSAL_HONJAP"})


def build_relationship_structure_modifiers(
    patterns: list[DetectedPattern],
    *,
    derived_from_by_pattern: dict[str, list[str]] | None = None,
) -> list[RelationshipStructureModifier]:
    """감지 패턴 → 관계 modifier 목록(순수 함수·shadow 전용).

    Args:
        patterns: structure_patterns 감지 결과(원 파이프라인 불변 — 읽기만).
        derived_from_by_pattern: 운 파생 패턴의 기저 evidence 역추적
            (pattern_id → evidence_id 목록). natal 정적 패턴에는 적용하지 않는다.

    Returns:
        관계 소관 패턴의 modifier만(그 외 패턴 무시). 독립 원인 수 기여 없음.
    """
    derived = derived_from_by_pattern or {}
    out: list[RelationshipStructureModifier] = []
    for p in patterns:
        effects = _PATTERN_EFFECTS.get(p.pattern_id)
        if effects is None:
            continue
        is_natal = p.pattern_id in _NATAL_STATIC
        out.append(RelationshipStructureModifier(
            pattern_id=p.pattern_id,
            effects=list(effects),
            affects_axes=list(_PATTERN_AFFECTS.get(p.pattern_id, ())),
            strength=float(getattr(p, "strength", 0.0) or 0.0),
            structural_context_id=f"natal:{p.pattern_id}" if is_natal else None,
            derived_from_evidence_ids=[] if is_natal else list(derived.get(p.pattern_id, [])),
        ))
    return out

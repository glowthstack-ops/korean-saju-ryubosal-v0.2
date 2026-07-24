"""7축 관계 효과 벡터 합성기 — P1-5 (RELATIONSHIP_EVENT_SYSTEM §4·부록 D, 2026-07-24 승인).

최우선 규칙(승인 최종 결정): **같은 `signal_trigger_id`에서 파생된 RelationPalace·MT2·
복수 관계 kind는 모두 evidence로 보존하되, root 축 기여는 한 번만 계산하고 복합성은
제한된 보정으로만 반영한다.** 어댑터의 base 총량(단순 합)은 진단값일 뿐 최종 축이
아니다 — 합성기가 root-normalized 값·band를 재산출한다.

합성 순서(승인 §4): (정밀도 우선·완전 중복은 어댑터 소관) → root trigger별 그룹화 →
root별 기본 축 기여(주 기여 + 제한 복합 보정) → 서로 다른 root 합성 → structure
modifier(affects_axes 한정) → blocker → AxisStatus·value·band 결정.

P1 평가 범위(승인 §3): activation·stability·separation_pressure만. exposure·
formalization·experience_valence는 미평가 유지(충·형≠부정 경험 확정). realization은
positive base evidence가 없으므로 INSUFFICIENT + blocker 보존 — **P1에서 BLOCKED
0건이 정상**(억지 상태 생성 금지).

shadow 전용(D-3 확대 불변식): 점수·confidence·랭킹·timeline·stage·가드·LLM/리포트
입력 어디에도 관여하지 않는다. recommended_event_key·stage 전이·확률류 필드는
P3/P4 소관이라 결과에 두지 않는다(승인 §9).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from saju_shared_types.relationship_effect import (
    AxisStatus,
    RelationshipActivationEvidence,
    RelationshipAxisValue,
    RelationshipEffectVector,
    TriggerPrecision,
    unevaluated,
)

from .relationship_structure_modifiers import (
    RelationshipStructureModifier,
    StructureModifierEffect,
)

# 부정 kind(분리 압력 평가 대상)와 kind별 압력·안정성 기여 — spouse_palace_activation과
# 동일 서열(§5 표). EMERGENCE(MT2)는 압력·안정성 기여 없음(보조 evidence).
_SEP_WEIGHT = {"CHUNG": 1.0, "HYEONG": 0.6, "HAE": 0.55, "PA": 0.55}
_STAB_SUPPORT = {"HAP": 0.3}
_STAB_PRESSURE = {"CHUNG": 1.0, "HYEONG": 0.8, "HAE": 0.6, "PA": 0.6}

# 같은 root 안의 복합 보정 계수(승인 §1-1 — 단순 합산 금지, 초안·shadow 감사 대상):
# 주 기여(최강) + SECONDARY_FACTOR × 나머지 기여.
_SECONDARY_FACTOR = 0.3
# 쟁합의 binding support 약화 계수(강도 비례) — P1 초안.
_JAENGHAP_SUPPORT_WEAKEN = 0.5


class RootEffectContribution(BaseModel):
    """root(실제 운 신호) 1개의 축 기여 — 승인 §1-1 권장 구조."""

    signal_trigger_id: str | None       # None = 미해소(PROVISIONAL — root 수 불포함)
    evidence_ids: list[str] = Field(default_factory=list)
    activation: float = 0.0
    stability_support: float = 0.0
    stability_pressure: float = 0.0
    separation_pressure: float = 0.0
    kinds: list[str] = Field(default_factory=list)


class RelationshipEffectVectorResult(BaseModel):
    """합성 결과(승인 §9) — shadow 전용, 사건 승격 필드 없음."""

    axes: RelationshipEffectVector
    evidence: list[RelationshipActivationEvidence] = Field(default_factory=list)
    modifiers: list[RelationshipStructureModifier] = Field(default_factory=list)
    blockers: list[RelationshipActivationEvidence] = Field(default_factory=list)

    evidence_count: int = 0
    semantic_evidence_group_count: int = 0
    # 사건 승격의 '독립 원인 수' 기준(승인 §5) — evidence 수·그룹 수와 혼용 금지.
    independent_root_trigger_count: int = 0
    unresolved_trigger_evidence_count: int = 0

    root_contributions: list[RootEffectContribution] = Field(default_factory=list)
    static_context_ids: list[str] = Field(default_factory=list)

    usage: str = "shadow_only"


def _primary_plus_secondary(values: list[float]) -> float:
    """주 기여 + 제한 복합 보정(같은 root 단순 합산 금지 — 승인 §1-1)."""
    if not values:
        return 0.0
    ordered = sorted(values, reverse=True)
    return ordered[0] + _SECONDARY_FACTOR * sum(ordered[1:])


def _band(value: float, *, strong: float, moderate: float, weak: float) -> str:
    if value >= strong:
        return "strong"
    if value >= moderate:
        return "moderate"
    if value >= weak:
        return "weak"
    return "low"


def synthesize_relationship_effect_vector(
    evidences: list[RelationshipActivationEvidence],
    *,
    blockers: list[RelationshipActivationEvidence] | None = None,
    modifiers: list[RelationshipStructureModifier] | None = None,
) -> RelationshipEffectVectorResult:
    """evidence·blocker·modifier → root-normalized 7축 벡터(shadow).

    Args:
        evidences: 어댑터 산출(배우자궁·MT2 — 정밀도 우선·중복 제거 완료본).
            배우자궁 축 기여는 on_spouse_palace=True인 evidence만 사용한다.
        blockers: MT2 clashed 등 — realization 축은 positive base 부재로
            INSUFFICIENT 유지 + blocker_ids 보존(BLOCKED 생성 금지).
        modifiers: 구조 패턴 — affects_axes 한정 적용(쟁합=support 약화),
            base evidence 없으면 어떤 축도 새로 평가하지 않는다.
    """
    blockers = blockers or []
    modifiers = modifiers or []
    day_evidence = [e for e in evidences if e.on_spouse_palace]

    # root 그룹화 — EXACT/COMPONENT signal별. PROVISIONAL·signal 없음은 각각 미해소
    # 그룹(축 기여는 보수적으로 개별 산출하되 root 수에는 불포함 — 승인 §3).
    roots: dict[str | None, list[RelationshipActivationEvidence]] = {}
    unresolved_keys: list[str] = []
    for e in day_evidence:
        if (e.signal_trigger_id is not None
                and e.trigger_precision is not TriggerPrecision.PROVISIONAL):
            roots.setdefault(e.signal_trigger_id, []).append(e)
        else:
            ukey: str | None = f"__unresolved__:{e.evidence_id}"
            unresolved_keys.append(str(ukey))
            roots.setdefault(ukey, []).append(e)

    contributions: list[RootEffectContribution] = []
    for key in sorted(roots, key=str):
        group = roots[key]
        key_str = str(key)
        # kind 단위 기여(같은 root의 참여자별 중복 kind는 kind 1회 — 같은 글자 하나가
        # 원국 여러 글자를 친 경우 압력을 원인 2처럼 세지 않는다: 승인 §8).
        kinds = sorted({e.relation_kind for e in group})
        act_by_kind: dict[str, float] = {}
        for e in group:
            act_by_kind[e.relation_kind] = max(
                act_by_kind.get(e.relation_kind, 0.0), e.base_relation_strength
            )
        activation = _primary_plus_secondary(list(act_by_kind.values()))
        sep_vals = [_SEP_WEIGHT[k] for k in kinds if k in _SEP_WEIGHT]
        separation = _primary_plus_secondary(sep_vals)
        support = sum(_STAB_SUPPORT.get(k, 0.0) for k in kinds)
        pressure = _primary_plus_secondary(
            [_STAB_PRESSURE[k] for k in kinds if k in _STAB_PRESSURE]
        )
        contributions.append(RootEffectContribution(
            signal_trigger_id=None if key_str.startswith("__unresolved__") else key,
            evidence_ids=[e.evidence_id for e in group],
            activation=round(activation, 3),
            stability_support=round(support, 3),
            stability_pressure=round(pressure, 3),
            separation_pressure=round(separation, 3),
            kinds=kinds,
        ))

    # 서로 다른 root 합성(독립 신호 — 합산 허용).
    total_activation = sum(c.activation for c in contributions)
    total_support = sum(c.stability_support for c in contributions)
    total_pressure = sum(c.stability_pressure for c in contributions)
    total_separation = sum(c.separation_pressure for c in contributions)
    has_negative = any(
        k in _SEP_WEIGHT for c in contributions for k in c.kinds
    )
    ev_ids = [e.evidence_id for e in day_evidence]

    # 구조 modifier — affects_axes 한정, base evidence 없으면 축 평가 생성 금지(승인 §4).
    static_ids: list[str] = []
    seen_static: set[str] = set()
    deduped_modifiers: list[RelationshipStructureModifier] = []
    for m in modifiers:
        if m.structural_context_id is not None:
            # natal 정적 — structural_context_id 기준 dedupe(기간 반복 비누적).
            if m.structural_context_id in seen_static:
                continue
            seen_static.add(m.structural_context_id)
            static_ids.append(m.structural_context_id)
        deduped_modifiers.append(m)
        if contributions and "stability" in m.affects_axes \
                and StructureModifierEffect.STABILITY_SUPPORT_WEAKEN in m.effects:
            total_support *= max(0.0, 1.0 - _JAENGHAP_SUPPORT_WEAKEN * m.strength)

    axes = RelationshipEffectVector()
    if contributions:
        axes.activation = RelationshipAxisValue(
            status=AxisStatus.EVALUATED, value=round(total_activation, 3),
            band=_band(total_activation, strong=20.0, moderate=12.0, weak=6.0),
            evidence_ids=ev_ids,
        )
        # stability — 상쇄 0(support·pressure 공존)은 EVALUATED, 무근거는 상위 else.
        net = round(total_support - total_pressure, 3)
        axes.stability = RelationshipAxisValue(
            status=AxisStatus.EVALUATED, value=net,
            band=("weak" if net <= -0.8 else "moderate" if net < 0.3 else "strong"),
            evidence_ids=ev_ids,
        )
        if has_negative:
            axes.separation_pressure = RelationshipAxisValue(
                status=AxisStatus.EVALUATED, value=round(total_separation, 3),
                band=_band(total_separation, strong=0.9, moderate=0.55, weak=0.3),
                evidence_ids=ev_ids,
            )
        else:
            # 부정 신호 없음 ≠ 분리 위험 낮음.
            axes.separation_pressure = RelationshipAxisValue(
                status=AxisStatus.INSUFFICIENT_EVIDENCE, evidence_ids=ev_ids,
            )
    # realization — positive base 부재(P1): blocker가 있어도 BLOCKED 생성 금지.
    axes.realization = RelationshipAxisValue(
        status=AxisStatus.INSUFFICIENT_EVIDENCE,
        blocker_ids=[b.evidence_id for b in blockers] + [
            m.pattern_id for m in deduped_modifiers
            if StructureModifierEffect.REALIZATION_BLOCKER in m.effects
        ],
    )
    axes.exposure = unevaluated()
    axes.formalization = unevaluated()
    axes.experience_valence = unevaluated()

    resolved_roots = {
        c.signal_trigger_id for c in contributions if c.signal_trigger_id is not None
    }
    return RelationshipEffectVectorResult(
        axes=axes,
        evidence=list(evidences),
        modifiers=deduped_modifiers,
        blockers=list(blockers),
        evidence_count=len(evidences),
        semantic_evidence_group_count=len(
            {e.independent_cause_group for e in evidences}
        ),
        independent_root_trigger_count=len(resolved_roots),
        unresolved_trigger_evidence_count=len(unresolved_keys),
        root_contributions=contributions,
        static_context_ids=static_ids,
    )

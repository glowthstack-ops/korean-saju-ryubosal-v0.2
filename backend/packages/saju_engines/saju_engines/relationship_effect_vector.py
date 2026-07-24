"""7축 관계 효과 벡터 합성기 — P1-5 (RELATIONSHIP_EVENT_SYSTEM §4·부록 D, 2026-07-24 승인).

최우선 규칙: **같은 `signal_trigger_id`에서 파생된 RelationPalace·MT2·복수 관계 kind는
모두 evidence로 보존하되, root 축 기여는 한 번만 계산하고 복합성은 제한 보정으로만
반영한다.** 어댑터의 base 총량(단순 합)은 진단값일 뿐 최종 축이 아니다.

명칭 정정(폐쇄 보완 §6): 본 합성은 root-**deduplicated/composed**다 — 같은 root 내
중복만 제거하고 서로 다른 root 기여는 합산하므로 상한 정규화(normalization)가 아니다.
band 임계(6/12/20)와 SECONDARY_FACTOR(0.3)는 **provisional calibration 값**이며 P1-6
telemetry(root 수별 분포·kind 조합·strong 비율·legacy cap 포화 비교)로 감사 후 P3
사용 전 별도 캘리브레이션한다.

폐쇄 보완(2026-07-24 §1~§5):
- PROVISIONAL evidence는 **숫자 축에 가산하지 않는다**(중복 확인 불가 신호를 독립
  신호로 간주하는 과대 반영 차단) — 보존+unresolved 계측만. resolved root가 없으면
  축은 INSUFFICIENT_EVIDENCE.
- AxisStatus는 contributions 존재가 아니라 **축별 적용 가능 evidence 존재**로 결정
  (MT2 emergence 단독 → activation만 평가, stability·separation은 근거 없음).
- modifier는 derived root에만 적용(전체 support 일괄 약화 금지). derived도
  structural_context_id도 없으면 적용 보류(메타 보존만). 동일 static ID는
  strength=max·effects/affects/derived=union으로 **입력 순서 불변** 병합.
- 축별 evidence_ids는 실제 기여 evidence만(감사 정확성).

P1 평가 범위: activation·stability·separation만. realization은 blocker 보존+
INSUFFICIENT(**BLOCKED 0건 정상**). shadow 전용(D-3) — 승격류 필드 없음.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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

# kind별 축 기여 자격(§4 산출 책임) — EMERGENCE(MT2)는 activation만(보조 evidence).
_SEP_WEIGHT = {"CHUNG": 1.0, "HYEONG": 0.6, "HAE": 0.55, "PA": 0.55}
_STAB_SUPPORT = {"HAP": 0.3}
_STAB_PRESSURE = {"CHUNG": 1.0, "HYEONG": 0.8, "HAE": 0.6, "PA": 0.6}
_ACTIVATION_KINDS = frozenset(
    {"HAP", "CHUNG", "HYEONG", "PA", "HAE", "BOKEUM", "EMERGENCE"}
)

# 버전(P1-6 §5-2) — processing key에 포함해 계수 변경 후 재감사가 이전 telemetry와
# dedupe되지 않게 한다. 계수·band 변경 시 CALIBRATION_VERSION을 반드시 올린다.
RELATIONSHIP_VECTOR_SCHEMA_VERSION = "p1.1"
RELATIONSHIP_CALIBRATION_VERSION = "cal-2026-07-24.1"

# provisional calibration(§6) — shadow 감사 후 P3 전 재조정 대상.
# 이 상수들이 BASELINE_CALIBRATION의 단일 source다(drift lint가 명세와 일치 강제).
_SECONDARY_FACTOR = 0.3
_SUPPORT_WEAKEN = 0.5
_ACT_BAND = {"strong": 20.0, "moderate": 12.0, "weak": 6.0}


class RelationshipVectorCalibration(BaseModel):
    """벡터 캘리브레이션 profile(P2-1 §8) — 합성기에 명시 주입한다(전역 monkeypatch 금지).

    production 경로는 BASELINE_CALIBRATION만 쓴다. 감사 harness만 실험 profile을
    전달한다. `profile_id`는 실험 run 구분용이며 **공식 CALIBRATION_VERSION과 별개**
    (실험이 운영 telemetry 버전을 오염시키지 않게 — §8). 필드 기본값 = 현행 상수라
    `RelationshipVectorCalibration()`은 기존 결과와 byte-identical(§9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = "baseline"
    secondary_factor: float = _SECONDARY_FACTOR
    support_weaken: float = _SUPPORT_WEAKEN
    activation_band: dict[str, float] = Field(
        default_factory=lambda: dict(_ACT_BAND))
    stability_support: dict[str, float] = Field(
        default_factory=lambda: dict(_STAB_SUPPORT))
    stability_pressure: dict[str, float] = Field(
        default_factory=lambda: dict(_STAB_PRESSURE))
    separation_weight: dict[str, float] = Field(
        default_factory=lambda: dict(_SEP_WEIGHT))
    # signed stability band 경계: (weak_max_inclusive, moderate_max_exclusive).
    stability_band: tuple[float, float] = (-0.8, 0.3)
    separation_band: dict[str, float] = Field(
        default_factory=lambda: {"strong": 0.9, "moderate": 0.55, "weak": 0.3})


BASELINE_CALIBRATION = RelationshipVectorCalibration()


class RootEffectContribution(BaseModel):
    """root(실제 운 신호) 1개의 축 기여 — EXACT/COMPONENT signal만 생성된다."""

    signal_trigger_id: str
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

    # 카운트 의미(폐쇄 보완 §4): retained=보존 전체 / contributing=축 숫자에 실제
    # 기여(일지+resolved) / noncontributing=보존만(비일지·PROVISIONAL). evidence_count는
    # retained의 별칭(호환) — 사건 승격 근거로는 contributing·root만 사용한다.
    evidence_count: int = 0
    retained_evidence_count: int = 0
    contributing_evidence_count: int = 0
    noncontributing_evidence_count: int = 0
    semantic_evidence_group_count: int = 0
    independent_root_trigger_count: int = 0
    unresolved_trigger_evidence_count: int = 0

    root_contributions: list[RootEffectContribution] = Field(default_factory=list)
    static_context_ids: list[str] = Field(default_factory=list)
    # 동일 static ID에 상이한 의미 payload(effects·affects 불일치) — 수치 적용 보류
    # 건수(P1-6 승인 §4: telemetry는 count만, 원문 미기록).
    static_modifier_conflict_count: int = 0
    # 동일 canonical key(pattern_id+evidence set)인데 payload 불일치한 derived modifier
    # 수치 적용 보류 건수(P2 hardening — 자동 2회 적용·max 금지, static과 일관).
    derived_modifier_conflict_count: int = 0
    # supersession 연쇄·순환·유실 계측(P1-6 §1) — 순환·유실은 수치 적용 보류.
    supersession_cycle_count: int = 0
    supersession_target_missing_count: int = 0
    # 복수 root 참조 modifier(P1-6 §2) — root마다 strength 반복 적용 금지: P1은 보류.
    modifier_multi_root_hold_count: int = 0
    # 어댑터에서 EXACT로 대체된 잠정 evidence 수(pass-through — superseded_map 크기).
    superseded_provisional_count: int = 0

    usage: str = "shadow_only"


def _primary_plus_secondary(values: list[float], secondary_factor: float) -> float:
    """주 기여 + 제한 복합 보정(같은 root 단순 합산 금지)."""
    if not values:
        return 0.0
    ordered = sorted(values, reverse=True)
    return ordered[0] + secondary_factor * sum(ordered[1:])


def _band(value: float, *, strong: float, moderate: float, weak: float) -> str:
    if value >= strong:
        return "strong"
    if value >= moderate:
        return "moderate"
    if value >= weak:
        return "weak"
    return "low"


def resolve_canonical_evidence_id(
    evidence_id: str,
    superseded_map: dict[str, str],
    valid_ids: set[str],
) -> tuple[str | None, str]:
    """supersession 연쇄를 최종 canonical evidence까지 추적(P1-6 §1).

    Returns:
        (canonical_id | None, status) — status: ok | cycle | missing.
        순환·유실(fail-closed)이면 canonical=None(수치 미적용, 계측만).
    """
    seen: set[str] = set()
    cur = evidence_id
    while cur in superseded_map:
        if cur in seen:
            return None, "cycle"
        seen.add(cur)
        cur = superseded_map[cur]
    if cur not in valid_ids:
        return None, "missing"
    return cur, "ok"


def _derived_key(m: RelationshipStructureModifier) -> tuple[str, tuple[str, ...]]:
    """derived(transit) modifier의 canonical identity(P2 hardening).

    (pattern_id, canonical derived evidence set). derived_from은 합성기 진입 전
    supersession remap으로 이미 canonical(EXACT/COMPONENT)이라 supersession 전후
    같은 root를 참조하면 동일 key가 된다. root set 정렬로 입력 순서 불변.
    """
    return (m.pattern_id, tuple(sorted(m.derived_from_evidence_ids)))


def _merge_modifiers(
    modifiers: list[RelationshipStructureModifier],
) -> tuple[
    list[RelationshipStructureModifier], list[str], int, set[str],
    int, set[tuple[str, tuple[str, ...]]],
]:
    """static ID 병합 + derived modifier 멱등 dedup(P2 hardening).

    static: 같은 structural_context_id는 strength=max·union 병합. effects·affects
    불일치는 static_modifier_conflict로 세고 수치 적용 보류(P1-6 §4).

    derived(transit): 같은 canonical key(pattern_id + canonical evidence set)는 **1회만**
    적용한다(중복 입력 멱등 — 합성기 계약). 동일 key인데 effects·affects·strength가
    불일치하면 derived_modifier_conflict로 세고 그 key의 **수치 적용을 보류**한다
    (자동 2회 적용·무조건 max 금지 — static fail-closed와 일관). 같은 pattern이라도
    root set이 다르면 별개 modifier로 유지. 입력 순서 불변(결과 정렬).
    """
    by_static: dict[str, RelationshipStructureModifier] = {}
    conflicts: set[str] = set()
    transit_raw: list[RelationshipStructureModifier] = []
    for m in modifiers:
        sid = m.structural_context_id
        if sid is None:
            transit_raw.append(m)
            continue
        prev = by_static.get(sid)
        if prev is None:
            by_static[sid] = m
        else:
            if set(prev.effects) != set(m.effects) \
                    or set(prev.affects_axes) != set(m.affects_axes):
                conflicts.add(sid)  # 의미 payload 불일치 — 수치 적용 보류 대상
            by_static[sid] = prev.model_copy(update={
                "strength": max(prev.strength, m.strength),
                "effects": sorted(set(prev.effects) | set(m.effects)),
                "affects_axes": sorted(set(prev.affects_axes) | set(m.affects_axes)),
                "derived_from_evidence_ids": sorted(
                    set(prev.derived_from_evidence_ids)
                    | set(m.derived_from_evidence_ids)
                ),
            })
    # derived 멱등 dedup — 같은 canonical key는 1회, payload 불일치는 conflict 보류.
    by_derived: dict[tuple[str, tuple[str, ...]], RelationshipStructureModifier] = {}
    derived_conflicts: set[tuple[str, tuple[str, ...]]] = set()
    for m in transit_raw:
        key = _derived_key(m)
        prev = by_derived.get(key)
        if prev is None:
            by_derived[key] = m
        elif (sorted(prev.effects) != sorted(m.effects)
              or sorted(prev.affects_axes) != sorted(m.affects_axes)
              or prev.strength != m.strength):
            derived_conflicts.add(key)  # 동일 key·다른 payload — 수치 적용 보류
    merged = sorted(by_static.values(), key=lambda m: m.structural_context_id or "")
    merged += sorted(by_derived.values(), key=_derived_key)
    return (merged, sorted(by_static), len(conflicts), conflicts,
            len(derived_conflicts), derived_conflicts)


def synthesize_relationship_effect_vector(
    evidences: list[RelationshipActivationEvidence],
    *,
    blockers: list[RelationshipActivationEvidence] | None = None,
    modifiers: list[RelationshipStructureModifier] | None = None,
    superseded_map: dict[str, str] | None = None,
    calibration: RelationshipVectorCalibration | None = None,
) -> RelationshipEffectVectorResult:
    """evidence·blocker·modifier → root-deduplicated 7축 벡터(shadow).

    Args:
        evidences: 어댑터 산출(배우자궁·MT2). 축 숫자 기여는 on_spouse_palace=True이며
            EXACT/COMPONENT signal을 가진 evidence만 — PROVISIONAL은 보존·계측 전용.
        blockers: MT2 clashed 등 — realization은 INSUFFICIENT+blocker 보존(BLOCKED 금지).
        modifiers: 구조 패턴 — derived root에만 적용, 동일 static ID는 순서 불변 병합.
        calibration: 계수 profile(P2-1 §8) — None이면 BASELINE_CALIBRATION(현행 상수).
            production 경로는 None(BASELINE)만 전달, 감사 harness만 실험 profile 주입.
            BASELINE은 기존 결과와 byte-identical(§9).
    """
    cal = calibration or BASELINE_CALIBRATION
    blockers = blockers or []
    modifiers = modifiers or []
    superseded_map = superseded_map or {}
    valid_ids = {e.evidence_id for e in evidences}
    cycle_count = 0
    missing_count = 0
    # modifier의 derived 참조를 canonical resolver로 해소(P1-6 §1 — 연쇄 추적·순환/
    # 유실 fail-closed). 해소 실패 참조는 제거되어 해당 modifier는 자연 보류된다.
    if modifiers:
        remapped: list[RelationshipStructureModifier] = []
        for m in modifiers:
            if not m.derived_from_evidence_ids:
                remapped.append(m)
                continue
            resolved: set[str] = set()
            for i in m.derived_from_evidence_ids:
                canon, status = resolve_canonical_evidence_id(
                    i, superseded_map, valid_ids)
                if status == "cycle":
                    cycle_count += 1
                elif status == "missing":
                    missing_count += 1
                elif canon is not None:
                    resolved.add(canon)
            remapped.append(m.model_copy(
                update={"derived_from_evidence_ids": sorted(resolved)}))
        modifiers = remapped
    day_evidence = [e for e in evidences if e.on_spouse_palace]

    # root 그룹화(폐쇄 §1) — resolved(EXACT/COMPONENT)만 축 숫자에 반영.
    roots: dict[str, list[RelationshipActivationEvidence]] = {}
    unresolved: list[RelationshipActivationEvidence] = []
    for e in day_evidence:
        if (e.signal_trigger_id is not None
                and e.trigger_precision is not TriggerPrecision.PROVISIONAL):
            roots.setdefault(e.signal_trigger_id, []).append(e)
        else:
            unresolved.append(e)

    contributions: list[RootEffectContribution] = []
    for key in sorted(roots):
        group = roots[key]
        kinds = sorted({e.relation_kind for e in group})
        act_by_kind: dict[str, float] = {}
        for e in group:
            if e.relation_kind in _ACTIVATION_KINDS:
                act_by_kind[e.relation_kind] = max(
                    act_by_kind.get(e.relation_kind, 0.0), e.base_relation_strength
                )
        contributions.append(RootEffectContribution(
            signal_trigger_id=key,
            evidence_ids=[e.evidence_id for e in group],
            activation=round(_primary_plus_secondary(
                list(act_by_kind.values()), cal.secondary_factor), 3),
            stability_support=round(
                sum(cal.stability_support.get(k, 0.0) for k in kinds), 3),
            stability_pressure=round(_primary_plus_secondary(
                [cal.stability_pressure[k] for k in kinds
                 if k in cal.stability_pressure], cal.secondary_factor), 3),
            separation_pressure=round(_primary_plus_secondary(
                [cal.separation_weight[k] for k in kinds
                 if k in cal.separation_weight], cal.secondary_factor), 3),
            kinds=kinds,
        ))

    # 축별 기여 evidence(폐쇄 §2·§4) — AxisStatus·evidence_ids의 기준.
    def _ids(pred) -> list[str]:
        return [e.evidence_id for c in contributions for e in _by_id(c.evidence_ids)
                if pred(e)]

    id_map = {e.evidence_id: e for e in day_evidence}

    def _by_id(ids: list[str]) -> list[RelationshipActivationEvidence]:
        return [id_map[i] for i in ids]

    activation_ids = _ids(lambda e: e.relation_kind in _ACTIVATION_KINDS)
    stability_ids = _ids(
        lambda e: e.relation_kind in _STAB_SUPPORT or e.relation_kind in _STAB_PRESSURE)
    separation_ids = _ids(lambda e: e.relation_kind in _SEP_WEIGHT)

    # modifier(폐쇄 §3) — 병합·멱등 dedup(순서 불변) 후 derived root에만 적용.
    (deduped_modifiers, static_ids, static_conflicts, conflicted_sids,
     derived_conflicts, conflicted_derived_keys) = _merge_modifiers(modifiers)
    multi_root_hold = 0
    for m in deduped_modifiers:
        if StructureModifierEffect.STABILITY_SUPPORT_WEAKEN not in m.effects \
                or "stability" not in m.affects_axes:
            continue
        if m.structural_context_id in conflicted_sids:
            continue  # 의미 payload 충돌 — 데이터 계약 위반: 수치 적용 보류(§3)
        if m.structural_context_id is None \
                and _derived_key(m) in conflicted_derived_keys:
            continue  # derived 동일 key·payload 충돌 — 수치 적용 보류(P2 hardening)
        factor = max(0.0, 1.0 - cal.support_weaken * m.strength)
        if m.derived_from_evidence_ids:
            targets = set(m.derived_from_evidence_ids)
            matched = [c for c in contributions if targets & set(c.evidence_ids)]
            if len(matched) > 1:
                # 복수 root 참조 — strength를 root마다 반복 적용하면 효과가 배가된다.
                # P1은 보수적으로 수치 보류(ROOT_SET 메타 보존·계측만 — 승인 §2).
                multi_root_hold += 1
                continue
            for c in matched:
                c.stability_support = round(c.stability_support * factor, 3)
                stability_ids = sorted(set(stability_ids) | {m.pattern_id})
        elif m.structural_context_id is not None:
            # 명시적 global(natal static) scope — 전체 support에 적용.
            for c in contributions:
                c.stability_support = round(c.stability_support * factor, 3)
        # derived도 static도 없으면 적용 보류(메타 보존만 — 대상 불명).

    total_activation = sum(c.activation for c in contributions)
    total_support = sum(c.stability_support for c in contributions)
    total_pressure = sum(c.stability_pressure for c in contributions)
    total_separation = sum(c.separation_pressure for c in contributions)

    axes = RelationshipEffectVector()
    if activation_ids:
        axes.activation = RelationshipAxisValue(
            status=AxisStatus.EVALUATED, value=round(total_activation, 3),
            band=_band(total_activation, **cal.activation_band),
            evidence_ids=sorted(set(activation_ids)),
        )
    if stability_ids:
        net = round(total_support - total_pressure, 3)
        _stab_weak_max, _stab_mod_max = cal.stability_band
        axes.stability = RelationshipAxisValue(
            status=AxisStatus.EVALUATED, value=net,
            band=("weak" if net <= _stab_weak_max
                  else "moderate" if net < _stab_mod_max else "strong"),
            evidence_ids=sorted(set(stability_ids)),
        )
    if separation_ids:
        axes.separation_pressure = RelationshipAxisValue(
            status=AxisStatus.EVALUATED, value=round(total_separation, 3),
            band=_band(total_separation, **cal.separation_band),
            evidence_ids=sorted(set(separation_ids)),
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

    contributing = {i for c in contributions for i in c.evidence_ids}
    return RelationshipEffectVectorResult(
        axes=axes,
        evidence=list(evidences),
        modifiers=deduped_modifiers,
        blockers=list(blockers),
        evidence_count=len(evidences),
        retained_evidence_count=len(evidences),
        contributing_evidence_count=len(contributing),
        noncontributing_evidence_count=len(evidences) - len(contributing),
        semantic_evidence_group_count=len(
            {e.independent_cause_group for e in evidences}
        ),
        independent_root_trigger_count=len(contributions),
        unresolved_trigger_evidence_count=len(unresolved),
        root_contributions=contributions,
        static_context_ids=static_ids,
        static_modifier_conflict_count=static_conflicts,
        derived_modifier_conflict_count=derived_conflicts,
        supersession_cycle_count=cycle_count,
        supersession_target_missing_count=missing_count,
        modifier_multi_root_hold_count=multi_root_hold,
        superseded_provisional_count=len(superseded_map),
    )

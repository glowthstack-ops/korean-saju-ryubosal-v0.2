"""배우자궁 활성화 → 관계 효과 벡터 어댑터 — P1-2 (RELATIONSHIP_EVENT_SYSTEM §5·부록 D).

입력은 **cap 이전 typed hit**(RelationActivation)이다 — legacy delta(상한 22 적용 후)를
재변환하지 않는다: 충 단독 = 충×2+형 = 파×2+COMPOUND가 전부 +22로 뭉개진 값에서는
복합 구조를 복원할 수 없다(P0-A A-3 #3). raw_strength는 legacy와 동일한 사전 산식
(kind 보너스 × 궁 activation_weight × 층위 × 위치)을 cap 없이 계산한다.

P1-2 평가 범위(부록 D 승인 표):
- activation: 평가 / stability: 합충형파해 종류 기반 제한 평가(signed —
  음수=불안정 압력·양수=안정 순효과) / separation_pressure: 부정 kind(충·형·파·해)
  존재 시에만 평가 — **부정 신호 없음 ≠ 분리 위험 낮음**(합 단독은 근거 부족,
  2026-07-24 보완: §5 표의 '낮음'은 직접 근거가 아니라 미평가로 보존)
- experience_valence: 부분 evidence만 기록, 축은 INSUFFICIENT_EVIDENCE
- exposure·realization·formalization: INSUFFICIENT_EVIDENCE —
  **육합이 있어도 formalization을 올리지 않고, 충이 있어도 경험 전체를 negative로
  확정하지 않는다.**

축 기여는 배우자궁(일지) 활성만이다(§4 산출 책임). 비일지 활성은 evidence로 보존만
(on_spouse_palace=False — 만남 경로 추론 §9는 별도 단계). shadow 전용 — 점수·후보·
가드 어디에도 관여하지 않는다(부록 D-3).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import (
    AxisStatus,
    RelationshipActivationEvidence,
    RelationshipAxisValue,
    RelationshipEffectVector,
    TriggerPrecision,
    unevaluated,
)

from .relation_palace_engine import RelationActivation

_NEGATIVE_KINDS = frozenset({
    RelationKind.CHUNG, RelationKind.HYEONG, RelationKind.PA, RelationKind.HAE,
})

# §5 표의 종료 압력 서열(충 높음 > 형·해·파 중간 > 합·복음 낮음) — 상대 가중.
_SEPARATION_WEIGHT: dict[RelationKind, float] = {
    RelationKind.CHUNG: 1.0, RelationKind.HYEONG: 0.6,
    RelationKind.HAE: 0.55, RelationKind.PA: 0.55,
}
# §5 표의 안정성 기여(육합 소폭 상승 / 충·형·해·파 하락 / 복음·삼합 문맥 의존=중립).
_STABILITY_CONTRIB: dict[RelationKind, float] = {
    RelationKind.HAP: +0.3, RelationKind.CHUNG: -1.0, RelationKind.HYEONG: -0.8,
    RelationKind.HAE: -0.6, RelationKind.PA: -0.6, RelationKind.BOKEUM: 0.0,
}


class SpousePalaceHit(BaseModel):
    """활성 1건 + 생성부가 아는 실측 정보(운 글자·참여자·소스 위치).

    P1-5 승인 조건: RelationPalace evidence도 실제 transit component를 받아
    signal_trigger_id가 EXACT/COMPONENT여야 MT2와의 동일 root 판정이 가능하다.
    participant·source_locator는 '같은 서명이지만 합법적 별도 원인'(다른 원국
    참여자)을 서명 수준에서 분리한다(§6).
    """

    kind: RelationKind
    palace: Pillar4
    layer: str                          # sewoon | wolwoon | daewoon (LuckLayer.value)
    position: str = "branch"
    hap_subtype: str | None = None
    element: str | None = None
    transit_component: str = ""         # stem | branch (운 쪽 구성요소 종류)
    transit_participant: str = ""       # 운 글자(한자) — 있으면 EXACT trigger
    natal_participant: str = ""         # 피자극 원국 글자
    source_locator: str = ""            # 생성 규칙·원국 자리 등 결정적 소스 식별


class SpousePalaceVectorResult(BaseModel):
    """어댑터 산출 — 벡터 + cap 이전 원시 증거(중간 승인 샘플의 표시 단위)."""

    vector: RelationshipEffectVector
    evidences: list[RelationshipActivationEvidence] = Field(default_factory=list)
    independent_cause_count: int = 0    # independent_cause_id 고유값 기준(≠reason 수)
    # 이벤트 무관 기본 강도 합(일지 한정, cap·×1.2·MT4 미적용) — 실제 legacy pre-cap
    # 점수가 아니다(이벤트 결합 후에만 정의 — evidence의 event_adjusted_* 참조).
    base_activation_total: float = 0.0
    # stability 내부 분해(보완 §5) — 축 value는 net이지만 근거는 support/pressure를
    # 따로 보존한다. support(+합 결속)는 '장기 안정성 확정'이 아니라 binding support의
    # 제한 의미 — 쟁합·합거·합반(P1-4)이 상쇄·blocker로 재분류할 수 있다.
    stability_support: float = 0.0
    stability_pressure: float = 0.0
    # 3종 카운트 분리(P1-5 승인 §2) — '독립 원인 수' 단일 압축 금지.
    evidence_count: int = 0
    semantic_cause_group_count: int = 0
    root_trigger_count: int = 0                 # EXACT/COMPONENT signal 고유값만
    unresolved_trigger_evidence_count: int = 0  # PROVISIONAL — root 병합·계산 사용 금지


class _Dict:
    """relation_palace_modifier.json 산식 재현용 로더(cap 미적용) — 읽기 전용."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "relation_palace_modifier.json")
            .read_text(encoding="utf-8")
        )
        self.rel_bonus = {k: int(v["base_event_score_bonus"])
                         for k, v in raw["relation_types"].items()}
        self.palace = raw["palace_map"]
        self.layer_w = {k: float(v["score_multiplier"])
                        for k, v in raw["relation_layer_weights"].items()}
        self.palace_mult = raw["palace_relation_score_multipliers"]

    def raw_strength_hit(self, h: SpousePalaceHit) -> float:
        """legacy와 동일 산식(likely·MT4 제외 기본형) — cap 없음."""
        pinfo = self.palace[h.palace.value]
        layer_mult = self.layer_w.get(f"{h.layer}_to_natal", 1.0)
        pmult = self.palace_mult[h.palace.value][h.position]
        return (self.rel_bonus[h.kind.value] * float(pinfo["activation_weight"])
                * layer_mult * pmult)


def _band(value: float, *, strong: float, moderate: float, weak: float) -> str:
    if value >= strong:
        return "strong"
    if value >= moderate:
        return "moderate"
    if value >= weak:
        return "weak"
    return "low"


def _normalize(hit: RelationActivation | SpousePalaceHit) -> SpousePalaceHit:
    if isinstance(hit, SpousePalaceHit):
        return hit
    return SpousePalaceHit(
        kind=hit.kind, palace=hit.palace, layer=hit.layer.value,
        position=hit.position, hap_subtype=hit.hap_subtype, element=hit.element,
    )


def build_spouse_palace_vector(
    activations: list[RelationActivation] | list[SpousePalaceHit],
    dictionaries_dir: Path,
    *,
    period_key: str = "",
) -> SpousePalaceVectorResult:
    """배우자궁 발동 목록 → 7축 벡터(shadow) + cap 이전 증거.

    independent_cause_id = 확보 가능한 전 필드 서명(layer:kind:palace:position:
    hap_subtype:element). **완전 동일 서명 반복은 독립 원인이 아니라 evidence 1건 +
    duplicate_count**(보완 §2 — 실제 별개 source면 상위 생성부가 participant를 채워
    서명이 갈라진다). 서명 정렬 처리라 입력 순서 무관(permutation invariant).
    COMPOUND는 원인 목록의 결합 상태(compound_group_id — 구성 evidence 각각에
    연결)이지 새 원인이 아니다(부록 D-2).
    """
    d = _Dict(dictionaries_dir)
    hits = [_normalize(a) for a in activations]
    evidences: list[RelationshipActivationEvidence] = []
    kinds_on_day: list[RelationKind] = []
    base_day_total = 0.0
    day_kinds_set = {h.kind for h in hits if h.palace is Pillar4.DAY}
    compound_id = (
        "+".join(sorted(k.value for k in day_kinds_set)) if len(day_kinds_set) >= 2
        else None
    )

    # 입력 순서 불변(permutation invariance) — 확보 가능한 전 필드로 정렬한 뒤 처리한다.
    # participant·source_locator가 서명에 들어가므로 '같은 kind·궁이지만 다른 원국
    # 참여자'는 별도 독립 원인으로 갈라진다(§6 합법적 별도 source).
    def _signature(h: SpousePalaceHit) -> str:
        return ":".join((
            h.layer, h.kind.value, h.palace.value, h.position,
            h.hap_subtype or "", h.element or "",
            h.natal_participant, h.transit_participant, h.source_locator,
        ))

    # 완전 동일 typed hit는 별도 독립 원인이 아니다(보완 §2) — 확보 가능한 전 필드
    # 서명이 같으면 evidence 1건 + duplicate_count로 보존한다. 실제로 서로 다른
    # source(다른 원국 참여자)라면 상위 생성부가 participant를 채워 서명이 갈라진다.
    grouped: dict[str, list[SpousePalaceHit]] = {}
    for h in hits:
        grouped.setdefault(_signature(h), []).append(h)

    for base_key in sorted(grouped):
        hs = grouped[base_key]
        h = hs[0]
        dup = len(hs)
        on_day = h.palace is Pillar4.DAY
        base = d.raw_strength_hit(h)
        if on_day:
            kinds_on_day.append(h.kind)
            base_day_total += base  # 중복 생성분은 강도 합에도 1회만(과대 집계 방지)
        # trigger 2계층(보완 §4·P1-5 승인 §1) — 운 글자가 있으면 EXACT(MT2와 동일
        # 포맷 layer:period:component:글자 — 동일 root 판정 기준), 기간만 있으면
        # signal 미상(PROVISIONAL — root 병합·계산 사용 금지).
        if h.transit_participant and period_key:
            signal = (f"{h.layer}:{period_key}:"
                      f"{h.transit_component or 'branch'}:{h.transit_participant}")
            precision = TriggerPrecision.EXACT
        else:
            signal = None
            precision = TriggerPrecision.PROVISIONAL
        evidences.append(RelationshipActivationEvidence(
            evidence_id=f"spa:{base_key}",
            independent_cause_id=base_key,
            independent_cause_group="palace_activation",
            period_trigger_id=f"{h.layer}:{period_key}" if period_key else h.layer,
            signal_trigger_id=signal,
            trigger_precision=precision,
            duplicate_count=dup,
            relation_kind=h.kind.value,
            source_layer=h.layer,
            affected_palace=h.palace.value,
            on_spouse_palace=on_day,
            natal_participant=h.natal_participant,
            transit_participant=h.transit_participant,
            compound_group_id=compound_id if on_day else None,
            base_relation_strength=round(base, 3),
            # event_adjusted_legacy_strength/legacy_delta/legacy_capped는 특정 이벤트와
            # 결합된 뒤에만 정의 — 어댑터 단계에서는 None(오해 방지, 2026-07-24 보완).
            reason_codes=[f"REL_{h.kind.value}_{h.palace.value}"],
        ))

    day_evidence_ids = [e.evidence_id for e in evidences if e.on_spouse_palace]
    day_causes = {e.independent_cause_id for e in evidences if e.on_spouse_palace}

    vector = RelationshipEffectVector()
    stability_support = stability_pressure = 0.0
    if kinds_on_day:
        # activation — 기본 강도 합 기준 밴드(§5: 충 매우 높음 > 합 높음 > 파·해 중간).
        vector.activation = RelationshipAxisValue(
            status=AxisStatus.EVALUATED,
            value=round(base_day_total, 3),
            band=_band(base_day_total, strong=20.0, moderate=12.0, weak=6.0),
            evidence_ids=day_evidence_ids,
        )
        # separation_pressure — 부정 kind가 있을 때만 평가(§5 서열 가중 최대치).
        # 합·복음만 있으면 근거 부족: '부정 신호 없음'은 '분리 위험 낮음'의 직접
        # 근거가 아니다(AxisStatus 원칙 — 2026-07-24 보완).
        neg = [k for k in kinds_on_day if k in _NEGATIVE_KINDS]
        if neg:
            sep = max(_SEPARATION_WEIGHT[k] for k in neg)
            vector.separation_pressure = RelationshipAxisValue(
                status=AxisStatus.EVALUATED,
                value=round(sep, 3),
                band=_band(sep, strong=0.9, moderate=0.55, weak=0.3),
                evidence_ids=day_evidence_ids,
            )
        else:
            vector.separation_pressure = RelationshipAxisValue(
                status=AxisStatus.INSUFFICIENT_EVIDENCE,
                evidence_ids=day_evidence_ids,
            )
        # stability — support(+)와 pressure(−)를 분해 보존하고 축 value는 net(보완 §5).
        support = sum(v for k in kinds_on_day
                      if (v := _STABILITY_CONTRIB.get(k, 0.0)) > 0)
        pressure = sum(-v for k in kinds_on_day
                       if (v := _STABILITY_CONTRIB.get(k, 0.0)) < 0)
        stab = support - pressure
        stability_support, stability_pressure = support, pressure
        vector.stability = RelationshipAxisValue(
            status=AxisStatus.EVALUATED,
            value=round(stab, 3),
            band=("weak" if stab <= -0.8 else "moderate" if stab < 0.3 else "strong"),
            evidence_ids=day_evidence_ids,
        )
        # experience_valence — 부분 evidence만(충≠경험 전체 negative 확정 금지).
        vector.experience_valence = RelationshipAxisValue(
            status=AxisStatus.INSUFFICIENT_EVIDENCE,
            evidence_ids=day_evidence_ids,
        )
    # exposure·realization·formalization — 육합이 있어도 올리지 않는다(부록 D 표).
    vector.exposure = unevaluated()
    vector.realization = unevaluated()
    vector.formalization = unevaluated()

    resolved_signals = {
        e.signal_trigger_id for e in evidences
        if e.signal_trigger_id is not None
        and e.trigger_precision is not TriggerPrecision.PROVISIONAL
    }
    unresolved = sum(
        1 for e in evidences if e.trigger_precision is TriggerPrecision.PROVISIONAL
    )
    return SpousePalaceVectorResult(
        vector=vector,
        evidences=evidences,
        independent_cause_count=len(day_causes),
        base_activation_total=round(base_day_total, 3),
        stability_support=round(stability_support, 3),
        stability_pressure=round(stability_pressure, 3),
        evidence_count=len(evidences),
        semantic_cause_group_count=len({e.independent_cause_group for e in evidences}),
        root_trigger_count=len(resolved_signals),
        unresolved_trigger_evidence_count=unresolved,
    )

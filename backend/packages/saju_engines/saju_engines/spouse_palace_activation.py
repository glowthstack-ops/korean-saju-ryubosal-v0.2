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
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import (
    AxisStatus,
    RelationshipActivationEvidence,
    RelationshipAxisValue,
    RelationshipEffectVector,
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


class SpousePalaceVectorResult(BaseModel):
    """어댑터 산출 — 벡터 + cap 이전 원시 증거(중간 승인 샘플의 표시 단위)."""

    vector: RelationshipEffectVector
    evidences: list[RelationshipActivationEvidence] = Field(default_factory=list)
    independent_cause_count: int = 0    # independent_cause_id 고유값 기준(≠reason 수)
    # 이벤트 무관 기본 강도 합(일지 한정, cap·×1.2·MT4 미적용) — 실제 legacy pre-cap
    # 점수가 아니다(이벤트 결합 후에만 정의 — evidence의 event_adjusted_* 참조).
    base_activation_total: float = 0.0


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

    def raw_strength(self, act: RelationActivation) -> float:
        """legacy와 동일 산식(likely·MT4 제외 기본형) — cap 없음."""
        pinfo = self.palace[act.palace.value]
        layer_mult = self.layer_w.get(f"{act.layer.value}_to_natal", 1.0)
        pmult = self.palace_mult[act.palace.value][act.position]
        return (self.rel_bonus[act.kind.value] * float(pinfo["activation_weight"])
                * layer_mult * pmult)


def _band(value: float, *, strong: float, moderate: float, weak: float) -> str:
    if value >= strong:
        return "strong"
    if value >= moderate:
        return "moderate"
    if value >= weak:
        return "weak"
    return "low"


def build_spouse_palace_vector(
    activations: list[RelationActivation],
    dictionaries_dir: Path,
) -> SpousePalaceVectorResult:
    """배우자궁 발동 목록 → 7축 벡터(shadow) + cap 이전 증거.

    independent_cause_id = 확보 가능한 전 필드 서명(layer:kind:palace:position:
    hap_subtype:element)(#k). 처리 전 서명 정렬 + 동일 서명 반복은 개수 기반 suffix라
    **입력 순서와 무관**(permutation invariant — 2026-07-24 보완). COMPOUND는 원인
    목록의 결합 상태(compound_group_id — 구성 evidence 각각에 연결)이지 새 원인이
    아니다(부록 D-2).
    """
    d = _Dict(dictionaries_dir)
    evidences: list[RelationshipActivationEvidence] = []
    kinds_on_day: list[RelationKind] = []
    base_day_total = 0.0
    key_seq: Counter[str] = Counter()
    day_kinds_set = {a.kind for a in activations if a.palace is Pillar4.DAY}
    compound_id = (
        "+".join(sorted(k.value for k in day_kinds_set)) if len(day_kinds_set) >= 2
        else None
    )

    # 입력 순서 불변(permutation invariance) — 확보 가능한 전 필드로 정렬한 뒤 처리한다.
    # 동일 서명 hit(구분 정보 없음)의 #k suffix는 개수 기반이라 순서와 무관하게 동일하다.
    def _signature(act: RelationActivation) -> str:
        return ":".join((
            act.layer.value, act.kind.value, act.palace.value, act.position,
            act.hap_subtype or "", act.element or "",
        ))

    for act in sorted(activations, key=_signature):
        base_key = _signature(act)
        key_seq[base_key] += 1
        cause_id = base_key if key_seq[base_key] == 1 else f"{base_key}#{key_seq[base_key]}"
        on_day = act.palace is Pillar4.DAY
        base = d.raw_strength(act)
        if on_day:
            kinds_on_day.append(act.kind)
            base_day_total += base
        evidences.append(RelationshipActivationEvidence(
            evidence_id=f"spa:{cause_id}",
            independent_cause_id=cause_id,
            independent_cause_group="palace_activation",
            # 잠정 root trigger 서명 — 입력에 운 글자가 없어 층위·합화오행으로 근사
            # (P1-3에서 활성 생성부의 운 글자 주입으로 정밀화 — 부록 D §7).
            shared_trigger_id=f"{act.layer.value}:{act.element or act.kind.value}",
            relation_kind=act.kind.value,
            source_layer=act.layer.value,
            affected_palace=act.palace.value,
            on_spouse_palace=on_day,
            compound_group_id=compound_id if on_day else None,
            base_relation_strength=round(base, 3),
            # event_adjusted_legacy_strength/legacy_delta/legacy_capped는 특정 이벤트와
            # 결합된 뒤에만 정의 — 어댑터 단계에서는 None(오해 방지, 2026-07-24 보완).
            reason_codes=[f"REL_{act.kind.value}_{act.palace.value}"],
        ))

    day_evidence_ids = [e.evidence_id for e in evidences if e.on_spouse_palace]
    day_causes = {e.independent_cause_id for e in evidences if e.on_spouse_palace}

    vector = RelationshipEffectVector()
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
        # stability — kind 기여 합의 제한 평가(합 소폭↑, 충·형·해·파↓; 혼재 시 상쇄 보존).
        stab = sum(_STABILITY_CONTRIB.get(k, 0.0) for k in kinds_on_day)
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

    return SpousePalaceVectorResult(
        vector=vector,
        evidences=evidences,
        independent_cause_count=len(day_causes),
        base_activation_total=round(base_day_total, 3),
    )

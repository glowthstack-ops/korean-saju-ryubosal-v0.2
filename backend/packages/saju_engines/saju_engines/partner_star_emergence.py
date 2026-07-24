"""배우자성 투출 회귀(MT2) → 관계 evidence 어댑터 — P1-3 (RELATIONSHIP_EVENT_SYSTEM 부록 D).

MT2의 의미(일지 지장간 투출 글자의 운 회귀 = 잠재 배우자성의 재등장)를 shadow evidence로
변환한다. **기존 MT2 점수 증폭 경로와 완전 별개**(생성·증폭 없음 — 부록 D-3 불변식).

원칙(2026-07-24 승인 §8):
- `partner_star_emergence` 그룹 — RelationPalace(궁위 활성화)와 역할 분리. 같은 운
  글자에서 두 evidence가 나오면 **증거 2종·독립 root(signal) 1개**로 계산할 수 있게
  `signal_trigger_id`를 EXACT로 채운다(운 천간 글자 확보 — RelationPalace 잠정 서명과
  대조는 합성기 소관).
- **realization을 EVALUATED로 올리지 않는다** — MT2는 현실 접촉의 직접 근거가 아니라
  보조 evidence다. 축 판정 없이 evidence만 반환한다(최종 상태는 P1-5 합성기).
- 배우자궁 충으로 MT2 delta=0인 사례는 **0점이 아니라 blocker evidence**로 보존한다
  (SPOUSE_PALACE_CLASHED — 최종 BLOCKED 판정은 합성기).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from saju_shared_types.relationship_effect import (
    RelationshipActivationEvidence,
    TriggerPrecision,
)

from .marriage_emergence_modifier import (
    _DELTA,
    MarriageEmergenceNatal,
    _classify_return,
)


class PartnerStarEmergenceResult(BaseModel):
    """MT2 evidence 산출 — 축 판정 없음(합성기 소비 전용)."""

    evidences: list[RelationshipActivationEvidence] = Field(default_factory=list)
    blocker_evidences: list[RelationshipActivationEvidence] = Field(default_factory=list)
    hit: bool = False
    tier: str | None = None             # same_stem | same_element
    is_partner_star: bool | None = None


def build_partner_star_emergence_evidence(
    natal: MarriageEmergenceNatal,
    luck_stem: str,
    *,
    layer: str,
    period_key: str,
    spouse_palace_clashed: bool = False,
) -> PartnerStarEmergenceResult:
    """운 천간의 투출 회귀를 evidence로 변환한다(순수 함수·shadow 전용).

    Args:
        natal: `analyze_marriage_emergence_natal` 결과(정적).
        luck_stem: 운 천간 글자(한자) — signal_trigger_id를 EXACT로 만든다.
        layer: sewoon | wolwoon | daewoon.
        period_key: '2028' / '2028-04' 등 기간 라벨(period_trigger_id).
        spouse_palace_clashed: 배우자궁 충 동반 여부(legacy MT2 delta=0 경로).

    Returns:
        회귀 없으면 빈 결과. 충 동반이면 evidence 대신 blocker_evidences에 보존.
    """
    hit = _classify_return(natal, luck_stem)
    if hit is None:
        return PartnerStarEmergenceResult()
    emerged, tier = hit
    base = float(_DELTA[(emerged.is_partner_star, tier)])
    cause_id = f"{layer}:MT2:{tier}:{emerged.stem}"
    ev = RelationshipActivationEvidence(
        evidence_id=f"pse:{cause_id}",
        independent_cause_id=cause_id,
        independent_cause_group="partner_star_emergence",
        period_trigger_id=f"{layer}:{period_key}",
        # 운 글자 확보 — RelationPalace 동일 글자 파생과 root 1개 판정의 기준(EXACT).
        signal_trigger_id=f"{layer}:{period_key}:stem:{luck_stem}",
        trigger_precision=TriggerPrecision.EXACT,
        relation_kind="EMERGENCE",          # 합충형파해가 아닌 투출 회귀
        source_layer=layer,
        affected_palace="day_pillar",       # 일지 지장간 기원
        on_spouse_palace=True,
        natal_participant=emerged.stem,
        transit_participant=luck_stem,
        base_relation_strength=base,        # legacy MT2 delta 표와 동일 스케일(이벤트 무관)
        reason_codes=[
            f"MT2_EMERGENCE_{'SAME_STEM' if tier == 'same_stem' else 'SAME_ELEMENT'}",
        ],
    )
    if spouse_palace_clashed:
        # legacy: delta=0 + CLASHED 태그. 벡터 계층: 0점이 아니라 blocker evidence로
        # 보존(현실화 저해 근거 — 최종 BLOCKED 판정·다른 evidence와의 결합은 합성기).
        blocked = ev.model_copy(update={
            "evidence_id": f"pse-blocker:{cause_id}",
            "base_relation_strength": 0.0,
            "reason_codes": [*ev.reason_codes, "SPOUSE_PALACE_CLASHED"],
        })
        return PartnerStarEmergenceResult(
            blocker_evidences=[blocked], hit=True, tier=tier,
            is_partner_star=emerged.is_partner_star,
        )
    return PartnerStarEmergenceResult(
        evidences=[ev], hit=True, tier=tier, is_partner_star=emerged.is_partner_star,
    )

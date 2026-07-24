"""P1-1 타입·P1-2 배우자궁 벡터 어댑터 검증 (RELATIONSHIP_EVENT_SYSTEM §5·부록 D).

핵심: cap 이전 원시 구조 보존(충 단독≠충2+형), reason 수≠독립 원인 수,
근거 없는 축은 0이 아니라 INSUFFICIENT_EVIDENCE, 합 단독으로 formalization 미상승.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relation_palace_engine import RelationActivation
from saju_engines.spouse_palace_activation import build_spouse_palace_vector
from saju_shared_types.event_engine import LuckLayer, Pillar4, RelationKind
from saju_shared_types.relationship_effect import AxisStatus

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _act(kind: RelationKind, palace: Pillar4 = Pillar4.DAY,
         layer: LuckLayer = LuckLayer.SEWOON) -> RelationActivation:
    return RelationActivation(kind, palace, layer)


def _build(*acts: RelationActivation):
    return build_spouse_palace_vector(list(acts), _DICTS)


def test_hap_alone_activation_up_formalization_unevaluated() -> None:
    """샘플① 일지 육합 단독 — activation 평가·상승, formalization은 미평가(미상승)."""
    r = _build(_act(RelationKind.HAP))
    assert r.vector.activation.status is AxisStatus.EVALUATED
    assert r.vector.activation.value and r.vector.activation.value > 0
    assert r.vector.formalization.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.vector.formalization.value is None  # 0으로 채우지 않는다
    assert r.vector.exposure.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.vector.realization.status is AxisStatus.INSUFFICIENT_EVIDENCE
    # 합 단독 — 분리 압력은 '낮음' 판정이 아니라 근거 부족(부정 신호 없음≠위험 낮음).
    assert r.vector.separation_pressure.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.vector.separation_pressure.value is None
    # 안정성은 signed 축 — 합은 소폭 양(+)의 안정 순효과.
    assert r.vector.stability.value and r.vector.stability.value > 0


def test_chung_alone_activation_and_separation_up_stability_down() -> None:
    """샘플② 일지 충 단독 — activation·separation 상승, stability 하락."""
    r = _build(_act(RelationKind.CHUNG))
    assert r.vector.activation.status is AxisStatus.EVALUATED
    assert r.vector.separation_pressure.band == "strong"
    assert r.vector.stability.value is not None and r.vector.stability.value < 0
    # 충이라도 경험 전체를 negative로 확정하지 않는다.
    assert r.vector.experience_valence.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.vector.experience_valence.direction is None


def test_hap_plus_chung_preserves_opposing_evidence() -> None:
    """샘플③ 합+충 — 상반 evidence 동시 보존(별개 독립 원인 + compound 그룹)."""
    r = _build(_act(RelationKind.HAP), _act(RelationKind.CHUNG))
    assert r.independent_cause_count == 2
    kinds = {e.relation_kind for e in r.evidences}
    assert kinds == {"HAP", "CHUNG"}
    assert all(e.compound_group_id == "CHUNG+HAP" for e in r.evidences)
    # 안정성: 합(+0.3)과 충(-1.0)의 상쇄가 보존된 값.
    assert r.vector.stability.value == -0.7


def test_double_chung_plus_hyeong_uncapped_structure() -> None:
    """샘플④ 충2+형 — cap 이전 독립 원인 3개 보존(legacy에선 충 단독과 동일 +22)."""
    single = _build(_act(RelationKind.CHUNG))
    triple = _build(
        _act(RelationKind.CHUNG), _act(RelationKind.CHUNG, layer=LuckLayer.WOLWOON),
        _act(RelationKind.HYEONG),
    )
    assert triple.independent_cause_count == 3
    assert triple.base_activation_total > single.base_activation_total  # cap 이전 변별
    # 어댑터 단계에서 legacy cap 여부는 미정의(이벤트 결합 후에만) — None 보존.
    assert all(e.legacy_capped is None and e.event_adjusted_legacy_strength is None
               and e.legacy_delta is None for e in triple.evidences)


def test_same_key_repeat_gets_distinct_cause_ids() -> None:
    """동일 (layer,kind,palace) 반복 — 결정적 suffix로 독립 원인 구분."""
    r = _build(_act(RelationKind.CHUNG), _act(RelationKind.CHUNG))
    ids = [e.independent_cause_id for e in r.evidences]
    assert len(set(ids)) == 2 and ids[1].endswith("#2")


def test_pa_hae_smaller_pressure_than_chung() -> None:
    """샘플⑤ 파·해 — 충과 다른(작은) 압력 크기."""
    chung = _build(_act(RelationKind.CHUNG)).vector.separation_pressure.value
    pa = _build(_act(RelationKind.PA)).vector.separation_pressure.value
    hae = _build(_act(RelationKind.HAE)).vector.separation_pressure.value
    assert chung is not None and pa is not None and hae is not None
    assert chung > pa and chung > hae


def test_no_activation_all_axes_unevaluated() -> None:
    """샘플⑥ 무발동 — 전 축 근거 없음(0이 아니라 status로 표현)."""
    r = _build()
    for axis in ("activation", "exposure", "realization", "experience_valence",
                 "stability", "formalization", "separation_pressure"):
        v = getattr(r.vector, axis)
        assert v.status is AxisStatus.INSUFFICIENT_EVIDENCE, axis
        assert v.value is None
    assert r.independent_cause_count == 0 and r.evidences == []


def test_non_day_palace_recorded_but_no_axis_contribution() -> None:
    """비일지 활성 — evidence 보존만, 축 기여 없음(§4 산출 책임: 배우자궁 한정)."""
    r = _build(_act(RelationKind.CHUNG, palace=Pillar4.MONTH))
    assert len(r.evidences) == 1 and r.evidences[0].on_spouse_palace is False
    assert r.vector.activation.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert r.independent_cause_count == 0


def test_reason_count_not_cause_count() -> None:
    """reason 수 ≠ 독립 원인 수 — COMPOUND는 결합 상태(compound_group_id)일 뿐."""
    r = _build(_act(RelationKind.HAP), _act(RelationKind.CHUNG))
    total_reasons = sum(len(e.reason_codes) for e in r.evidences)
    assert total_reasons == 2 and r.independent_cause_count == 2
    # legacy에서는 REL_COMPOUND reason이 추가로 붙지만 원인 수는 여전히 2다 —
    # 어댑터는 COMPOUND를 reason이 아니라 그룹 서명으로 보존한다.
    assert all("COMPOUND" not in c for e in r.evidences for c in e.reason_codes)


def test_adapter_is_pure_no_input_mutation() -> None:
    """shadow 불변식 — 입력 activations 무변경(순수 함수)."""
    acts = [_act(RelationKind.CHUNG), _act(RelationKind.HAP)]
    snapshot = [(a.kind, a.palace, a.layer, a.position) for a in acts]
    _build(*acts)
    assert [(a.kind, a.palace, a.layer, a.position) for a in acts] == snapshot


def test_permutation_invariance() -> None:
    """입력 순서 역전 — evidence ID 집합·원인 수·축 값 전부 동일(보완 §3)."""
    acts = [
        _act(RelationKind.CHUNG), _act(RelationKind.HAP),
        _act(RelationKind.HYEONG, layer=LuckLayer.WOLWOON),
        _act(RelationKind.CHUNG),  # 동일 서명 반복
    ]
    fwd = _build(*acts)
    rev = _build(*reversed(acts))
    assert {e.independent_cause_id for e in fwd.evidences} == \
        {e.independent_cause_id for e in rev.evidences}
    assert fwd.independent_cause_count == rev.independent_cause_count
    assert fwd.vector.model_dump() == rev.vector.model_dump()


def test_compound_group_linked_on_constituent_evidences() -> None:
    """compound_group_id가 구성 evidence 각각에 연결(보완 §6) — 우연 공존과 구분 근거."""
    r = _build(_act(RelationKind.HAP), _act(RelationKind.CHUNG))
    day = [e for e in r.evidences if e.on_spouse_palace]
    assert all(e.compound_group_id == "CHUNG+HAP" for e in day)
    single = _build(_act(RelationKind.CHUNG))
    assert all(e.compound_group_id is None for e in single.evidences)


def test_shared_trigger_id_present_for_synthesizer() -> None:
    """shared_trigger_id 잠정 서명 존재(§7 — P1-3 MT2와 root trigger 대조용)."""
    r = _build(_act(RelationKind.HAP))
    assert all(e.shared_trigger_id for e in r.evidences)


def test_base_strength_not_confused_with_legacy_precap() -> None:
    """base_relation_strength는 이벤트 무관 기본 강도 — legacy pre-cap 필드는 None(보완 §2)."""
    r = _build(_act(RelationKind.CHUNG))
    e = r.evidences[0]
    assert e.base_relation_strength > 0
    assert e.event_adjusted_legacy_strength is None
    assert e.legacy_delta is None and e.legacy_capped is None

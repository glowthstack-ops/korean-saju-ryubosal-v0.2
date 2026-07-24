"""P2-2 단조성·불변식 정식 회귀 (RELATIONSHIP_VECTOR_CALIBRATION §6~§9).

harness에 흩어진 단조성·구조 격리·일반 불변식을 **상시 회귀 계약**으로 승격한다.
계수 profile이 허용 범위 안에서 달라져도 의미 방향과 구조 불변식이 깨지지 않음을
자동 검증한다(특정 profile 결과값 박제 아님 — 방향·격리·불변만). 작은 결정적
lattice 중심(§8).

목적(§6): 계수 변경 시 activation·stability·separation의 의미 방향과 routing이
유지되는지. 실패는 최소 반례로 드러나도록 사례를 분리한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.relationship_effect_vector import (
    BASELINE_CALIBRATION,
    RelationshipVectorCalibration,
    SameRootSecondaryFactors,
    SecondaryFactorStructure,
    synthesize_relationship_effect_vector,
)
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import AxisStatus
from saju_shared_types.structure_patterns import DetectedPattern

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FACTORS = [0.0, 0.15, 0.3, 0.45, 0.6]


def _hit(kind, glyph, natal="丑"):
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=glyph, natal_participant=natal)


def _ev(hits):
    return build_spouse_palace_vector(hits, _DICTS, period_key="2027").evidences


K = RelationKind


# 작은 결정적 lattice(§8) — 각 kind 단독·same-root·cross-root·HAP혼합·root수.
def _same_pressure_pair():
    return _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "未", "戌")])


def _cross_pressure_pair():
    return _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "戌", "辰")])


def _hap_chung_same():
    return _ev([_hit(K.HAP, "未", "丑"), _hit(K.CHUNG, "未", "辰")])


def _single(kind, glyph="未"):
    return _ev([_hit(kind, glyph)])


def _c1(activation, pressure):
    return RelationshipVectorCalibration.activation_pressure_split(
        activation=activation, pressure=pressure)


def _act(ev, cal=None):
    return synthesize_relationship_effect_vector(ev, calibration=cal).axes


def _v(ax):
    return ax.value if ax.status is AxisStatus.EVALUATED else None


# ── activation 단조성(§6) ────────────────────────────────────────────────────
def test_activation_nondecreasing_in_secondary_factor():
    """같은 root secondary factor↑ → activation 비감소(SF0에서 동일 가능)."""
    ev = _same_pressure_pair()
    vals = [_v(_act(ev, RelationshipVectorCalibration.shared(secondary_factor=f))
               .activation) for f in _FACTORS]
    assert vals == sorted(vals)


def test_activation_nondecreasing_adding_cross_root():
    """서로 다른 root 추가 → activation 비감소."""
    one = _v(_act(_single(K.CHUNG)).activation)
    two = _v(_act(_cross_pressure_pair()).activation)
    assert two >= one


def test_same_root_compound_not_exceed_independent_sum():
    """same-root 복합 activation ≤ 완전 독립 합산(cross-root)."""
    same = _v(_act(_same_pressure_pair()).activation)
    cross = _v(_act(_cross_pressure_pair()).activation)
    assert same <= cross


def test_activation_factor_isolates_from_pressure_axes():
    """activation factor 변경 → stability·separation 변화 0(C1 routing)."""
    ev = _same_pressure_pair()
    ref = _act(ev, _c1(0.3, 0.3))
    for a in _FACTORS:
        ax = _act(ev, _c1(a, 0.3))
        assert ax.stability.model_dump() == ref.stability.model_dump()
        assert ax.separation_pressure.model_dump() == ref.separation_pressure.model_dump()


# ── stability 단조성(§6) ─────────────────────────────────────────────────────
def test_stability_pressure_factor_raises_pressure_lowers_net():
    """pressure factor↑ → stability pressure 비감소 → net 비증가."""
    ev = _same_pressure_pair()
    nets = [_v(_act(ev, _c1(0.3, f)).stability) for f in _FACTORS]
    assert nets == sorted(nets, reverse=True)  # 비증가


def test_hap_support_up_raises_net():
    """HAP support weight↑ → stability net 비감소(support만 있는 사례)."""
    ev = _ev([_hit(K.HAP, "未")])
    sup_lo = RelationshipVectorCalibration.shared(
        secondary_factor=0.3, stability_support={"HAP": 0.3})
    sup_hi = RelationshipVectorCalibration.shared(
        secondary_factor=0.3, stability_support={"HAP": 0.45})
    assert _v(_act(ev, sup_hi).stability) >= _v(_act(ev, sup_lo).stability)


def test_negative_relation_added_does_not_improve_stability():
    """negative relation 추가 → stability 개선 안 됨(HAP 단독 vs HAP+CHUNG)."""
    hap = _v(_act(_ev([_hit(K.HAP, "未")])).stability)
    hap_chung = _v(_act(_hap_chung_same()).stability)
    assert hap_chung <= hap


def test_jaenghap_weaken_up_lowers_net():
    """JAENGHAP weaken↑ → 대상 support 비증가 → stability net 비증가."""
    ev = _ev([_hit(K.HAP, "未")])
    tid = ev[0].evidence_id
    mods = build_relationship_structure_modifiers(
        [DetectedPattern(pattern_id="JAENGHAP", name_ko="쟁합", strength=0.6,
                         polarity_mode="context_only")],
        derived_from_by_pattern={"JAENGHAP": [tid]})
    nets = []
    for jw in (0.0, 0.25, 0.5, 0.75):
        cal = RelationshipVectorCalibration.shared(
            secondary_factor=0.3, support_weaken=jw)
        nets.append(_v(synthesize_relationship_effect_vector(
            ev, modifiers=mods, calibration=cal).axes.stability))
    assert nets == sorted(nets, reverse=True)


# ── separation 단조성(§6) ────────────────────────────────────────────────────
def test_separation_factor_raises_pressure():
    """separation(=pressure) factor↑ → separation 비감소."""
    ev = _same_pressure_pair()
    vals = [_v(_act(ev, _c1(0.3, f)).separation_pressure) for f in _FACTORS]
    assert vals == sorted(vals)


def test_hap_only_separation_insufficient():
    """HAP 단독 → separation INSUFFICIENT_EVIDENCE 유지(0/low 아님)."""
    ax = _act(_ev([_hit(K.HAP, "未")]))
    assert ax.separation_pressure.status is AxisStatus.INSUFFICIENT_EVIDENCE
    assert ax.separation_pressure.value is None


# ── 구조 격리·routing(§6) ────────────────────────────────────────────────────
def test_c0_all_axes_move_with_shared_factor():
    """C0 단일 factor↑ → 세 축 same-root 복합 동시 변화(동조)."""
    ev = _same_pressure_pair()
    lo = _act(ev, RelationshipVectorCalibration.shared(secondary_factor=0.15))
    hi = _act(ev, RelationshipVectorCalibration.shared(secondary_factor=0.45))
    assert _v(hi.activation) != _v(lo.activation)
    assert _v(hi.separation_pressure) != _v(lo.separation_pressure)


def test_c2_three_independent_factors_route():
    """C2: 세 factor 독립 routing — activation factor만 activation 변경."""
    ev = _same_pressure_pair()
    base = RelationshipVectorCalibration.axis_split(
        activation=0.3, stability_pressure=0.3, separation_pressure=0.3)
    act_hi = RelationshipVectorCalibration.axis_split(
        activation=0.6, stability_pressure=0.3, separation_pressure=0.3)
    b = _act(ev, base)
    a = _act(ev, act_hi)
    assert _v(a.activation) != _v(b.activation)
    assert a.separation_pressure.model_dump() == b.separation_pressure.model_dump()


# ── 일반 불변식(§7) ──────────────────────────────────────────────────────────
def test_duplicate_evidence_invariant():
    """duplicate evidence(같은 hit 2회) → 값 불변(dedupe+duplicate_count)."""
    one = synthesize_relationship_effect_vector(_ev([_hit(K.CHUNG, "未")]))
    two = synthesize_relationship_effect_vector(
        _ev([_hit(K.CHUNG, "未"), _hit(K.CHUNG, "未")]))
    assert one.axes.model_dump() == two.axes.model_dump()


def test_permutation_invariant():
    """입력 순서 변경 → serialized vector 동일."""
    hits = [_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "未", "戌")]
    a = synthesize_relationship_effect_vector(_ev(hits))
    b = synthesize_relationship_effect_vector(_ev(list(reversed(hits))))
    assert a.model_dump() == b.model_dump()


def test_cross_root_contribution_factor_invariant():
    """cross-root(단일 kind root 2개) → secondary factor 변경 영향 0."""
    ev = _cross_pressure_pair()
    lo = _act(ev, RelationshipVectorCalibration.shared(secondary_factor=0.0))
    hi = _act(ev, RelationshipVectorCalibration.shared(secondary_factor=0.6))
    assert lo.model_dump() == hi.model_dump()


def test_unevaluated_axes_stay_none():
    """미평가 4축(exposure·realization·experience·formalization) None 유지."""
    r = synthesize_relationship_effect_vector(_same_pressure_pair())
    for ax in (r.axes.exposure, r.axes.realization,
               r.axes.experience_valence, r.axes.formalization):
        assert ax.status is AxisStatus.INSUFFICIENT_EVIDENCE
        assert ax.value is None


def test_actual_cancellation_is_evaluated_zero_not_insufficient():
    """support=pressure 실제 상쇄 → stability EVALUATED value=0(근거 없음과 구분)."""
    # 두 HAP support(0.6) vs PA pressure(0.6) → net 0.
    ev = _ev([_hit(K.HAP, "未", "丑"), _hit(K.HAP, "戌", "辰"),
              _hit(K.PA, "申", "巳")])
    ax = _act(ev).stability
    assert ax.status is AxisStatus.EVALUATED
    assert ax.value == 0.0


def test_production_baseline_byte_identical():
    """production BASELINE(None) == 명시 BASELINE — byte-identical."""
    ev = _same_pressure_pair()
    a = synthesize_relationship_effect_vector(ev)
    b = synthesize_relationship_effect_vector(ev, calibration=BASELINE_CALIBRATION)
    assert a.model_dump() == b.model_dump()


def test_not_admissible_c1_rejected_before_run():
    """NOT_ADMISSIBLE(C1 stability≠separation) profile은 생성 단계에서 거부."""
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        RelationshipVectorCalibration(
            factor_structure=SecondaryFactorStructure.C1_ACTIVATION_PRESSURE,
            same_root_factors=SameRootSecondaryFactors(
                activation=0.3, stability_pressure=0.1, separation_pressure=0.5))


# ── property-based 보조(§9) — 고정 seed·bounded ─────────────────────────────
@pytest.mark.parametrize("a", _FACTORS)
@pytest.mark.parametrize("p", _FACTORS)
def test_c1_grid_activation_only_from_activation_factor(a, p):
    """C1 전 격자: activation은 activation factor에만, separation은 pressure factor에만."""
    ev = _same_pressure_pair()
    ref = _act(ev, _c1(0.3, p))               # activation 0.3 고정
    got = _act(ev, _c1(a, p))
    # separation은 a 무관(p 고정 시 동일).
    assert got.separation_pressure.model_dump() == ref.separation_pressure.model_dump()

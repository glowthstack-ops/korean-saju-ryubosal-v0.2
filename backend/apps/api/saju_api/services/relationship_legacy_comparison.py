"""관계 벡터 ↔ legacy 후보 비교 감사 — P1-7a (RELATIONSHIP_EVENT_SYSTEM 부록 D).

**감사 전용**: 신규 P1 벡터가 legacy보다 "맞다"를 증명하지 않는다. legacy가 보던
신호·cap으로 잃은 구조·event key마다 다른 반영·후보 부재·P1 근거 부족을 **분류**해
관찰 지도를 만든다. 읽기 전용 — score/rank/candidate/payload를 건드리지 않는다.

설계 원칙(2026-07-24 P1-7 승인):
- 비교 단위 3층: 기간 / 후보 family(marriage_signal·new_relationship·
  relationship_change 분리 — 동일 구조를 다르게 소비) / 축(activation·stability·
  separation만 평가 대상, 미평가 축은 0 비교 금지·INSUFFICIENT 분포만).
- legacy relation delta와 P1 activation은 **동일 척도가 아니다** — 유무·방향·cap·
  root·kind·family 우선, 수치는 bucket 분포 보조.
- 방향 불일치는 **보수적**으로 REVIEW_REQUIRED_DIRECTION_MISMATCH(§6 — P1은
  formalization을 아직 평가하지 않아 leakage 확정은 P3 증거 계약 이후).
- 후보 부재는 오류가 아니다(§7) — VECTOR_PRESENT/STRONG/MULTI_ROOT 세분해 P3
  검토 대상으로 보낸다.
- comparison DTO는 P1-6 telemetry와 **별도 버전·별도 allowlist**(§11) — 기존
  aggregate 의미가 흔들리지 않게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from saju_engines.relationship_effect_vector import (
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipEffectVectorResult,
)
from saju_shared_types.relationship_effect import AxisStatus

from .relationship_vector_telemetry import (
    AuditProjectionStatus,
    KindCombo,
    _root_bucket,
    classify_kind_combo,
)

# comparison DTO 버전(§11) — P1-6 telemetry schema/calibration과 독립.
COMPARISON_SCHEMA_VERSION = "cmp.v1"

# 관계 후보 canonical family(P0-A 실측 3종) — 반드시 분리 비교(합산 금지).
REL_COMPARISON_FAMILIES = ("marriage_signal", "new_relationship", "relationship_change")
# formalization 의미를 갖는 family — 방향 불일치 판정의 대상(충·형이 결혼 신호를
# 긍정 증폭하는지). new_relationship·relationship_change는 결속 확정 의미가 아니다.
_FORMALIZATION_FAMILY = "marriage_signal"

# delta ~0 판정 임계(legacy relation 기여가 사실상 없음).
_DELTA_ZERO_EPS = 0.5
# legacy relation delta cap(relation_palace_engine._MAX_RELATION_DELTA 미러 — 감사 표시용).
_LEGACY_RELATION_CAP = 22.0


class LegacyVectorComparisonClass(StrEnum):
    """벡터 ↔ legacy 비교 분류(§2, §6 보수화 반영).

    §2의 LEGACY_DIRECTION_LEAKAGE는 §6 지침대로 REVIEW_REQUIRED_DIRECTION_MISMATCH로
    보수화한다 — P1이 formalization을 평가하지 않아 leakage 확정 불가(P3 이후).
    """

    ALIGNED = "aligned"
    LEGACY_CAP_SATURATED = "legacy_cap_saturated"
    LEGACY_EVENT_KEY_BLIND_SPOT = "legacy_event_key_blind_spot"
    LEGACY_CANDIDATE_ABSENT = "legacy_candidate_absent"
    REVIEW_REQUIRED_DIRECTION_MISMATCH = "review_required_direction_mismatch"
    VECTOR_INSUFFICIENT = "vector_insufficient"
    VECTOR_ONLY_STRUCTURE = "vector_only_structure"
    LEGACY_ONLY_SIGNAL = "legacy_only_signal"
    MIXED = "mixed"


class CandidateAbsentSubclass(StrEnum):
    """LEGACY_CANDIDATE_ABSENT 세분(§7) — 부재 자체는 오류 아님, P3 검토 신호."""

    VECTOR_PRESENT = "vector_present"          # 벡터 activation 평가됨, 후보 없음
    VECTOR_STRONG = "vector_strong"            # activation strong band, 후보 없음
    MULTI_ROOT = "multi_root"                  # 독립 root 2+, 후보 없음


@dataclass(frozen=True)
class FamilyLegacyObservation:
    """한 기간·한 family의 legacy 관측(감사 입력 — 벡터와 별개).

    relation_delta/precap/capped는 deterministic harness가 채운다(cap 적용 delta +
    cap 이전 precap). production aggregate 경로는 값이 None일 수 있고, 그 경우
    수치 기반 분류(cap·blind spot)는 보류된다(추정 금지).
    """

    event_family: str
    candidate_present: bool
    relation_delta: float | None = None       # cap 적용 기여(contributions['relation'])
    relation_precap: float | None = None       # cap 이전 relation 합(포화 판정용)
    relation_capped: bool | None = None


@dataclass(frozen=True)
class PeriodComparisonInput:
    """한 기간의 벡터 + 그 기간 legacy family 관측 묶음(감사 입력)."""

    vector: RelationshipEffectVectorResult
    period_layer: str                          # daewoon | sewoon | wolwoon | ilwoon
    subject_scope: str                         # self | companion:<opaque>
    vector_run_id: str
    audit_status: AuditProjectionStatus
    families: list[FamilyLegacyObservation] = field(default_factory=list)


class LegacyVectorComparisonRecord(BaseModel):
    """사례 단위 비교 최소 projection(§5) — PII·간지·ID 미노출, allowlist 전용.

    금지(§5): period identity 원문·간지·evidence ID·signal trigger·target ID·후보
    reason·사용자 발화. 상세 재현은 deterministic fixture/로컬 harness로만(telemetry
    원문 복원 금지).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = COMPARISON_SCHEMA_VERSION
    calibration_version: str

    vector_run_id: str
    subject_scope_bucket: str                  # self | companion
    period_layer: str

    comparison_class: LegacyVectorComparisonClass
    candidate_absent_subclass: CandidateAbsentSubclass | None = None

    activation_status: AxisStatus
    activation_bucket: str | None
    stability_bucket: str | None
    separation_status: AxisStatus
    separation_bucket: str | None

    root_count_bucket: str                     # 0 | 1 | 2 | 3+
    kind_combo: KindCombo

    legacy_candidate_present: bool
    legacy_event_family: str | None            # 비교 대상 family(구조 전용이면 None)
    legacy_relation_delta_bucket: str | None
    legacy_capped: bool | None

    audit_status: AuditProjectionStatus


def _delta_bucket(delta: float | None) -> str | None:
    """legacy relation delta bucket(§3 보조 수치) — 미상은 None."""
    if delta is None:
        return None
    if delta <= _DELTA_ZERO_EPS:
        return "zero"
    if delta >= _LEGACY_RELATION_CAP:
        return "capped_22"
    if delta < 8.0:
        return "low"
    if delta < 16.0:
        return "mid"
    return "high"


def _axis_band_bucket(status: AxisStatus, band: str | None) -> str | None:
    return band if status is AxisStatus.EVALUATED else None


def _stability_sign_bucket(vector: RelationshipEffectVectorResult) -> str | None:
    """stability net 부호 bucket(신규 축은 signed) — 미평가는 None."""
    ax = vector.axes.stability
    if ax.status is not AxisStatus.EVALUATED or ax.value is None:
        return None
    if ax.value < 0:
        return "negative"
    if ax.value < 0.3:
        return "mixed_or_neutral"
    return "positive"


def _has_negative_relation(vector: RelationshipEffectVectorResult) -> bool:
    """부정 relation 근거(방향 불일치 판정 재료) — separation 평가 또는 stability<0."""
    sep = vector.axes.separation_pressure
    stab = vector.axes.stability
    if sep.status is AxisStatus.EVALUATED:
        return True
    return (stab.status is AxisStatus.EVALUATED and stab.value is not None
            and stab.value < 0)


def _absent_subclass(
    vector: RelationshipEffectVectorResult,
) -> CandidateAbsentSubclass:
    """후보 부재 세분(§7) — root 우선 > strong band > present."""
    if vector.independent_root_trigger_count >= 2:
        return CandidateAbsentSubclass.MULTI_ROOT
    if vector.axes.activation.band == "strong":
        return CandidateAbsentSubclass.VECTOR_STRONG
    return CandidateAbsentSubclass.VECTOR_PRESENT


def _classify_family(
    vector: RelationshipEffectVectorResult,
    obs: FamilyLegacyObservation,
    *,
    any_other_family_positive: bool,
) -> tuple[LegacyVectorComparisonClass, CandidateAbsentSubclass | None] | None:
    """한 family의 비교 분류(§2·§6·§7 결정 트리). None = 기록 불요(둘 다 무신호).

    precedence: 후보 부재(활성 벡터) > 벡터 미활성(legacy만) > 양쪽 활성
    (cap > delta~0[blind spot/mixed] > 방향 불일치 > aligned).
    """
    v_active = vector.axes.activation.status is AxisStatus.EVALUATED
    present = obs.candidate_present
    delta = obs.relation_delta

    if not present and not v_active:
        return None  # 양쪽 무신호 — 노이즈 방지(기록 안 함)

    if not present and v_active:
        return (LegacyVectorComparisonClass.LEGACY_CANDIDATE_ABSENT,
                _absent_subclass(vector))

    if present and not v_active:
        # legacy 후보는 있으나 P1 activation 미평가.
        if vector.evidence_count == 0:
            # P1 어댑터 범위에 대응 evidence 자체가 없음(도화·현실 exposure 등 P1 밖).
            return (LegacyVectorComparisonClass.LEGACY_ONLY_SIGNAL, None)
        # evidence는 있으나 축 근거 부족.
        return (LegacyVectorComparisonClass.VECTOR_INSUFFICIENT, None)

    # present and v_active — 양쪽 활성.
    if obs.relation_capped:
        return (LegacyVectorComparisonClass.LEGACY_CAP_SATURATED, None)
    if delta is not None and delta <= _DELTA_ZERO_EPS:
        # 활성 벡터인데 legacy relation delta ~0.
        if any_other_family_positive:
            return (LegacyVectorComparisonClass.LEGACY_EVENT_KEY_BLIND_SPOT, None)
        return (LegacyVectorComparisonClass.MIXED, None)
    # delta > 0 또는 미상(present 확인) — legacy가 이 family를 반영.
    if (_has_negative_relation(vector)
            and obs.event_family == _FORMALIZATION_FAMILY
            and delta is not None and delta > _DELTA_ZERO_EPS):
        # 부정 relation인데 결혼(formalization 의미) 후보를 긍정 증폭 — 보수 분류(§6).
        return (LegacyVectorComparisonClass.REVIEW_REQUIRED_DIRECTION_MISMATCH, None)
    return (LegacyVectorComparisonClass.ALIGNED, None)


def _base_record_fields(inp: PeriodComparisonInput) -> dict:
    """벡터 축·root·kind 등 기간 공통 필드(family 무관)."""
    v = inp.vector
    return {
        "calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "vector_run_id": inp.vector_run_id,
        "subject_scope_bucket": inp.subject_scope.split(":", 1)[0],
        "period_layer": inp.period_layer,
        "activation_status": v.axes.activation.status,
        "activation_bucket": _axis_band_bucket(
            v.axes.activation.status, v.axes.activation.band),
        "stability_bucket": _stability_sign_bucket(v),
        "separation_status": v.axes.separation_pressure.status,
        "separation_bucket": _axis_band_bucket(
            v.axes.separation_pressure.status, v.axes.separation_pressure.band),
        "root_count_bucket": _root_bucket(v.independent_root_trigger_count),
        "kind_combo": classify_kind_combo(v),
        "audit_status": inp.audit_status,
    }


def classify_period(
    inp: PeriodComparisonInput,
) -> list[LegacyVectorComparisonRecord]:
    """한 기간 → family별 비교 record(+ 구조 전용 기간 record). 읽기 전용.

    family별로 분류하되(§1 후보 family 분리), 어느 family에도 후보가 없고 벡터가
    구조(modifier·비활성 evidence)만 보존하면 기간 단위 VECTOR_ONLY_STRUCTURE
    record 1건을 낸다(§2). P1 미평가 축(exposure·realization 등)은 비교하지 않는다
    (§1 — status 분포는 P1-6 telemetry가 이미 관측).
    """
    v = inp.vector
    base = _base_record_fields(inp)
    positive_families = {
        o.event_family for o in inp.families
        if o.relation_delta is not None and o.relation_delta > _DELTA_ZERO_EPS
    }
    out: list[LegacyVectorComparisonRecord] = []
    any_present = False
    for obs in inp.families:
        any_present = any_present or obs.candidate_present
        other_positive = bool(positive_families - {obs.event_family})
        result = _classify_family(
            v, obs, any_other_family_positive=other_positive)
        if result is None:
            continue
        cls, subclass = result
        out.append(LegacyVectorComparisonRecord(
            **base,
            comparison_class=cls,
            candidate_absent_subclass=subclass,
            legacy_candidate_present=obs.candidate_present,
            legacy_event_family=obs.event_family,
            legacy_relation_delta_bucket=_delta_bucket(obs.relation_delta),
            legacy_capped=obs.relation_capped,
        ))

    # 구조 전용 — 어느 family에도 후보가 없고 activation 미평가이나 구조는 보존.
    v_active = v.axes.activation.status is AxisStatus.EVALUATED
    has_structure = bool(v.modifiers) or (v.evidence_count > 0 and not v_active)
    if not any_present and not v_active and has_structure and not out:
        out.append(LegacyVectorComparisonRecord(
            **base,
            comparison_class=LegacyVectorComparisonClass.VECTOR_ONLY_STRUCTURE,
            candidate_absent_subclass=None,
            legacy_candidate_present=False,
            legacy_event_family=None,
            legacy_relation_delta_bucket=None,
            legacy_capped=None,
        ))
    return out

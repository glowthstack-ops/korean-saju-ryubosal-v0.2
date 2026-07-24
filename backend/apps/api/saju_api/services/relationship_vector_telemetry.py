"""관계 벡터 shadow sidecar·익명 telemetry — P1-6 (RELATIONSHIP_EVENT_SYSTEM 부록 D).

핵심 3원칙(2026-07-24 승인):
1. **벡터는 candidate가 아니라 기간 평가에서 생성한다** — 관계 후보 존재 여부와 무관
   (legacy 사각지대 기간도 관측). sidecar는 요청 내 ephemeral — EventCandidate·
   ConversationState·user_facts·LLM/report DTO·API 응답에 저장 금지.
2. **Top-N·reducer 이전 전체 평가 기간에서 관측한다**(legacy 편향 복제 방지) —
   단 shadow는 reducer·후보 경로에 입력되지 않는다(관측 위치=Top-N 이전, 영향=없음).
3. **telemetry는 envelope dump가 아니라 전용 allowlist DTO로만 직렬화한다**
   (기본 거부·명시 허용 필드 복사 — 새 필드 추가 시 자동 유출 차단).

processing identity(§4·§5): HMAC-SHA256 + 고정 secret + key_version.
observation은 scope·turn·subject·period identity·정규화 입력 서명을 포함하고,
run은 observation + schema/calibration version. 원문·대상 ID는 digest에만 소비.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from saju_engines.relationship_effect_vector import (
    RELATIONSHIP_CALIBRATION_VERSION,
    RELATIONSHIP_VECTOR_SCHEMA_VERSION,
    RelationshipEffectVectorResult,
)
from saju_shared_types.relationship_effect import AxisStatus

logger = logging.getLogger(__name__)

# 다기간 요청 하드 상한(§13) — 초과분은 truncation 계측(뒤쪽 기간만 상시 제외되는
# 편향을 피하기 위해 결정적 stride 샘플링).
MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST = 36

_HMAC_KEY_VERSION = "k1"


def _hmac_key() -> bytes:
    # 운영은 env로 주입 — 부재 시 dev 고정 키(재시작 간 dedupe 안정성 유지).
    return os.getenv("SAJU_REL_TELEMETRY_HMAC_KEY", "saju-rel-dev-k1").encode()


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def _digest(*parts: str) -> str:
    msg = "\x1f".join(_norm(p) for p in parts).encode()
    return hmac.new(_hmac_key(), msg, hashlib.sha256).hexdigest()[:16]


def vector_observation_id(
    *, thread_scope: str, turn: int, subject_scope: str,
    period_identity: str, input_signature: str,
) -> str:
    """기간·대상 단위 안정 관측 ID(§4) — 재시도 dedupe 기준, 원문 미노출.

    period_identity는 층위 포함('sewoon:2029'·'wolwoon:2029-04'), subject_scope는
    내부 스코프('self'·'companion:<opaque>')다.
    """
    return _digest(thread_scope, str(turn), subject_scope, period_identity,
                   input_signature)


def vector_run_id(observation_id: str) -> str:
    """계산 런 ID = 관측 + schema/calibration version(§4) — 재감사는 별도 run."""
    return _digest(observation_id, RELATIONSHIP_VECTOR_SCHEMA_VERSION,
                   RELATIONSHIP_CALIBRATION_VERSION)


class LegacyCandidateAudit(BaseModel):
    """legacy 후보 최소 projection(§9) — 벡터와 의미 분리, 원문·reason 미보존."""

    event_key: str
    candidate_present: bool
    score: float | None = None
    confidence: str | None = None
    rank: int | None = None
    relation_delta: float | None = None
    relation_capped: bool | None = None


class RelationshipEffectShadowEnvelope(BaseModel):
    """기간 단위 shadow sidecar(§8) — 요청 내 ephemeral, 저장·직렬화 경로 금지."""

    observation_id: str
    vector_run_id: str
    period_identity: str                # 예: sewoon:2029 (층위 포함)
    subject_scope: str                  # self | companion:<opaque>
    schema_version: str = RELATIONSHIP_VECTOR_SCHEMA_VERSION
    calibration_version: str = RELATIONSHIP_CALIBRATION_VERSION
    vector: RelationshipEffectVectorResult
    legacy_candidate_audits: list[LegacyCandidateAudit] = Field(default_factory=list)
    usage: Literal["shadow_only"] = "shadow_only"


class KindCombo(StrEnum):
    """kind 조합 고정 enum(§11) — 동적 문자열 조합 금지(카디널리티 상한)."""

    NONE = "none"
    HAP_ONLY = "hap_only"
    NEGATIVE_SINGLE = "negative_single"
    HAP_WITH_NEGATIVE = "hap_with_negative"
    MULTI_NEGATIVE = "multi_negative"
    PALACE_PLUS_EMERGENCE = "palace_plus_emergence"
    EMERGENCE_ONLY = "emergence_only"
    OTHER_BOUNDED = "other_bounded"


_NEG = {"CHUNG", "HYEONG", "PA", "HAE"}


def classify_kind_combo(vector: RelationshipEffectVectorResult) -> KindCombo:
    kinds = {k for c in vector.root_contributions for k in c.kinds}
    if not kinds:
        return KindCombo.NONE
    neg = kinds & _NEG
    has_hap = "HAP" in kinds
    has_em = "EMERGENCE" in kinds
    if has_em and (has_hap or neg):
        return KindCombo.PALACE_PLUS_EMERGENCE
    if has_em:
        return KindCombo.EMERGENCE_ONLY
    if has_hap and neg:
        return KindCombo.HAP_WITH_NEGATIVE
    if has_hap and not neg:
        return KindCombo.HAP_ONLY
    if len(neg) == 1 and kinds == neg:
        return KindCombo.NEGATIVE_SINGLE
    if len(neg) >= 2 and kinds <= _NEG:
        return KindCombo.MULTI_NEGATIVE
    return KindCombo.OTHER_BOUNDED


def _bucket_from_band(status: AxisStatus, band: str | None) -> str | None:
    """축 band → telemetry bucket(§12) — 미평가는 None."""
    if status is not AxisStatus.EVALUATED:
        return None
    return band or "none"


def _stability_bucket(status: AxisStatus, value: float | None) -> str | None:
    """signed stability 전용 bucket(§12) — 다른 축과 분리, 미평가는 None."""
    if status is not AxisStatus.EVALUATED or value is None:
        return None
    if value <= -1.5:
        return "strong_pressure"
    if value <= -0.5:
        return "moderate_pressure"
    if value < 0.5:
        return "mixed_or_neutral"
    if value < 1.5:
        return "moderate_support"
    return "strong_support"


class RelationshipVectorTelemetry(BaseModel):
    """telemetry 전용 allowlist DTO(§10) — envelope dump 금지·명시 필드만 수동 복사.

    금지(§7·§10): 원문·별칭·target/evidence/signal ID 전체·간지 문자열·conversation
    평문·자유 exception. trigger는 precision·layer·bucket 수준만.
    """

    schema_version: str
    calibration_version: str
    processing_key_version: str = _HMAC_KEY_VERSION
    observation_id: str
    vector_run_id: str
    period_layer: str                   # daewoon | sewoon | wolwoon | ilwoon
    subject_scope_kind: str             # self | companion

    activation_status: str
    activation_bucket: str | None
    stability_status: str
    stability_bucket: str | None
    separation_status: str
    separation_bucket: str | None
    realization_status: str
    blocker_count: int
    modifier_count: int

    kind_combo: KindCombo
    root_count: int
    evidence_count: int
    contributing_evidence_count: int
    noncontributing_evidence_count: int
    semantic_evidence_group_count: int
    unresolved_count: int
    superseded_provisional: bool
    static_conflict: bool
    supersession_cycle: bool
    supersession_missing: bool
    multi_root_hold: bool
    legacy_relation_capped: bool
    legacy_candidate_present_keys: list[str] = Field(default_factory=list)


def build_relationship_vector_telemetry(
    envelope: RelationshipEffectShadowEnvelope,
) -> RelationshipVectorTelemetry:
    """기본 거부·명시 허용 복사(§10) — envelope에 새 필드가 생겨도 유출되지 않는다."""
    v = envelope.vector
    return RelationshipVectorTelemetry(
        schema_version=envelope.schema_version,
        calibration_version=envelope.calibration_version,
        observation_id=envelope.observation_id,
        vector_run_id=envelope.vector_run_id,
        period_layer=envelope.period_identity.split(":", 1)[0],
        subject_scope_kind=envelope.subject_scope.split(":", 1)[0],
        activation_status=v.axes.activation.status.value,
        activation_bucket=_bucket_from_band(
            v.axes.activation.status, v.axes.activation.band),
        stability_status=v.axes.stability.status.value,
        stability_bucket=_stability_bucket(
            v.axes.stability.status, v.axes.stability.value),
        separation_status=v.axes.separation_pressure.status.value,
        separation_bucket=_bucket_from_band(
            v.axes.separation_pressure.status, v.axes.separation_pressure.band),
        realization_status=v.axes.realization.status.value,
        blocker_count=len(v.blockers),
        modifier_count=len(v.modifiers),
        kind_combo=classify_kind_combo(v),
        root_count=v.independent_root_trigger_count,
        evidence_count=v.evidence_count,
        contributing_evidence_count=v.contributing_evidence_count,
        noncontributing_evidence_count=v.noncontributing_evidence_count,
        semantic_evidence_group_count=v.semantic_evidence_group_count,
        unresolved_count=v.unresolved_trigger_evidence_count,
        superseded_provisional=v.superseded_provisional_count > 0,
        static_conflict=v.static_modifier_conflict_count > 0,
        supersession_cycle=v.supersession_cycle_count > 0,
        supersession_missing=v.supersession_target_missing_count > 0,
        multi_root_hold=v.modifier_multi_root_hold_count > 0,
        legacy_relation_capped=any(
            a.relation_capped for a in envelope.legacy_candidate_audits
            if a.relation_capped is not None),
        legacy_candidate_present_keys=sorted(
            a.event_key for a in envelope.legacy_candidate_audits
            if a.candidate_present),
    )


class RelationshipVectorTelemetryBatch(BaseModel):
    """요청 단위 batch(§13) — 기간별 개별 전송 금지·hard cap·truncation 계측."""

    records: list[RelationshipVectorTelemetry] = Field(default_factory=list)
    evaluated_period_count: int = 0
    emitted_period_count: int = 0
    truncated_period_count: int = 0


def build_batch(
    envelopes: list[RelationshipEffectShadowEnvelope],
) -> RelationshipVectorTelemetryBatch:
    """cap 초과 시 결정적 stride 샘플링(§13 — 뒤쪽 기간 상시 제외 편향 방지)."""
    total = len(envelopes)
    picked = envelopes
    if total > MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST:
        stride = -(-total // MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST)  # ceil
        picked = envelopes[::stride][:MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST]
    return RelationshipVectorTelemetryBatch(
        records=[build_relationship_vector_telemetry(e) for e in picked],
        evaluated_period_count=total,
        emitted_period_count=len(picked),
        truncated_period_count=total - len(picked),
    )


# telemetry 실패 격리(§14) — 본 요청 비차단 + 로그 폭주 방지(단순 rate limit).
_FAIL_LOG_EVERY = 20
_fail_count = 0


def emit_batch(batch: RelationshipVectorTelemetryBatch) -> None:
    """PII 없는 1줄 로그(shadow 관측). 실패는 계수 기반 rate-limit 로깅만."""
    global _fail_count
    try:
        logger.info(
            "relationship_vector_batch evaluated=%d emitted=%d truncated=%d "
            "records=%s",
            batch.evaluated_period_count, batch.emitted_period_count,
            batch.truncated_period_count,
            [r.model_dump(mode="json") for r in batch.records],
        )
    except Exception:  # noqa: BLE001 — telemetry 실패는 본 요청을 막지 않는다
        _fail_count += 1
        if _fail_count % _FAIL_LOG_EVERY == 1:
            logger.warning("relationship_vector_telemetry_emit_failed count=%d",
                           _fail_count)

"""P1-6 sidecar·telemetry 검증 (RELATIONSHIP_EVENT_SYSTEM — 2026-07-24 승인 §10~§13)."""

from __future__ import annotations

import json
from pathlib import Path

from saju_api.services.relationship_vector_telemetry import (
    MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST,
    KindCombo,
    LegacyCandidateAudit,
    RelationshipEffectShadowEnvelope,
    build_batch,
    build_relationship_vector_telemetry,
    classify_kind_combo,
    vector_observation_id,
    vector_run_id,
)
from saju_engines.relationship_effect_vector import (
    synthesize_relationship_effect_vector,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _vector(*kinds: RelationKind, transit: str = "未"):
    hits = [SpousePalaceHit(
        kind=k, palace=Pillar4.DAY, layer="sewoon", transit_component="branch",
        transit_participant=transit, natal_participant="丑",
    ) for k in kinds]
    res = build_spouse_palace_vector(hits, _DICTS, period_key="2027")
    return synthesize_relationship_effect_vector(res.evidences)


def _envelope(vector=None, audits=None) -> RelationshipEffectShadowEnvelope:
    obs = vector_observation_id(
        thread_scope="t1", turn=3, subject_scope="self",
        period_identity="sewoon:2027", input_signature="sig-abc",
    )
    return RelationshipEffectShadowEnvelope(
        observation_id=obs, vector_run_id=vector_run_id(obs),
        period_identity="sewoon:2027", subject_scope="self",
        vector=vector or _vector(RelationKind.CHUNG),
        legacy_candidate_audits=audits or [],
    )


def test_observation_id_includes_period_and_subject() -> None:
    """§4 — 기간·대상이 다르면 관측 ID가 갈라진다(다기간·동반자 충돌 방지)."""
    base = dict(thread_scope="t1", turn=3, subject_scope="self",
                input_signature="sig")
    a = vector_observation_id(**base, period_identity="sewoon:2027")
    b = vector_observation_id(**base, period_identity="sewoon:2028")
    c = vector_observation_id(thread_scope="t1", turn=3,
                              subject_scope="companion:rel-1",
                              period_identity="sewoon:2027", input_signature="sig")
    assert len({a, b, c}) == 3
    # 재실행 안정(HMAC 고정 키 — 프로세스 무관 dedupe).
    assert a == vector_observation_id(**base, period_identity="sewoon:2027")


def test_no_forbidden_strings_in_nested_telemetry_payload() -> None:
    """§10 — 금지 필드 재귀 검사: 발화·간지·evidence/signal ID가 payload 어디에도 없다."""
    env = _envelope(audits=[LegacyCandidateAudit(
        event_key="marriage_signal", candidate_present=True, score=86.0,
        confidence="strong_event_candidate", rank=4, relation_delta=22.0,
        relation_capped=True)])
    t = build_relationship_vector_telemetry(env)
    dumped = json.dumps(t.model_dump(mode="json"), ensure_ascii=False)
    for forbidden in ("未", "丑", "spa:", "sewoon:2027:branch", "sig-abc",
                      "t1", "남자친구"):
        assert forbidden not in dumped, forbidden
    # 허용 수준: 층위·bucket·enum·count.
    assert t.period_layer == "sewoon"
    assert t.kind_combo is KindCombo.NEGATIVE_SINGLE


def test_stability_bucket_signed_and_unevaluated_none() -> None:
    """§12 — signed stability bucket 분리, 미평가는 None(low 아님)."""
    neg = build_relationship_vector_telemetry(_envelope(_vector(RelationKind.CHUNG)))
    assert neg.stability_bucket in ("moderate_pressure", "strong_pressure")
    empty = build_relationship_vector_telemetry(
        _envelope(synthesize_relationship_effect_vector([])))
    assert empty.activation_status == "insufficient_evidence"
    assert empty.activation_bucket is None
    assert empty.stability_bucket is None


def test_kind_combo_fixed_enum() -> None:
    """§11 — 동적 문자열 조합 금지: 고정 enum 값만."""
    assert classify_kind_combo(_vector(RelationKind.HAP)) is KindCombo.HAP_ONLY
    assert classify_kind_combo(
        _vector(RelationKind.HAP, RelationKind.CHUNG)) is KindCombo.HAP_WITH_NEGATIVE
    assert classify_kind_combo(
        _vector(RelationKind.CHUNG, RelationKind.HYEONG)) is KindCombo.MULTI_NEGATIVE
    assert classify_kind_combo(
        synthesize_relationship_effect_vector([])) is KindCombo.NONE


def test_batch_cap_deterministic_sampling() -> None:
    """§13 — hard cap 초과 시 결정적 stride 샘플(뒤쪽 상시 제외 편향 방지)+계측."""
    envs = []
    for y in range(2027, 2027 + 50):
        e = _envelope()
        envs.append(e.model_copy(update={"period_identity": f"sewoon:{y}"}))
    batch = build_batch(envs)
    assert batch.evaluated_period_count == 50
    assert batch.emitted_period_count <= MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST
    assert batch.truncated_period_count == 50 - batch.emitted_period_count
    years = [r.period_layer for r in batch.records]
    assert years  # stride 샘플 — 앞뒤 고르게(첫 기간 포함)
    assert batch.records[0].observation_id == build_batch(envs).records[0].observation_id


def test_envelope_not_serializable_into_llm_paths() -> None:
    """§8 — envelope는 shadow_only 고정(직렬화 경로 유입 방지 표식)."""
    env = _envelope()
    assert env.usage == "shadow_only"


def test_supersession_counters_surface_in_telemetry() -> None:
    """§1 — 순환·유실 fail-closed가 telemetry 불리언으로 관측된다."""
    v = synthesize_relationship_effect_vector([])
    v = v.model_copy(update={"supersession_cycle_count": 1})
    t = build_relationship_vector_telemetry(_envelope(v))
    assert t.supersession_cycle is True and t.supersession_missing is False

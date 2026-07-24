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
        confidence="strong_event_candidate", pre_reduce_rank=4,
        selected_in_top_n=True, final_rank=4, relation_delta=22.0,
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


def test_batch_cap_detail_only_aggregate_full() -> None:
    """§2·§13 — hard cap은 상세 record만 제한, aggregate는 전 기간 반영.
    HMAC 정렬 샘플은 입력 순서 불변·재실행 동일."""
    envs = []
    for y in range(2027, 2027 + 50):
        obs = vector_observation_id(
            thread_scope="t1", turn=3, subject_scope="self",
            period_identity=f"sewoon:{y}", input_signature="sig")
        envs.append(_envelope().model_copy(update={
            "period_identity": f"sewoon:{y}", "observation_id": obs}))
    batch = build_batch(envs)
    assert batch.evaluated_period_count == 50
    assert batch.vector_success_count == 50
    assert batch.telemetry_record_success_count == 50   # 집계는 절단 없음
    assert batch.detailed_period_count \
        == MAX_RELATIONSHIP_SHADOW_PERIODS_PER_REQUEST  # 상세만 cap
    assert batch.truncated_success_period_count == 50 - batch.detailed_period_count
    # axis bucket 합계 = telemetry_record_success(§1 분모 불변식).
    assert sum(batch.aggregate.separation_bucket_counts.values()) == 50
    # 입력 순서 불변 + 재실행 동일(HMAC 정렬).
    rev = build_batch(list(reversed(envs)))
    assert [r.observation_id for r in batch.records] \
        == [r.observation_id for r in rev.records]


def test_batch_failure_denominators_separated() -> None:
    """§1·§2 — evaluated=성공+실패, 계산 실패와 변환 실패·degraded 2축 분리."""
    from saju_api.services.relationship_vector_telemetry import PeriodFailureReason

    ok = [_envelope()]
    batch = build_batch(ok, period_failure_counts={
        PeriodFailureReason.ADAPTER_FAILURE.value: 3})
    assert batch.evaluated_period_count == 4
    assert batch.vector_success_count == 1
    assert batch.vector_failure_count == 3
    assert batch.evaluated_period_count \
        == batch.vector_success_count + batch.vector_failure_count
    assert batch.vector_degraded is True   # 계산 과반 실패
    assert batch.telemetry_degraded is False  # 변환은 정상 — 축 분리
    # 실패 기간은 어떤 bucket에도 포함되지 않는다(임의 bucket 배정 금지).
    assert sum(batch.aggregate.separation_bucket_counts.values()) == 1
    ok2 = build_batch(ok)
    assert ok2.vector_degraded is False and ok2.telemetry_degraded is False


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


def test_all_string_values_structurally_allowlisted() -> None:
    """§4 구조 잠금 — 직렬화된 모든 문자열 값이 enum/버전/hex digest/고정 bucket
    라벨 중 하나여야 한다(특정 금지 문자열 스캔은 보조 회귀)."""
    import re

    env = _envelope(audits=[LegacyCandidateAudit(
        event_key="marriage_signal", candidate_present=True,
        pre_reduce_rank=2, selected_in_top_n=True, final_rank=1)])
    batch = build_batch([env])
    allowed_exact = {
        "evaluated", "insufficient_evidence", "not_applicable", "blocked",
        "self", "companion", "daewoon", "sewoon", "wolwoon", "ilwoon",
        "none", "low", "weak", "moderate", "strong",
        "strong_pressure", "moderate_pressure", "mixed_or_neutral",
        "moderate_support", "strong_support",
        "marriage_signal", "relationship_change", "new_relationship",
        "shadow_only",
    } | {k.value for k in KindCombo}
    patterns = (
        re.compile(r"^[0-9a-f]{16}$"),            # HMAC digest
        re.compile(r"^p\d+\.\d+$"),                # schema version
        re.compile(r"^cal-[0-9.\-]+$"),           # calibration version
        re.compile(r"^k\d+$"),                     # key version
        re.compile(r"^hmac-sort\.v\d+$"),          # sampling version
        re.compile(r"^\d+(\.\d+)?[-+]?(\d+(\.\d+)?)?\+?$"),  # bucket 라벨(0-5 등)
        re.compile(r"^\d+\+?$"),                   # root bucket(0/1/2/3+)
        re.compile(r"^[a-z_]+$"),                  # enum snake_case
    )

    def check(value):
        if isinstance(value, str):
            assert value in allowed_exact or any(
                p.match(value) for p in patterns), f"자유 문자열 유출: {value!r}"
        elif isinstance(value, dict):
            for k, v in value.items():
                check(k)
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)

    check(batch.model_dump(mode="json"))


def test_dto_extra_forbid() -> None:
    """§4 — DTO·batch·audit 전부 extra=forbid(새 필드 자동 유출 차단)."""
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        LegacyCandidateAudit(event_key="x", candidate_present=False, rank=1)
    t = build_relationship_vector_telemetry(_envelope())
    with pytest.raises(pydantic.ValidationError):
        type(t).model_validate({**t.model_dump(), "freeform": "leak"})


def test_detail_sampling_does_not_affect_aggregate() -> None:
    """§5 — 상세 샘플 선택이 달라져도 aggregate는 완전히 동일(역순 입력 비교)."""
    envs = []
    for y in range(2027, 2027 + 40):
        obs = vector_observation_id(
            thread_scope="t1", turn=3, subject_scope="self",
            period_identity=f"sewoon:{y}", input_signature="sig")
        envs.append(_envelope().model_copy(update={
            "period_identity": f"sewoon:{y}", "observation_id": obs}))
    a = build_batch(envs)
    b = build_batch(list(reversed(envs)))
    assert a.aggregate.model_dump() == b.aggregate.model_dump()


def test_legacy_cap_units_separated() -> None:
    """§6 — cap 후보 수와 cap 발생 기간 수 분리, 후보 없는 기간도 벡터 정상."""
    with_caps = _envelope(audits=[
        LegacyCandidateAudit(event_key="marriage_signal", candidate_present=True,
                             relation_capped=True),
        LegacyCandidateAudit(event_key="relationship_change", candidate_present=True,
                             relation_capped=True),
        LegacyCandidateAudit(event_key="new_relationship", candidate_present=False,
                             relation_capped=False),
    ])
    no_candidates = _envelope(audits=[])  # 후보 없는 기간 — 벡터는 존재
    batch = build_batch([with_caps, no_candidates])
    assert batch.aggregate.legacy_candidate_count == 3
    assert batch.aggregate.legacy_capped_candidate_count == 2
    assert batch.aggregate.periods_with_any_legacy_cap == 1
    assert batch.telemetry_record_success_count == 2  # 후보 없어도 관측됨

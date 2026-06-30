"""Marriage Production Readiness v1 — Step 6: 익명 결혼 텔레메트리.

핵심 검증: ① 관계 MT 후보만 집계 ② PII(생년월일·식별자) 미포함 ③ mt4_shadow_diff 합산 ④
active_mt_features 프로파일별 ⑤ emit는 답변을 막지 않음(예외 무해).
"""

from __future__ import annotations

from saju_engines.marriage_telemetry import (
    build_marriage_telemetry,
    emit_marriage_telemetry,
)
from saju_engines.marriage_timing_profile import active_mt_features


class _C:
    def __init__(self, ek: str, stage: str, score: int, reasons: list[str]) -> None:
        self.event_key = ek
        self.marriage_stage = stage
        self.score = score
        self.marriage_stage_reason = reasons


def _cands() -> list:
    return [
        _C("new_relationship", "relationship", 74, ["MT3_DIRECTIONAL_DAY_BRANCH"]),
        _C("marriage_signal", "awareness", 40, ["MT1_DAY_STEM_HAP_PARTNER"]),
        _C("career_change", "", 60, []),            # 비-관계 → 제외
        _C("new_relationship", "", 30, []),         # MT 단계 없음 → 제외
    ]


def test_aggregates_only_relationship_mt() -> None:
    t = build_marriage_telemetry("production_candidate", ["MT1", "MT3"], _cands())
    assert t["relationship_candidate_count"] == 2
    assert {e["event"] for e in t["top_events"]} == {"new_relationship", "marriage_signal"}
    assert set(t["stages_present"]) == {"relationship", "awareness"}


def test_no_pii_keys() -> None:
    t = build_marriage_telemetry("production_candidate", ["MT1"], _cands())
    keys = set(t.keys())
    assert not (keys & {"birth_date", "owner_id", "name", "subject_id", "gender"})


def test_mt4_shadow_diff_sum() -> None:
    shadow = [{"relation_mt4_diff": -4.2}, {"relation_mt4_diff": -2.0}]
    t = build_marriage_telemetry("production_candidate", [], _cands(), shadow)
    assert t["mt4_shadow_diff"] == -6.2
    assert t["mt4_shadow_entries"] == 2


def test_active_mt_features_by_profile() -> None:
    assert active_mt_features("default") == []
    feats = active_mt_features("production_candidate")
    assert "MT1" in feats and "MT2" in feats and "MT3" in feats
    assert "MT4_shadow" in feats and "MT6" in feats


def test_emit_never_raises() -> None:
    # 직렬화 불가 값이 섞여도 답변을 막지 않는다(예외 삼킴).
    emit_marriage_telemetry({"bad": object()})
    emit_marriage_telemetry(build_marriage_telemetry("default", [], _cands()))

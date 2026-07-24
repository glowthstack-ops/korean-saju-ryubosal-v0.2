"""Marriage Production Readiness v1 — Step 2: marriage_stage LLM payload 연결.

핵심 검증: ① derive_marriage_stage 규칙(MT1→awareness / MT3·MT2강회귀→relationship / 비-MT→"") ②
commitment 초과 금지(stage_limit) ③ LlmEventCandidate 신규 필드 ④ chat(context_reducer)·report
(report_event_input) 직렬화에 stage 라인 — MT 있을 때만 ⑤ default 프로파일(MT OFF)에서 출력 불변.
"""

from __future__ import annotations

from saju_engines.context_reducer import _to_llm_candidate
from saju_engines.report_event_input import _marriage_stage_note
from saju_shared_types.events import EventCandidate, EventType
from saju_shared_types.marriage_timing import derive_marriage_stage


def _cand(event_key: str = "new_relationship", evidence: list[str] | None = None) -> EventCandidate:
    return EventCandidate(
        event_key=event_key, event_type=EventType.PROGRESS, period="2026",
        score=50, confidence="medium", polarity="conditional",
        evidence_path=evidence or [],
    )


# ── derive 규칙 ──────────────────────────────────────────────────────


def test_derive_awareness_from_mt1() -> None:
    st = derive_marriage_stage(["MT1_DAY_STEM_HAP_PARTNER", "MT1_STAGE_AWARENESS"])
    assert st.stage == "awareness" and st.base_stage == "awareness"
    assert st.stage_limit == "commitment_marker_absent"


def test_derive_relationship_from_mt3() -> None:
    st = derive_marriage_stage(["MT3_DIRECTIONAL_DAY_BRANCH"])
    assert st.stage == "relationship" and st.base_stage == "action"


def test_derive_relationship_from_mt2_same_stem() -> None:
    st = derive_marriage_stage(["MT2_EMERGENCE_SAME_STEM"])
    assert st.stage == "relationship"


def test_derive_empty_when_no_mt() -> None:
    st = derive_marriage_stage(["REL_HAP_day_pillar", "DAEWOON_TRANSITION_BOOST_0.50"])
    assert st.stage == "" and st.stage_reason == []


def test_never_exceeds_relationship() -> None:
    """MT가 겹쳐도 commitment/formalization으로 못 올라간다(marker 미구현 → 상한)."""
    st = derive_marriage_stage([
        "MT1_DAY_STEM_HAP_PARTNER", "MT3_DIRECTIONAL_DAY_BRANCH", "MT2_EMERGENCE_SAME_STEM",
    ])
    assert st.stage in ("awareness", "relationship")
    assert st.stage_limit == "commitment_marker_absent"


# ── 직렬화 연결 ──────────────────────────────────────────────────────


def test_llm_candidate_carries_stage_when_mt_present() -> None:
    c = _cand(evidence=["MT3_DIRECTIONAL_DAY_BRANCH"])
    out = _to_llm_candidate(c, ganji={}, dw_by_year={})
    assert out.marriage_stage == "relationship"
    assert out.marriage_base_stage == "action"
    assert "MT3_DIRECTIONAL_DAY_BRANCH" in out.marriage_stage_reason
    assert out.marriage_stage_limit == "commitment_marker_absent"


def test_llm_candidate_empty_stage_when_no_mt() -> None:
    """비-MT 후보(=default 프로파일)는 stage 빈값 → 렌더 미노출(출력 불변)."""
    c = _cand(evidence=["REL_HAP_day_pillar"])
    out = _to_llm_candidate(c, ganji={}, dw_by_year={})
    assert out.marriage_stage == ""
    assert out.marriage_stage_reason == []


def test_report_stage_note_present_and_absent() -> None:
    """report 접미사 — MT 있으면 관계단계 표기, 없으면 빈 문자열(출력 불변)."""
    assert _marriage_stage_note(_cand(evidence=["MT3_DIRECTIONAL_DAY_BRANCH"])).startswith(
        " · 관계단계 relationship"
    )
    assert _marriage_stage_note(_cand(evidence=["REL_HAP_day_pillar"])) == ""
    assert _marriage_stage_note(_cand(evidence=[])) == ""


# ── B2 보강(RELATIONSHIP_EVENT_SYSTEM 부록 B) — stability_risk 전 경로 전달 ────────


def test_llm_candidate_stability_risk_from_rel_evidence() -> None:
    """chat 경로: full evidence_path의 REL_CHUNG_*가 marriage_stability_risk로 보존된다."""
    c = _cand(evidence=["MT2_EMERGENCE_SAME_STEM", "REL_CHUNG_day_pillar", "REL_COMPOUND"])
    out = _to_llm_candidate(c, ganji={}, dw_by_year={})
    assert out.marriage_stability_risk is True


def test_llm_candidate_stability_risk_false_for_hap_only() -> None:
    """합 단독은 위험 아님 — 필드 False(방향 누수 차단은 충·형·파·해 한정)."""
    c = _cand(evidence=["REL_HAP_day_pillar", "MT3_DIRECTIONAL_DAY_BRANCH"])
    out = _to_llm_candidate(c, ganji={}, dw_by_year={})
    assert out.marriage_stability_risk is False


def test_llm_candidate_stability_risk_deserialization_default() -> None:
    """구버전 payload(필드 부재) 역직렬화 호환 — 기본값 False."""
    c = _cand(evidence=["REL_CHUNG_day_pillar"])
    data = _to_llm_candidate(c, ganji={}, dw_by_year={}).model_dump()
    data.pop("marriage_stability_risk")
    from saju_shared_types.llm_input import LlmEventCandidate
    assert LlmEventCandidate.model_validate(data).marriage_stability_risk is False

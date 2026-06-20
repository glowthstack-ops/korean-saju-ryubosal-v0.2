"""직업운 결과 길흉 신호가 레거시 어댑터·LLM 입력까지 살아남는지 검증.

favorability 채널과 새 reason_code(EXAM_/CAREER_EXIT/JOBCHANGE_/PROFILE_public_official)가
to_legacy_candidate → context_reducer 직렬화에서 드롭되지 않고 사용자 향 신호로 표면화됨을 고정.
"""

from __future__ import annotations

from saju_engines.context_reducer import _favorability_ko
from saju_engines.event_engine_v2 import to_legacy_candidate
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_shared_types.event_engine import EventCandidateV2


def test_reason_codes_ko_maps_new_career_codes() -> None:
    # 새 코드가 prefix 매핑으로 한글 신호가 된다(이전엔 조용히 누락).
    codes = [
        "EXAM_PASS_관인상생", "EXAM_FAIL_상관견관", "CAREER_EXIT_RISK",
        "CAREER_SPECIAL_OCC_CLASH_BOOST", "JOBCHANGE_PRESSURE_DRIVEN",
        "JOBCHANGE_OPPORTUNITY", "PROFILE_public_official_transfer",
    ]
    out = reason_codes_ko(codes)
    assert "합격 기류" in out
    assert "불합격 위험" in out
    assert "퇴직·이탈 리스크" in out
    assert "특수직군 길화" in out
    assert "압박성 이직" in out
    assert "기회성 이직" in out
    assert "공직 발령·전보" in out


def test_specific_profile_prefix_beats_generic() -> None:
    # PROFILE_public_official_*는 일반 PROFILE_('프로필 반영')보다 구체 라벨로 매칭.
    out = reason_codes_ko(["PROFILE_public_official_transfer"])
    assert out == ["공직 발령·전보"]
    assert reason_codes_ko(["PROFILE_job_gain_to_promotion"]) == ["프로필 반영"]


def test_to_legacy_candidate_preserves_favorability() -> None:
    # favorability가 레거시 EventCandidate로 보존된다(이전엔 드롭).
    c = EventCandidateV2(
        event_key="education_admission", period="2026", score=60, favorability=0.4,
    )
    legacy = to_legacy_candidate(c)
    assert legacy.favorability == 0.4


def test_favorability_band_labels() -> None:
    assert _favorability_ko(0.4) == "유리(결과 우호)"
    assert _favorability_ko(-0.4) == "불리(결과 주의)"
    assert _favorability_ko(0.1) == ""  # 중립대는 노출 안 함

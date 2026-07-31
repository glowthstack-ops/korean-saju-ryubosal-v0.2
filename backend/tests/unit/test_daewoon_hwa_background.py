"""대운 합화 체용 배경 — 현행(랭킹 반영)과 post_selection(서사 전용) 두 모드.

원래 이 파일은 `DAEWOON_HWA_BG_*` 가 candidate 의 `reason_codes` 에 실린다는 것을 고정하고
있었다. DW-HWA 감사에서 그 위치가 **잘못된 의미 계약**임이 드러났다 — 점수 기여가 없더라도
근거 목록을 읽는 guard·리포트·감사가 "이 사건의 발생을 대운이 지지했다" 로 오독한다.
분기는 `event_key` 가 아니라 `quality`(길/흉군)이므로 그런 뜻이 아니다.

그래서 문자열 값 계약은 보존하되 위치를 `DaewoonHwaBackground.evidence_code` 로 옮겼다.

    DAEWOON_HWA_EVIDENCE_CODE_VALUE_PRESERVED
    DAEWOON_HWA_OCCURRENCE_REASON_REMOVED
    DAEWOON_HWA_BACKGROUND_PROVENANCE_PRESERVED

기본 모드는 여전히 `'current'` 라 production 은 불변이다(PRODUCTION_FLAG_UNCHANGED).
"""

from __future__ import annotations

import pytest

from saju_engines.daewoon_background import (
    LEGACY_SCORE_COEFFICIENT,
    DaewoonHwaBackground,
    background_narrative_block,
    background_narrative_frame,
    derive_daewoon_hwa_background,
)
from saju_engines.event_engine_v2 import _apply_daewoon_hwa_background
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventQuality,
    PolarityRole,
)


def _c(quality: EventQuality) -> EventCandidateV2:
    return EventCandidateV2(event_key="wealth_change", period="2026", score=100, quality=quality)


# ── 현행 모드(기본) — production 불변 ─────────────────────────────────────


def test_pressure_daewoon_biases_bad_up_good_down() -> None:
    """압력 대운(기신 化) — 흉 사건 성패율↓(점수↑), 길 사건 완화(↓)."""
    bad = _apply_daewoon_hwa_background([_c(EventQuality.LOSS)], PolarityRole.GI)[0]
    good = _apply_daewoon_hwa_background([_c(EventQuality.OPPORTUNITY)], PolarityRole.GI)[0]
    assert bad.score == 103 and good.score == 97
    assert any("DAEWOON_HWA_BG_압력" in rc for rc in bad.reason_codes)


def test_boon_daewoon_biases_good_up_bad_down() -> None:
    """보강 대운(용신 化) — 길 사건↑, 흉 사건 완화(↓)."""
    good = _apply_daewoon_hwa_background([_c(EventQuality.ACHIEVEMENT)], PolarityRole.YONG)[0]
    bad = _apply_daewoon_hwa_background([_c(EventQuality.CONFLICT)], PolarityRole.YONG)[0]
    assert good.score == 103 and bad.score == 97
    assert any("DAEWOON_HWA_BG_보강" in rc for rc in good.reason_codes)


def test_none_or_neutral_unchanged() -> None:
    """대운 합화 없음/중립 → 무변경(사건 종류·점수 불변)."""
    c = _apply_daewoon_hwa_background([_c(EventQuality.LOSS)], None)[0]
    assert c.score == 100 and not any("DAEWOON_HWA" in rc for rc in c.reason_codes)


def test_quality_without_direction_unchanged() -> None:
    """방향 없는 품질(mixed 등)은 성패 보정 대상 아님."""
    c = _apply_daewoon_hwa_background([_c(EventQuality.MIXED)], PolarityRole.GI)[0]
    assert c.score == 100


def test_default_mode_is_current() -> None:
    """기본값이 바뀌면 production 이 조용히 달라진다."""
    assert _apply_daewoon_hwa_background(
        [_c(EventQuality.LOSS)], PolarityRole.GI
    )[0].score == 103


# ── post_selection 모드 — 점수·근거 불변 ──────────────────────────────────


@pytest.mark.parametrize("role", [PolarityRole.GI, PolarityRole.YONG, PolarityRole.HEE])
@pytest.mark.parametrize(
    "quality", [EventQuality.LOSS, EventQuality.OPPORTUNITY, EventQuality.MIXED]
)
def test_post_selection_touches_neither_score_nor_reasons(
    role: PolarityRole, quality: EventQuality
) -> None:
    """랭킹 영향 0 — 점수도 근거 코드도 바뀌지 않는다."""
    src = _c(quality)
    out = _apply_daewoon_hwa_background([src], role, mode="post_selection")[0]
    assert out.score == src.score
    assert out.reason_codes == src.reason_codes
    assert not any("DAEWOON_HWA" in rc for rc in out.reason_codes)
    assert "daewoon_hwa" not in out.contributions


def test_post_selection_preserves_canonical_quality() -> None:
    """canonical EventQuality 는 YongiQualityEngine 소관 — 배경이 바꾸지 않는다."""
    src = _c(EventQuality.LOSS)
    out = _apply_daewoon_hwa_background([src], PolarityRole.YONG, mode="post_selection")[0]
    assert out.quality is EventQuality.LOSS


# ── 배경 파생 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "state", "code"),
    [
        (PolarityRole.YONG, "supportive", "DAEWOON_HWA_BG_보강"),
        (PolarityRole.HEE, "supportive", "DAEWOON_HWA_BG_보강"),
        (PolarityRole.GI, "pressuring", "DAEWOON_HWA_BG_압력"),
    ],
)
def test_evidence_code_value_preserved_at_new_location(
    role: PolarityRole, state: str, code: str
) -> None:
    """문자열 값은 그대로, 위치만 배경으로 옮긴다."""
    bg = derive_daewoon_hwa_background(role)
    assert bg.state == state
    assert bg.evidence_code == code
    assert bg.support_eligibility == "REVIEW_REQUIRED"
    assert bg.usage == "narrative_background_only"


def test_no_hwa_is_not_applicable() -> None:
    """합화 불성립 — 음성 대조에서 이 값이어야 한다."""
    bg = derive_daewoon_hwa_background(None)
    assert bg.state == "not_applicable"
    assert not bg.applicable
    assert bg.evidence_code is None


def test_neutral_role_has_no_direction() -> None:
    """중립은 방향이 없어 서사에 붙일 것이 없다."""
    bg = derive_daewoon_hwa_background(PolarityRole.NEUTRAL)
    assert bg.state == "neutral" and not bg.applicable


def test_legacy_coefficient_is_audit_metadata_not_intensity() -> None:
    """0.03 은 랭킹 계수였다 — 서사 강도로 재사용하지 않는다.

    강도·등급 필드를 두지 않는 것이 계약이다. 두면 검증된 적 없는 수치가 서사 강약을
    결정하게 된다.
    """
    bg = derive_daewoon_hwa_background(PolarityRole.GI)
    assert bg.legacy_score_coefficient == LEGACY_SCORE_COEFFICIENT
    assert not hasattr(bg, "strength")
    assert not hasattr(bg, "narrative_intensity")


# ── 서사 결합(렌더링 단계) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "quality", "fragment"),
    [
        (PolarityRole.YONG, EventQuality.OPPORTUNITY, "받쳐주는"),
        (PolarityRole.YONG, EventQuality.LOSS, "누그러뜨리는"),
        (PolarityRole.GI, EventQuality.ACHIEVEMENT, "제약을 더하는"),
        (PolarityRole.GI, EventQuality.LOSS, "체감 부담을 키우는"),
    ],
)
def test_four_combinations_render_distinct_frames(
    role: PolarityRole, quality: EventQuality, fragment: str
) -> None:
    """배경 × quality 4조합. 전부 '이미 선택된' 사건의 체감 서술이다."""
    frame = background_narrative_frame(derive_daewoon_hwa_background(role), quality)
    assert frame is not None
    assert fragment in frame
    assert "이미 선택된" in frame


def test_frame_absent_when_quality_has_no_direction() -> None:
    """방향 없는 품질에 억지로 프레임을 붙이면 근거 없는 체감 서술이 된다."""
    bg = derive_daewoon_hwa_background(PolarityRole.GI)
    assert background_narrative_frame(bg, EventQuality.MIXED) is None
    assert background_narrative_frame(bg, None) is None


def test_frame_absent_for_not_applicable() -> None:
    """합화가 없으면 붙일 배경도 없다."""
    assert background_narrative_frame(
        derive_daewoon_hwa_background(None), EventQuality.LOSS
    ) is None


# ── 반복 주입 방지 ───────────────────────────────────────────────────────


def _bg_map() -> dict[str, DaewoonHwaBackground]:
    return {
        "2027-03": derive_daewoon_hwa_background(PolarityRole.GI),
        "2028-06": derive_daewoon_hwa_background(PolarityRole.YONG),
        "2029-01": derive_daewoon_hwa_background(None),
    }


def test_same_period_described_once_within_a_call() -> None:
    """한 호출 안에서 같은 시점이 여러 대표로 나와도 한 번만 서술한다."""
    reps = [("2027-03", EventQuality.LOSS), ("2027-03", EventQuality.PRESSURE)]
    assert len(background_narrative_block(reps, _bg_map())) == 1


def test_request_scoped_dedup_suppresses_later_sections() -> None:
    """섹션이 바뀌어도 같은 (시점, 방향)은 요청 안에서 한 번만 상세 서술한다."""
    seen: set[tuple[str, str]] = set()
    reps = [("2027-03", EventQuality.LOSS)]
    first = background_narrative_block(reps, _bg_map(), already_described=seen)
    second = background_narrative_block(reps, _bg_map(), already_described=seen)
    assert len(first) == 1
    assert second == []


def test_not_applicable_period_yields_no_line() -> None:
    """합화 없는 시점에는 배경 문장이 붙지 않는다."""
    assert background_narrative_block([("2029-01", EventQuality.LOSS)], _bg_map()) == []


def test_unknown_period_is_skipped() -> None:
    """맵에 없는 시점은 조용히 건너뛴다 — 없는 배경을 지어내지 않는다."""
    assert background_narrative_block([("2099-12", EventQuality.LOSS)], _bg_map()) == []

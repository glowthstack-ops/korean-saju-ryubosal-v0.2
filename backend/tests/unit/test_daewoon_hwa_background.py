"""대운 합화 체용 배경 보정(슬라이스 2) — 직접 치환 아님, 성패율에 약한 배경 가중.

대운 천간이 합화하면 化神의 용기신 역할로 그 대운 기간 사건 성패율을 미세 보정한다(10년 배경
체질 변화). 사건 종류·개수는 불변. 보강 대운(化神 용·희)은 길 사건↑·흉 사건 완화, 압력 대운
(化神 기·구)은 흉 사건↑·길 사건↓.
"""

from __future__ import annotations

from saju_engines.event_engine_v2 import _apply_daewoon_hwa_background
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventQuality,
    PolarityRole,
)


def _c(quality: EventQuality) -> EventCandidateV2:
    return EventCandidateV2(event_key="wealth_change", period="2026", score=100, quality=quality)


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

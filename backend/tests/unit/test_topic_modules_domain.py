"""도메인 신호형 Topic Builder 모듈 검증 — M01·M02·M09·M11·M12 (docs/09 4·5장).

합성 LuckComposite(도메인 신호 주입)로 모듈이 올바른 도메인/이벤트만 집계하고 정책 톤(절대원칙
3·8)을 싣는지 결정론적으로 검증한다. 실차트 의존을 피해 신호 매핑 자체를 고정한다.
"""

from __future__ import annotations

import pytest

from saju_engines.topic_builder import build_topic_context
from saju_shared_types.precompute import (
    CompositeGanji,
    CompositeLevel,
    DomainSignal,
    LuckComposite,
    TenGodPair,
)
from saju_shared_types.topic_context import PeriodSpec

_PERIOD = PeriodSpec(start="2024", end="2027", granularity="year")


def _comp(
    period_key: str, domain: str, event_key: str, *, weight: float = 0.6, fav: str = "용신",
    stem: str = "甲", branch: str = "辰",
) -> LuckComposite:
    return LuckComposite(
        subject_id="s", level=CompositeLevel.YEAR, period_key=period_key,
        ganji=CompositeGanji(stem=stem, branch=branch),
        ten_god=TenGodPair(stem="편재", branch_main="정관"), twelve_stage="건록",
        favorability=fav,
        domain_signals=[DomainSignal(
            domain=domain, event_key=event_key, weight=weight, source_interaction="rel_x",
        )],
        dict_version="1.0.0", computed_at="2026-01-01T00:00:00+00:00",
    )


def test_m01_love_picks_relationship_events_only() -> None:
    """M01은 연애 이벤트(relationship_start/end)만, 결혼 이벤트는 제외."""
    comps = [
        _comp("2025", "relationship", "relationship_start"),
        _comp("2026", "relationship", "marriage"),  # M01 제외 대상
        _comp("2025", "wealth", "wealth_change"),  # 타도메인 제외
    ]
    ctx = build_topic_context("M01", [], _PERIOD, comps)
    assert ctx.module_id == "M01" and ctx.findings
    assert all(f.event_key == "relationship_start" for f in ctx.findings)


def test_m02_marriage_picks_marriage_events_only() -> None:
    """M02는 결혼·가정 이벤트만, 연애 시작은 제외."""
    comps = [
        _comp("2026", "relationship", "marriage"),
        _comp("2025", "relationship", "relationship_start"),  # M02 제외
    ]
    ctx = build_topic_context("M02", [], _PERIOD, comps)
    assert ctx.findings and all(
        f.event_key in ("marriage", "childbirth", "family_change") for f in ctx.findings
    )


def test_m09_wealth_aggregates_wealth_domain() -> None:
    """M09는 wealth 도메인 신호를 점수로 확정(시계열·findings)."""
    comps = [
        _comp("2025", "wealth", "wealth_change", weight=0.8),
        _comp("2026", "wealth", "windfall", weight=0.5),
        _comp("2025", "health", "health_issue"),  # 제외
    ]
    ctx = build_topic_context("M09", [], _PERIOD, comps)
    assert {f.period_key for f in ctx.findings} == {"2025", "2026"}
    assert ctx.findings[0].period_key == "2025"  # 가중 큰 쪽이 상위
    assert all(0 <= p.score <= 100 for p in ctx.time_series)


def test_m11_health_and_m12_education_domains() -> None:
    """M11=health, M12=education 도메인만 각각 집계."""
    comps = [
        _comp("2025", "health", "health_issue"),
        _comp("2026", "education", "exam"),
    ]
    h = build_topic_context("M11", [], _PERIOD, comps)
    e = build_topic_context("M12", [], _PERIOD, comps)
    assert [f.event_key for f in h.findings] == ["health_issue"]
    assert [f.event_key for f in e.findings] == ["exam"]


def test_policy_tone_notes_present() -> None:
    """정책 톤(절대원칙 8·3): 재물=횡재 가드, 시험=당락 금지, 건강=의료 단정 금지, 결혼=보류."""
    comps_w = [_comp("2025", "wealth", "windfall")]
    comps_e = [_comp("2025", "education", "exam")]
    comps_h = [_comp("2025", "health", "surgery")]
    comps_m = [_comp("2026", "relationship", "marriage")]
    def _tones(mid: str, comps: list) -> list[str]:
        return build_topic_context(mid, [], _PERIOD, comps).style_rules.tone_notes

    assert any("횡재" in t for t in _tones("M09", comps_w))
    assert any("당락" in t for t in _tones("M12", comps_e))
    assert any("전문의" in t for t in _tones("M11", comps_h))
    assert any("보류" in t for t in _tones("M02", comps_m))


def test_findings_deterministic_and_calendar_attached() -> None:
    """동일 입력 → 동일 출력 + 시계열 간지가 압축 간지달력에 동반(절대원칙 2)."""
    comps = [_comp("2025", "wealth", "wealth_change"), _comp("2026", "wealth", "windfall")]
    a = build_topic_context("M09", [], _PERIOD, comps)
    b = build_topic_context("M09", [], _PERIOD, comps)
    assert a.model_dump() == b.model_dump()
    cal_keys = {e.period_key for e in a.calendar_context}
    assert {p.period_key for p in a.time_series} <= cal_keys
    assert all(p.ganji for p in a.time_series)


@pytest.mark.parametrize("mid", ["M04", "M05", "M06", "M08", "M13", "M14"])
def test_still_planned_modules_raise(mid: str) -> None:
    """아직 미구현 모듈은 NotImplementedError(이번 배치 범위 밖)."""
    with pytest.raises(NotImplementedError):
        build_topic_context(mid, [], _PERIOD, [])

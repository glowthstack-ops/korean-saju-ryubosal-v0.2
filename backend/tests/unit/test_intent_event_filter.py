"""IntentEventFilter 검증 (Phase 7c — 의도·컨텍스트 후보 필터)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from saju_engines.intent_event_filter import IntentEventFilter

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@dataclass
class _C:
    event_key: str


def _f() -> IntentEventFilter:
    return IntentEventFilter(_DICTS)


def test_career_deprioritizes_relationship() -> None:
    f = _f()
    cands = [_C("career_change"), _C("new_relationship"), _C("windfall")]
    out = {c.event_key for c in f.filter(cands, "career")}
    assert "career_change" in out
    assert "new_relationship" not in out and "windfall" not in out


def test_general_keeps_all() -> None:
    f = _f()
    cands = [_C("career_change"), _C("childbirth"), _C("windfall")]
    out = f.filter(cands, "general")
    assert len(out) == 3


def test_empty_fallback_keeps_original() -> None:
    # 전부 deprioritize 대상이면 원본 유지(빈 결과 방지).
    f = _f()
    cands = [_C("new_relationship"), _C("childbirth")]
    out = f.filter(cands, "career")
    assert out == cands


def test_daily_context_overlay() -> None:
    f = _f()
    cands = [_C("wealth_change"), _C("marriage_signal")]
    out = {c.event_key for c in f.filter(cands, "general", context="daily_fortune")}
    # 일운 컨텍스트는 marriage_signal/childbirth 등 장기 사건 제외.
    assert "wealth_change" in out and "marriage_signal" not in out


def test_domain_includes() -> None:
    f = _f()
    assert "career_change" in f.domain_includes("career")
    assert f.domain_includes("general")

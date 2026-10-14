"""intent_event_filter 'exclude' 오버레이 — 비연애 관계 질문의 연애·결혼 후보 제거(2026-10-14)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from saju_engines.intent_event_filter import IntentEventFilter
from saju_engines.relationship_hints import (
    NON_ROMANTIC_RELATION_TYPES,
    is_non_romantic_relation,
    non_romantic_frame_directive,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _c(key: str):
    return SimpleNamespace(event_key=key)


def test_non_romantic_overlay_drops_marriage_and_romance_keys():
    f = IntentEventFilter(_DICTS)
    cands = [
        _c("relationship_change"), _c("marriage_signal"), _c("new_relationship"),
        _c("social_conflict"),
    ]
    out = f.filter(cands, "relationship", "non_romantic_relation")
    assert [c.event_key for c in out] == ["relationship_change", "social_conflict"]
    # 전부 걸러지면 원본 유지(차단 금지).
    only = [_c("marriage_signal")]
    assert f.filter(only, "relationship", "non_romantic_relation") == only
    # 오버레이 없으면 기존 동작.
    assert len(f.filter(cands, "relationship")) == 4


def test_non_romantic_types_and_directive():
    assert is_non_romantic_relation("parent_child") and not is_non_romantic_relation("romance")
    assert not is_non_romantic_relation(None) and "spouse" not in NON_ROMANTIC_RELATION_TYPES
    d = non_romantic_frame_directive("parent_child", "박여사")
    assert d.startswith("[관계 유형 — 부모·자식: 본인과 박여사]") and "보호와 독립" in d

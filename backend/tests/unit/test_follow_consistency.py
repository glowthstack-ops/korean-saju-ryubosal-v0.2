"""C1-c C안 — 종격 두 기준 정합 표기(follow_consistency)와 FOLLOW_MAX_SCORE 단일 출처 (2026-10-08).

판정 통일이 아니라 불일치 관리: main_structure·special_pattern·점수·역할은 바뀌지 않고, 어느
한쪽이라도 종격을 보면 두 기준의 판정을 나란히 적는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_manse_analysis.strength import strength_score
from saju_manse_analysis.structure import geokguk_eval

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "test_fixtures" / "manse" / "golden"
_CHARTS = Path(__file__).resolve().parents[2] / "data" / "shadow_charts" / "charts.jsonl"


def _golden_input(name: str) -> BirthInput:
    return BirthInput(**json.loads((_GOLDEN / f"{name}.json").read_text("utf-8"))["input"])


def _shadow_input(chart_id: str) -> BirthInput:
    for line in _CHARTS.read_text("utf-8").splitlines():
        rec = json.loads(line)
        if rec["chart_id"] == chart_id:
            return BirthInput(**rec["input"])
    raise KeyError(chart_id)


def test_follow_max_score_single_source() -> None:
    """격국 평가는 strength_score 의 FOLLOW_MAX_SCORE 를 그대로 쓴다(사본 상수 없음)."""
    assert not hasattr(geokguk_eval, "_FOLLOW_MAX_SCORE")
    assert geokguk_eval.FOLLOW_MAX_SCORE is strength_score.FOLLOW_MAX_SCORE


def test_mismatch_when_only_yongsin_detects_follow() -> None:
    """japan_tokyo 골든(乙丑己卯癸丑己未): 격국 식신격·신호 없음, 용신 종격 → mismatch."""
    r = calculate(_golden_input("japan_tokyo_standard"))
    g = r.geokguk
    assert g.main_structure == "식신격" and g.special_pattern is None
    fc = g.follow_consistency
    assert fc is not None and fc["status"] == "mismatch"
    assert fc["geokguk_signal"] is None and fc["yongsin_follow_kind"] in ("real", "pseudo")
    assert "종격" in fc["note"]


def test_consistent_when_both_confirm() -> None:
    """shadow jonggyeok_01: 격국 override 종격 + 용신 진종 → consistent."""
    r = calculate(_shadow_input("jonggyeok_01"))
    g = r.geokguk
    sp = g.special_pattern
    assert sp and sp["type"] == "follow" and sp["override"]
    fc = g.follow_consistency
    assert fc is not None and fc["status"] == "consistent"
    assert fc["yongsin_follow_kind"] == "real"


def test_none_when_neither_detects() -> None:
    """정격이고 용신도 종격을 보지 않으면 None(표기 없음)."""
    r = calculate(_golden_input("korea_seoul_1980_11_22"))
    assert r.geokguk.special_pattern is None
    assert r.geokguk.follow_consistency is None

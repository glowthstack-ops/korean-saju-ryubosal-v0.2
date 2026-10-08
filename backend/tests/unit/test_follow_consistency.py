"""종격 공통 판정기(strength.follow_check) 통합 후 정합 표기(follow_consistency) 계약 (2026-10-08).

C안(불일치 관리)에서 통합으로 전환: 격국 special_signal 과 용신 detect_special_cases 가 같은
detect_follow 를 쓰므로 follow 의 mismatch 는 더 이상 생기지 않는다. 표기 필드는 투명성용으로
남긴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_manse_analysis.strength import follow_check, strength_score
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
    """종격 전제 점수 임계는 strength_score 하나(공통 판정기가 import, 격국에 사본 상수 없음)."""
    assert not hasattr(geokguk_eval, "_FOLLOW_MAX_SCORE")
    assert follow_check.FOLLOW_MAX_SCORE is strength_score.FOLLOW_MAX_SCORE


def test_unified_detector_resolves_japan_tokyo() -> None:
    """japan_tokyo 골든(乙丑己卯癸丑己未): 비겁 뿌리 11(丑 중기 癸×2) → 공통 기준상 종격 아님.

    통합 전에는 용신만 종격(세력비)이라 mismatch 였다. 이제 격국 식신격 유지, 용신도 종격 모델을
    쓰지 않으며 정합 표기는 None(양쪽 모두 종격 아님).
    """
    r = calculate(_golden_input("japan_tokyo_standard"))
    g = r.geokguk
    assert g.main_structure == "식신격" and g.special_pattern is None
    assert g.follow_consistency is None
    assert r.force_analysis.strength.components["peer_root_score"] >= follow_check.PEER_ROOT_MAX
    assert r.yongsin_analysis.final["selected_model"] != "follow_structure"
    assert not r.yongsin_analysis.special_case_checks["follow_structure"].detected


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

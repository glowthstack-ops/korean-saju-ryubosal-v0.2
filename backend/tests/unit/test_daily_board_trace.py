"""OA-9r — 감사 추적이 라이브 선택과 같은지, 그리고 지표 이름이 단계를 밝히는지.

OA-9a 정정의 원인은 **감사가 선택 로직을 흉내 낸 것**이었다. `cautions[0]`(점수순
주의 1위)을 "주의 슬롯 승자"로 셌는데, 라이브 선택기는 주의를 good 과 다른 도메인에서
뽑는다. 실측 421건에서 원시 1위 100% · 표시 0% 로 갈렸다.

재발을 막는 장치는 둘이다.
  1. 감사는 라이브 순수 함수를 그대로 호출한다 — `trace_board` 결과가 `compute_board`
     와 한 건도 다르면 안 된다.
  2. 지표 이름이 선택 단계를 밝힌다 — `top1`·`winner` 처럼 단계가 불명확한 이름 금지.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_board_trace import (
    AMBIGUOUS_METRIC_NAMES,
    STAGES,
    trace_board,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

_AUDITS = Path(M.__file__).resolve().parents[4] / "doc" / "v2_2" / "audits"


def _scored_by_ilju(ctx, dicts) -> dict[str, list]:
    out = {}
    for i in range(60):
        stem, branch = ganzi_from_index(i)
        out[f"{stem.value}{branch.value}"] = [
            M._score_event(k, e, stem, branch, ctx)
            for k, e in dicts.catalog["events"].items()
        ]
    return out


# ── 1. 추적이 라이브와 같다 ────────────────────────────────────────────────


@pytest.mark.parametrize("day", [
    dt.date(2026, 7, 1), dt.date(2026, 7, 29), dt.date(2026, 7, 30), dt.date(2026, 8, 15),
])
def test_trace_reproduces_live_board(day: dt.date) -> None:
    """final_headline 과 3개 슬롯이 `compute_board` 와 완전히 일치한다."""
    dicts = M.load_daily_dicts_for(day)
    ctx = M.build_day_context(day)
    traces = trace_board(_scored_by_ilju(ctx, dicts), day)
    board = M.compute_board(ctx, dicts)

    for f in board.fortunes:
        t = traces[f.ilju]
        assert t.final_headline == str(f.headline_event_key), f.ilju
        assert [
            t.slot_good_selected, t.slot_caution_selected, t.slot_support_selected
        ] == [e.event_key for e in f.events], f.ilju


def test_trace_separates_raw_and_final_headline() -> None:
    """보드 캡이 실제로 옮긴 카드가 있어야 두 단계 구분이 의미를 갖는다."""
    day = dt.date(2026, 8, 15)
    dicts = M.load_daily_dicts_for(day)
    traces = trace_board(_scored_by_ilju(M.build_day_context(day), dicts), day)
    displaced = [t for t in traces.values() if t.board_cap_displaced]
    assert displaced, "캡 이동이 0건이면 raw/final 구분을 검증하지 못한다"
    for t in displaced:
        assert t.raw_headline != t.final_headline
        assert t.board_cap_reason != "raw_top"


def test_raw_rank1_can_differ_from_slot_selection() -> None:
    """점수순 1위와 표시되는 사건이 갈리는 카드가 실제로 존재한다.

    이 차이가 OA-9a 정정의 본질이다 — 없으면 단계 구분이 형식에 그친다.
    """
    day = dt.date(2026, 8, 15)
    dicts = M.load_daily_dicts_for(day)
    traces = trace_board(_scored_by_ilju(M.build_day_context(day), dicts), day)
    assert any(t.raw_rank1 != t.final_headline for t in traces.values())


# ── 2. 지표 이름이 단계를 밝힌다 ───────────────────────────────────────────


def test_stage_vocabulary_is_declared() -> None:
    assert "raw_rank1" in STAGES
    assert "slot_caution_selected" in STAGES
    assert "final_headline" in STAGES
    assert "caution_slot_wins" in AMBIGUOUS_METRIC_NAMES


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, f"{path}/{k}"
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _oa9_audits() -> list[Path]:
    return sorted(_AUDITS.glob("oa9*.json"))


def test_oa9_audits_declare_measurement_stage() -> None:
    """어느 선택 단계를 잰 값인지 밝히지 않은 감사는 결론에 쓸 수 없다."""
    files = _oa9_audits()
    assert files
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("measurement_stage"), path.name


def test_oa9_audits_avoid_ambiguous_metric_names() -> None:
    for path in _oa9_audits():
        data = json.loads(path.read_text(encoding="utf-8"))
        bad = [p for k, p in _walk(data) if k in AMBIGUOUS_METRIC_NAMES]
        assert not bad, f"{path.name}: 단계가 불명확한 지표명 {bad}"


def test_superseded_audits_are_marked() -> None:
    """정정된 감사는 원자료를 남기되 무엇이 대체됐는지 밝힌다."""
    oa9a = json.loads((_AUDITS / "oa9a_signal_routing_90d.json").read_text(encoding="utf-8"))
    c = oa9a["correction"]
    assert c["supersedes"] == "OA-9a caution exposure interpretation"
    assert c["raw_overspend_rate"] == 1.0
    assert c["displayed_overspend_rate"] == 0.0
    assert c["actual_no_adverse_count"] == 29
    assert c["still_valid"] and c["retracted"]

    for name in (
        "oa7c_money_affinity_curve_90d.json",
        "oa7c_domain_coverage_90d.json",
        "oa7c_money_ten_god_90d.json",
    ):
        data = json.loads((_AUDITS / name).read_text(encoding="utf-8"))
        assert data["measurement_stage"] == "raw_candidate_ranking", name
        assert data["superseded_by"].startswith("OA-9r"), name


def test_display_stage_audit_exists_and_is_verified() -> None:
    """표시 기준 재측정이 라이브 보드와 일치했음을 감사 결과가 스스로 밝힌다."""
    data = json.loads((_AUDITS / "oa9r_display_stage_90d.json").read_text(encoding="utf-8"))
    assert data["measurement_stage"] == "display_pipeline"
    result = data["result"]
    assert result["live_board_verified_days"] == result["days"]

"""Scoring Phase 1a — operational adjusted score(감점·산출만) 검증.

flag off 미호출·byte-identical, 감점 단조성·바닥 클램프, A/B component 게이트·조건, 랭킹 미교체,
sidecar index 정렬, 불변. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §14
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import cast

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_api.services.manse_service import calculate
from saju_engines.event_scoring import favorability_map
from saju_engines.scoring_operational import (
    apply_operational_scoring,
    operational_scoring_sidecar,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate

# 희신 과다 교정(2026-07-12) 후 구 표준차트는 A 감점 대상이 아님(水=조건부 한신/병·legacy
# 한신 0) — 교정 후에도 조건부 희신/병이 남는 차트(비겁 희신의 한습 강등, 癸巳 일주)를 쓴다.
_STD = BirthInput(calendar_type="solar", birth_date="1970-01-13", birth_time="04:30",
                  birth_place_name="Seoul", gender="male")
# 차트: 水=조건부 희신/병(legacy 희신)·金=용신 op0.85·木 구신(제살보조)·火 기신·土 조건부 한신/병.
_GBP = {"W": "壬子", "M": "甲寅", "F": "丙午", "E": "戊辰", "G": "庚申"}


def _cands(score=80):
    return [SimpleNamespace(period=p, score=score, event_key=f"e_{p}") for p in _GBP]


def _on(monkeypatch, a=True, b=True):
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_COMPONENTS",
                        {"conditional_byeong_downgrade": a, "low_operability_yongsin": b})


def _apply(monkeypatch, a=True, b=True, score=80):
    _on(monkeypatch, a, b)
    return apply_operational_scoring(calculate(_STD), _cands(score), _GBP)


def _by_period(rows):
    return {r["period"]: r for r in rows}


# ── flag off: wrapper 미산출(None) ──
def test_master_flag_off_returns_none() -> None:
    assert cfg.SCORING_OPERATIONAL_SHADOW_ENABLED is False  # 기본 off
    assert operational_scoring_sidecar(calculate(_STD), _cands(), _GBP) is None


def test_master_flag_on_runs(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_COMPONENTS",
                        {"conditional_byeong_downgrade": True, "low_operability_yongsin": True})
    out = operational_scoring_sidecar(calculate(_STD), _cands(), _GBP)
    assert out is not None and len(out) == len(_GBP)


# ── sidecar index 정렬(동일 period/event_key 충돌 무관) ──
def test_sidecar_index_aligned(monkeypatch) -> None:
    _on(monkeypatch)
    dup = [SimpleNamespace(period="W", score=80, event_key="x") for _ in range(3)]
    rows = apply_operational_scoring(
        calculate(_STD), cast("list[EventCandidate]", dup), {"W": "壬子"})
    assert [r["candidate_index"] for r in rows] == [0, 1, 2]  # 충돌 없이 보존


# ── 감점 단조성 + 바닥 클램프 ──
def test_monotonic_and_floor(monkeypatch) -> None:
    rows = _apply(monkeypatch, score=80)
    for r in rows:
        assert r["operational_adjusted_score"] <= r["legacy_score"]    # 감점만
        assert r["operational_score_delta"] <= 0
        assert r["operational_adjusted_score"] >= math.ceil(80 * 0.5)  # 바닥
        assert all(v > 0 for v in r["penalties"].values())            # penalty 양수


# ── A: 조건부 희신/병(水)만 downgrade, legacy_fav>0 조건 ──
def test_component_A_only(monkeypatch) -> None:
    rows = _by_period(_apply(monkeypatch, a=True, b=False))
    assert rows["W"]["operational_score_delta"] < 0          # 水 조건부 희신/병 감점
    assert "conditional_byeong_downgrade" in rows["W"]["penalties"]
    assert rows["F"]["operational_score_delta"] == 0         # 火 기신(legacy_fav<0) 무감점
    assert rows["E"]["operational_score_delta"] == 0         # 土 조건부 한신/병(legacy 0) 무감점


# ── B: 낮은 operability 용신(金 op0.85)만, 용신 오행 한정 ──
def test_component_B_only(monkeypatch) -> None:
    rows = _by_period(_apply(monkeypatch, a=False, b=True))
    assert rows["G"]["operational_score_delta"] < 0          # 金 용신 op0.85 감점
    assert "low_operability_yongsin" in rows["G"]["penalties"]
    assert rows["W"]["operational_score_delta"] == 0         # 水(비용신) B 무관
    assert rows["F"]["operational_score_delta"] == 0


# ── 둘 다 off → adjusted=legacy·delta 0 ──
def test_components_both_off(monkeypatch) -> None:
    rows = _apply(monkeypatch, a=False, b=False)
    for r in rows:
        assert r["operational_adjusted_score"] == r["legacy_score"]
        assert r["operational_score_delta"] == 0 and r["penalties"] == {}


# ── missing ganji → skip 명시·임의 계산 금지 ──
def test_missing_ganji(monkeypatch) -> None:
    _on(monkeypatch)
    rows = apply_operational_scoring(
        calculate(_STD),
        cast("list[EventCandidate]",
             [SimpleNamespace(period="ZZ", score=80, event_key="x")]), {})
    assert rows[0]["missing_ganji"] is True
    assert rows[0]["operational_score_delta"] == 0


# ── 불변: 산출이 favorability_map/final 미변경 ──
def test_invariance(monkeypatch) -> None:
    chart = calculate(_STD)
    assert chart.yongsin_analysis is not None
    fav, final = favorability_map(chart), dict(chart.yongsin_analysis.final)
    _on(monkeypatch)
    apply_operational_scoring(chart, _cands(), _GBP)
    assert favorability_map(chart) == fav
    assert dict(chart.yongsin_analysis.final) == final


# ── byte-identical 근거: EventCandidate 스키마 미변경(sidecar 방식) ──
def test_eventcandidate_schema_unchanged() -> None:
    from saju_shared_types.events import EventCandidate
    assert not any(f.startswith("operational_") for f in EventCandidate.model_fields)


# ── 후보 객체 비변형(adjusted 는 sidecar 로만) ──
def test_candidates_not_mutated(monkeypatch) -> None:
    _on(monkeypatch)
    cands = _cands(80)
    before = [(c.period, c.score, c.event_key) for c in cands]
    apply_operational_scoring(calculate(_STD), cands, _GBP)
    assert [(c.period, c.score, c.event_key) for c in cands] == before

"""Scoring Phase 1b — adjusted rank 실험 검증(랭킹 미교체·관찰만).

sub-flag off None·legacy=입력순서·adjusted stable tie-break·level 분리·component 분기·coef_override
config 불변·top-N 이탈·불변·missing_ganji 유지. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §14-8
"""

from __future__ import annotations

from types import SimpleNamespace

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_api.services.manse_service import calculate
from saju_engines.event_scoring import favorability_map
from saju_engines.scoring_operational import (
    adjusted_rank_experiment,
    rank_experiment_sidecar,
)
from saju_shared_types.birth_input import BirthInput

_STD = BirthInput(calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
                  birth_place_name="Seoul", gender="male")
_A = {"conditional_byeong_downgrade": True, "low_operability_yongsin": False}
_B = {"conditional_byeong_downgrade": False, "low_operability_yongsin": True}
_AB = {"conditional_byeong_downgrade": True, "low_operability_yongsin": True}
# 水(조건부 희신/병)·木(용신 op0.595)·金(기신) — year 풀.
_GBP = {"y1": "壬子", "y2": "甲寅", "y3": "庚申", "y4": "丙午", "y5": "戊辰"}
_LEVEL = dict.fromkeys(_GBP, "year")


def _cands(scores):
    return [SimpleNamespace(period=p, score=s, event_key=f"e_{p}")
            for p, s in zip(_GBP, scores, strict=False)]


def _exp(components, scores=(90, 80, 70, 60, 50), coef=None):
    return adjusted_rank_experiment(
        calculate(_STD), _cands(scores), _GBP, _LEVEL,
        components=components, coef_override=coef)


# ── sub-flag off → None ──
def test_subflag_off_none() -> None:
    assert cfg.SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED is False
    assert rank_experiment_sidecar(
        calculate(_STD), _cands((90, 80, 70, 60, 50)), _GBP, _LEVEL,
        components=_AB) is None


def test_subflag_on(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED", True)
    out = rank_experiment_sidecar(
        calculate(_STD), _cands((90, 80, 70, 60, 50)), _GBP, _LEVEL, components=_AB)
    assert out is not None and len(out) == 5


# ── legacy_rank = 입력 순서(재계산 아님) ──
def test_legacy_rank_is_input_order() -> None:
    rows = {r["period"]: r for r in _exp(_AB)}
    # 입력 순서 y1..y5 → legacy_rank_level 1..5 (score 재정렬 아님).
    assert rows["y1"]["legacy_rank_level"] == 1
    assert rows["y5"]["legacy_rank_level"] == 5


# ── adjusted 동점 tie-break = legacy order(stable) ──
def test_adjusted_tiebreak_legacy_order() -> None:
    # 둘 다 off → 모든 adjusted=legacy=동일 점수면 tie. 같은 점수로 두면 adjusted_rank=legacy_rank.
    rows = _exp({"conditional_byeong_downgrade": False, "low_operability_yongsin": False},
                scores=(70, 70, 70, 70, 70))
    for r in rows:
        assert r["adjusted_rank_level"] == r["legacy_rank_level"]  # tie → legacy 유지


# ── level 분리: year/daewoon 독립 풀 ──
def test_level_separation() -> None:
    gbp = {"y1": "壬子", "d1": "甲寅"}
    level = {"y1": "year", "d1": "daewoon"}
    rows = adjusted_rank_experiment(
        calculate(_STD), _cands_for(gbp, (80, 80)), gbp, level, components=_AB)
    by = {r["period"]: r for r in rows}
    assert by["y1"]["pool"] == 1 and by["d1"]["pool"] == 1   # 각 level 1개
    assert by["y1"]["legacy_rank_level"] == 1 and by["d1"]["legacy_rank_level"] == 1


def _cands_for(gbp, scores):
    return [SimpleNamespace(period=p, score=s, event_key="x")
            for p, s in zip(gbp, scores, strict=False)]


# ── component 분기: A-only ≠ B-only (다른 후보가 감점) ──
def test_component_branches_differ() -> None:
    a = {r["period"]: r["operational_adjusted_score"] for r in _exp(_A)}
    b = {r["period"]: r["operational_adjusted_score"] for r in _exp(_B)}
    assert a["y1"] < 90 and b["y1"] == 90   # A는 水(y1) 감점, B는 무관
    assert b["y2"] < 80 and a["y2"] == 80   # B는 木 용신(y2) 감점, A는 무관


# ── coef_override: low_op 14 > 10 감점 · config 불변 ──
def test_coef_override_and_config_immutable() -> None:
    before = cfg.SCORING_OPERATIONAL_COEF["low_op_max_penalty"]
    r10 = {r["period"]: r["operational_adjusted_score"]
           for r in _exp(_B, coef={"low_op_max_penalty": 10.0})}
    r14 = {r["period"]: r["operational_adjusted_score"]
           for r in _exp(_B, coef={"low_op_max_penalty": 14.0})}
    assert r14["y2"] < r10["y2"]   # 木 용신 더 큰 감점
    assert cfg.SCORING_OPERATIONAL_COEF["low_op_max_penalty"] == before  # config 불변


# ── top-N 이탈 플래그 ──
def test_left_topn() -> None:
    # topn=1: 水(y1) 최상위인데 감점되면 top-1 이탈 가능.
    rows = adjusted_rank_experiment(
        calculate(_STD), _cands((90, 89, 70, 60, 50)), _GBP, _LEVEL,
        components=_A, topn=1)
    assert any(r["left_topn"] for r in rows)  # 최상위 감점으로 1위 교체


# ── missing ganji 유지(제거 금지) ──
def test_missing_ganji_kept() -> None:
    gbp = {"y1": "壬子"}  # y2.. 누락
    rows = adjusted_rank_experiment(
        calculate(_STD), _cands((90, 80, 70, 60, 50)), gbp, _LEVEL, components=_AB)
    assert len(rows) == 5  # 후보 수 보존(missing 제거 안 함)
    assert any(r["missing_ganji"] for r in rows)


# ── 불변: favorability/final 미변경 ──
def test_invariance() -> None:
    chart = calculate(_STD)
    fav, final = favorability_map(chart), dict(chart.yongsin_analysis.final)
    adjusted_rank_experiment(chart, _cands((90, 80, 70, 60, 50)), _GBP, _LEVEL,
                             components=_AB)
    assert favorability_map(chart) == fav
    assert dict(chart.yongsin_analysis.final) == final

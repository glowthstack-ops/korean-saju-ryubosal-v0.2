"""Shadow Validation Harness 리포트 빌더(shadow_report.py) — 검증 도구·운영 미연결.

build_shadow_report 행 구조·guard 플래그·불변(Guard #6)·missing ganji skip 을 표준 operational
차트(丁巳/壬子/丁未/癸卯)로 고정한다. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §13
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart

from saju_engines.shadow_report import (
    REPORT_COLUMNS,
    build_shadow_report,
    invariance_snapshot,
)
from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
# period → 운 간지(오행 대표): 水 火 木 土 金
_GBP = {"W": "壬子", "F": "丙午", "M": "甲寅", "E": "戊辰", "G": "庚申"}
_LEVEL = dict.fromkeys(_GBP, "year")


def _result(make_pillars):
    return SimpleNamespace(yongsin_analysis=analyze_chart(make_pillars(*_STD)).yongsin)


def _cands(score=70):
    return [SimpleNamespace(period=p, score=score, event_key=f"e_{p}",
                            polarity="positive") for p in _GBP]


def _build(make_pillars, score=70, gbp=None):
    res = _result(make_pillars)
    return build_shadow_report(
        res, _cands(score), gbp if gbp is not None else _GBP,
        chart_id="t", period_level=_LEVEL,
    )


def _by_period(rows):
    return {r["period"]: r for r in rows}


def test_row_schema_and_levels(make_pillars) -> None:
    rows, summary = _build(make_pillars)
    assert len(rows) == 5 and summary["rows"] == 5 and summary["missing_ganji"] == 0
    for r in rows:
        assert set(r) == set(REPORT_COLUMNS)  # 모든 컬럼 존재
        assert r["level"] == "year"
        assert r["chart_id"] == "t"
    assert _by_period(rows)["W"]["ganji"] == "壬子"


# ── 레벨별 랭킹: YEAR/DAEWOON 혼합 시 전역은 크게 흔들려도 레벨 내부는 레벨 기준 ──
def test_level_aware_ranking(make_pillars) -> None:
    res = _result(make_pillars)
    # 동일 ganji 풀을 YEAR 5 + DAEWOON 5 로 복제(레벨만 다름).
    gbp = {f"Y_{p}": g for p, g in _GBP.items()} | {f"D_{p}": g for p, g in _GBP.items()}
    level = ({k: "year" for k in gbp if k.startswith("Y_")}
             | {k: "daewoon" for k in gbp if k.startswith("D_")})
    # 세운은 고득점, 대운은 저득점 — 전역 풀이면 대운이 늘 하위(섞임 착시).
    cands = ([SimpleNamespace(period=f"Y_{p}", score=80, event_key="y", polarity="x")
              for p in _GBP]
             + [SimpleNamespace(period=f"D_{p}", score=40, event_key="d", polarity="x")
                for p in _GBP])
    rows, _ = build_shadow_report(res, cands, gbp, chart_id="t", period_level=level)
    # 레벨별 순위는 레벨 내부(1~5), 전역은 1~10 범위.
    for r in rows:
        assert 1 <= r["legacy_rank_level"] <= 5
        assert 1 <= r["legacy_rank_global"] <= 10
    year_rows = [r for r in rows if r["level"] == "year"]
    dw_rows = [r for r in rows if r["level"] == "daewoon"]
    # 세운(고득점)은 전역에서도 상위 1~5, 레벨에서도 1~5.
    for r in year_rows:
        assert r["legacy_rank_global"] <= 5
    # 대운(저득점)은 전역에선 6~10으로 밀리지만 레벨 내부 기준이면 1~5 → 착시 제거.
    for r in dw_rows:
        assert r["legacy_rank_global"] >= 6
        assert r["legacy_rank_level"] < r["legacy_rank_global"]


def test_operational_summary_present(make_pillars) -> None:
    rows, _ = _build(make_pillars)
    r = rows[0]
    assert "火:조후보조신" in r["operational_roles"]      # 조후보조신 라벨
    assert "조건부 한신/병" in r["operational_roles"]      # 水 조건부(희신 과다 교정 후)
    assert "op=0.595" in r["operability_factors"]         # 용신 木 작동성


# ── Guard #1: 조건부 한신/병(水) positive 작동 금지 → fav_delta ≤ 0 ──
# (희신 과다 교정 후 legacy=한신 0.0 — 승격 없이 중립 유지, 서술 가드는 5b-1이 담당)
def test_guard1_conditional_heesin_not_positive(make_pillars) -> None:
    rows = _by_period(_build(make_pillars)[0])
    assert rows["W"]["fav_delta"] <= 0
    assert rows["W"]["expression_class"] == "중립"


# ── Guard #3: operability 낮은 용신운(木 0.595) 과대평가 금지 → shadow_fav ≤ legacy_fav ──
def test_guard3_low_operability_not_overvalued(make_pillars) -> None:
    r = _by_period(_build(make_pillars)[0])["M"]
    assert r["shadow_fav"] <= r["legacy_fav"] and r["fav_delta"] <= 0


# ── rank WARN 임계 상대화: 작은 풀 abs=3 유지 / 큰 풀 ratio 적용 ──
def test_rank_warn_threshold_scales_with_pool(make_pillars) -> None:
    res = _result(make_pillars)
    # 작은 풀(5) → max(3, ceil(5×0.05))=max(3,1)=3
    small, _ = _build(make_pillars)
    assert all(r["level_pool_size"] == 5 for r in small)
    assert all(r["rank_warn_threshold"] == 3 for r in small)
    # 큰 풀(100, year) → max(3, ceil(100×0.05))=max(3,5)=5
    n = 100
    gbp = {f"P{i}": "壬子" for i in range(n)}
    level = dict.fromkeys(gbp, "year")
    cands = [SimpleNamespace(period=f"P{i}", score=50 + (i % 30),
                             event_key="e", polarity="x") for i in range(n)]
    rows, _ = build_shadow_report(res, cands, gbp, chart_id="t", period_level=level)
    assert all(r["level_pool_size"] == n for r in rows)
    assert all(r["rank_warn_threshold"] == 5 for r in rows)       # ratio 적용
    assert all("rank_delta_pct" in r for r in rows)               # 해석 필드
    # 큰 풀에서 |rank_delta_level| < 5 인 잔흔은 WARN 에서 빠진다.
    minor = [r for r in rows if 0 < abs(r["rank_delta_level"]) < 5]
    assert all("rank_delta" not in r["warns"] for r in minor)


# ── Guard #5: abs(score_delta) ≥ 18 → score WARN 플래그 ──
# (희신 과다 교정 후 水 delta=0 — 큰 delta 는 土 완화 상향 +0.7×30=+21 이 담당)
def test_guard5_warn_flagging(make_pillars) -> None:
    rows, summary = _build(make_pillars, score=70)
    e = _by_period(rows)["E"]
    assert e["score_delta"] == 21 and "score_delta" in e["warns"]  # 土: +0.7×30
    assert summary["warn_score_delta"] >= 1


# ── Guard #6: build 전후 불변 스냅샷 동일(운영값 미변경) ──
def test_guard6_invariance(make_pillars) -> None:
    res = _result(make_pillars)
    cands = _cands()
    before = invariance_snapshot(res, cands)
    build_shadow_report(res, cands, _GBP, chart_id="t", period_level=_LEVEL)
    after = invariance_snapshot(res, cands)
    assert before == after


# ── missing ganji: 후보 period 가 ganji 맵에 없으면 skip + 집계 ──
def test_missing_ganji_skipped_counted(make_pillars) -> None:
    gbp = {"W": "壬子"}  # F/M/E/G 누락
    rows, summary = _build(make_pillars, gbp=gbp)
    assert summary["rows"] == 1 and summary["missing_ganji"] == 4
    assert summary["errors"] == []  # 일부만 skip


def test_all_skipped_is_error(make_pillars) -> None:
    rows, summary = _build(make_pillars, gbp={})  # 전부 누락
    assert rows == [] and summary["errors"] == ["all_candidates_skipped"]

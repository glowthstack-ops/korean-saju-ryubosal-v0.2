"""후보 단위 operational shadow 관찰 (#9b) — 미소비.

candidate.score(발생 가능성) 불변. 운 간지 오행의 legacy vs shadow 유불리 차(fav_delta) +
관찰용 결합값(shadow_observation_score) + 가상 순위 변화만 산출. 실제 랭킹·favorability·final 불변.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.operational_role_config import SHADOW_SCORE_SPAN

from saju_engines.event_scoring import favorability_map
from saju_engines.shadow_scoring import candidate_shadow_diff, shadow_rank_diff
from saju_shared_types.enums import Branch, Stem

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)
# period → 운 간지(오행 대표): 水 火 木 土 金
_GBP = {"W": "壬子", "F": "丙午", "M": "甲寅", "E": "戊辰", "G": "庚申"}


def _diffs(make_pillars, score=70):
    res = SimpleNamespace(yongsin_analysis=analyze_chart(make_pillars(*_STD)).yongsin)
    cands = [SimpleNamespace(period=p, score=score, event_key="x") for p in _GBP]
    return candidate_shadow_diff(res, cands, _GBP)  # type: ignore[arg-type]


def _by_period(diffs):
    return {d["period"]: d for d in diffs}


def test_golden_fav_delta_directions(make_pillars) -> None:
    # 희신 과다 교정(2026-07-12) 후 legacy(final)=모델맵 — delta 방향도 그에 맞춰 갱신.
    d = _by_period(_diffs(make_pillars))
    assert d["W"]["fav_delta"] == 0.0      # 水 한신 → 조건부 한신/병 (가중 동일 0)
    assert d["F"]["fav_delta"] == -0.25    # 火 희신 → 조후보조신 (보조약 하향)
    assert d["M"]["fav_delta"] == -0.405   # 木 용신 operability 0.595 (하향)
    assert d["E"]["fav_delta"] == 0.7      # 土 구신 → 조건부 제살보조 (완화)
    assert d["G"]["fav_delta"] == 0.0      # 金 기신 유지 (불변)


def test_observation_score_combination(make_pillars) -> None:
    d = _by_period(_diffs(make_pillars, score=70))
    # 관찰용 결합 = clamp(score + fav_delta × SPAN). 실제 score 아님.
    expected = max(0, min(100, round(70 - 0.25 * SHADOW_SCORE_SPAN)))
    assert d["F"]["shadow_observation_score"] == expected
    assert d["W"]["legacy_score"] == 70                  # legacy 불변
    assert d["W"]["shadow_observation_score"] == 70      # 水 가중 동일(0) — 불변
    assert d["E"]["shadow_observation_score"] > 70       # 土 완화 상향
    assert d["G"]["shadow_observation_score"] == 70      # 金 불변


def test_reason_role_change_and_operability(make_pillars) -> None:
    d = _by_period(_diffs(make_pillars))
    # reason 은 '가중이 바뀐 것'만 기록 — 水(한신→조건부 한신/병)는 가중 동일(0)이라 미기록,
    # 火(희신→조후보조신)가 라벨 변경 reason 을 담는다.
    assert d["W"]["reason"] == []
    assert any("조후보조신" in r for r in d["F"]["reason"])       # 라벨 변경
    assert any("작동성 0.595" in r for r in d["M"]["reason"])     # 용신 operability
    assert d["G"]["reason"] == []                                # 변화 없음
    assert all(len(x["reason"]) <= 3 for x in d.values())        # reason ≤3


def test_conditional_heesin_lowers_not_positive(make_pillars) -> None:
    # 조건부 한신/병(水)은 어떤 경우에도 positive 로 승격되지 않는다(0 이하).
    assert _by_period(_diffs(make_pillars))["W"]["fav_delta"] <= 0


def test_rank_observation_only(make_pillars) -> None:
    ranks = shadow_rank_diff(_diffs(make_pillars))
    keys = set(ranks[0])
    assert {"period", "legacy_rank", "shadow_rank", "rank_delta", "rank_changed"} <= keys
    # 동일 legacy score인데 shadow로 순위가 갈린다(土 상향·水 하향).
    by = {r["period"]: r for r in ranks}
    assert by["E"]["shadow_rank"] < by["W"]["shadow_rank"]
    assert any(r["rank_changed"] for r in ranks)


def test_missing_ganji_skipped(make_pillars) -> None:
    res = SimpleNamespace(yongsin_analysis=analyze_chart(make_pillars(*_STD)).yongsin)
    cands = [SimpleNamespace(period="UNKNOWN", score=70, event_key="x")]
    assert candidate_shadow_diff(res, cands, {}) == []  # type: ignore[arg-type]


def test_legacy_favorability_unchanged(make_pillars) -> None:
    ya = analyze_chart(make_pillars(*_STD)).yongsin
    fav = favorability_map(SimpleNamespace(yongsin_analysis=ya))  # type: ignore[arg-type]
    assert fav.get("水") == "한신" and fav.get("火") == "희신"  # canonical(교정 후) 그대로

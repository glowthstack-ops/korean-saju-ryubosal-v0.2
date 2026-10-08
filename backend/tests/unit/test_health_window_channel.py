"""C5 건강 채널(2026-10-07 데굴님 승인) — 창 점수 파생 후보·개인 분위수·관리자 코드.

사례집 CASE-010/L(1960-09-14 甲申시, 2010 庚寅년): 전문가 해설과 같은 글자(寅申충·乙庚합×2)로
건강 창 100. 플래그 ON 이면 2010 health_attention 이 1위이고 reason_codes 에 창 근거·코드가
실린다. OFF 면 기존 동작.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import period_v2_config as cfg
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.event_scoring import favorability_map
from saju_engines.health_vulnerability import (
    analyze_health_vulnerability,
    health_percentile_thresholds,
    lifetime_health_scores,
    percentile_level,
    severe_event_code,
)
from saju_engines.health_window_channel import inject_health_window_candidates
from saju_engines.lifetime_scan import lifetime_pillars, merge_yearly_luck
from saju_engines.structural_context import health_lines
from saju_shared_types.birth_input import BirthInput, TimeCalculationOptions
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.health_vulnerability import HealthRiskWindow

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _case_010_l(reference_year: int | None = None):
    kw = {"reference_date": date(reference_year, 6, 1)} if reference_year else {}
    return calculate(BirthInput(
        calendar_type="solar", birth_date="1960-09-14", birth_time="16:30",
        birth_place_name="서울", gender="male",
        time_options=TimeCalculationOptions(apply_daylight_saving=False), **kw,
    ))


def _lifetime(result):
    by = 1960
    dw, _ = lifetime_pillars(result, by, by + 100)
    return merge_yearly_luck(result, list(dw))


def test_health_window_candidate_ranks_first_in_event_year(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "HEALTH_WINDOW_CHANNEL_ENABLED", True)
    lt = _lifetime(_case_010_l())
    scored = EventEngineV2(_DICTS).score(lt, levels={GanjiLevel.YEAR})
    cands = [c for c in scored if c.period == "2010"]
    cands.sort(key=lambda c: -c.score)
    assert cands and cands[0].event_key == EventKeyV2.HEALTH_ATTENTION
    assert cands[0].score >= 90
    assert any(r.startswith("HEALTH_WINDOW:천극지충") for r in cands[0].reason_codes)
    assert "HEALTH_CODE:F-1" in cands[0].reason_codes
    # 같은 해 health_attention 후보는 하나만(규칙 후보 치환).
    assert sum(1 for c in cands if c.event_key == EventKeyV2.HEALTH_ATTENTION) == 1


def test_flag_off_keeps_legacy_candidates(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "HEALTH_WINDOW_CHANNEL_ENABLED", False)
    lt = _lifetime(_case_010_l())
    cands = EventEngineV2(_DICTS).score(lt, levels={GanjiLevel.YEAR})
    assert not any("HEALTH_WINDOW:" in r for c in cands for r in c.reason_codes)


def test_inject_replaces_only_year_level_health() -> None:
    lt = _lifetime(_case_010_l())
    base = EventEngineV2(_DICTS).score(lt, levels={GanjiLevel.YEAR})
    out = inject_health_window_candidates(lt, base)
    non_health_before = [c for c in base if c.event_key != EventKeyV2.HEALTH_ATTENTION]
    non_health_after = [c for c in out if c.event_key != EventKeyV2.HEALTH_ATTENTION]
    assert len(non_health_before) == len(non_health_after)  # 다른 도메인 후보 불변
    assert all(c.period.isdigit() for c in out if "HEALTH_WINDOW:" in " ".join(c.reason_codes))


def test_percentile_levels_and_code_trigger() -> None:
    r = _case_010_l()
    hv = analyze_health_vulnerability(r, favorability_map(r))
    scores = lifetime_health_scores(r, hv)
    th = health_percentile_thresholds(scores)
    assert set(th) == {"p85", "p93", "p97"} and th["p85"] <= th["p93"] <= th["p97"]
    w2010 = scores[2010]
    assert w2010.score == 100
    assert percentile_level(w2010.score, th) == "적극 관리·검진 권장"
    assert severe_event_code(w2010, th) == "F-1"
    # 중첩·근거 없는 창은 코드가 붙지 않는다.
    plain = HealthRiskWindow(
        period="2010", daewoon="", score=100, level="x", reasons=["과다 기신 반복"],
    )
    assert severe_event_code(plain, th) is None
    assert percentile_level(5, th) is None


def test_health_lines_render_code_without_meaning() -> None:
    r = _case_010_l(2010)
    hv = analyze_health_vulnerability(r, favorability_map(r))
    lines = health_lines(r, hv, 2008)
    coded = [ln for ln in lines if "코드 F-1에 해당하는 사건" in ln]
    assert coded and any("2010년" in ln for ln in coded)
    joined = "\n".join(lines)
    # 가드 문구 자체의 금지어 언급은 제외하고, 본문에 금지 어휘가 없어야 한다.
    scrubbed = (
        joined.replace("질병·사망 예측 아님", "")
        .replace("질병명·수명·사망은 절대", "")
        .replace("사망·사고·수명 어휘", "")
    )
    for banned in ("사망", "생명 위협", "급변"):
        assert banned not in scrubbed


@pytest.mark.parametrize("year", [1994])
def test_below_personal_percentile_is_candidate_but_not_exposed(year: int) -> None:
    # CASE-036/R(1949-07-02 07:00+2h 보정): 1994 창 49 — 후보(≥30)이지만 본인 p85(57) 미만이라
    # 비노출.
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1949-07-02", birth_time="09:00",
        birth_place_name="서울", gender="male", reference_date=date(year, 6, 1),
    ))
    hv = analyze_health_vulnerability(r, favorability_map(r))
    th = health_percentile_thresholds(lifetime_health_scores(r, hv))
    scores = lifetime_health_scores(r, hv)
    w = scores.get(year)
    assert w is not None and w.score >= 30
    assert percentile_level(w.score, th) is None


def test_accident_case_gets_f2_not_f1() -> None:
    """CASE-034/L(1981-06-12 10:00, 2004 甲申 오토바이 사고): 손상 장기 재공격·중첩이지만 일간 직접
    타격(천극지충·일간 입묘)이 없어 F-1 이 아니라 F-2 — 데굴님 확정(2026-10-07)."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1981-06-12", birth_time="10:00",
        birth_place_name="서울", gender="male",
    ))
    hv = analyze_health_vulnerability(r, favorability_map(r))
    scores = lifetime_health_scores(r, hv)
    th = health_percentile_thresholds(scores)
    w = scores[2004]
    assert w.score >= th["p93"]
    assert "천극지충" not in w.reasons and "일간 입묘" not in w.reasons
    assert severe_event_code(w, th) == "F-2"


def test_monthly_candidates_follow_flagged_year(monkeypatch) -> None:
    """월 단위(데굴님 지시): 2010 이 본인 p85 이상인 010/L 에서 2010 월운 창 ≥30 인 달에 월 후보가
    생기고, 기존 규칙 월 후보는 치환된다. 다른 도메인 월 후보는 불변."""
    monkeypatch.setattr(cfg, "HEALTH_WINDOW_CHANNEL_ENABLED", True)
    r = _case_010_l(2010)  # reference_date=2010 → monthly_luck 이 2010년 12개월
    assert r.luck_cycles is not None and len(r.luck_cycles.monthly_luck) >= 12
    eng = EventEngineV2(_DICTS)
    base = eng.score(r, levels={GanjiLevel.MONTH})
    monkeypatch.setattr(cfg, "HEALTH_WINDOW_CHANNEL_ENABLED", False)
    legacy = eng.score(r, levels={GanjiLevel.MONTH})
    month_health = [
        c for c in base if c.event_key == EventKeyV2.HEALTH_ATTENTION and len(c.period) == 7
    ]
    assert month_health, "월 후보가 하나는 있어야 한다(2010 은 p85 이상)"
    assert all("HEALTH_WINDOW:월 단위" in c.reason_codes for c in month_health)
    others_base = sorted((c.period, c.event_key, c.score) for c in base
                         if c.event_key != EventKeyV2.HEALTH_ATTENTION)
    others_legacy = sorted((c.period, c.event_key, c.score) for c in legacy
                           if c.event_key != EventKeyV2.HEALTH_ATTENTION)
    assert others_base == others_legacy

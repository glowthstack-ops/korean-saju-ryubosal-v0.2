"""외부 교재 대조 P2(2026-10-15 데굴님 '권고대로').

궁합 보완 2신호·여명 부성 대체 설명층·이중 충 표지·사생지 충 보조."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import period_v2_config
from saju_engines.compatibility_engine import _element_season_signals, analyze_compatibility
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_engines.structural_context import marriage_resource_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatDirection, CompatSignalKind
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_WINTER_M = BirthInput(  # 1980-11-22 亥월(겨울)
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_SUMMER_M = BirthInput(  # 1985-05-20 巳월(여름)
    birth_date=date(1985, 5, 20), birth_time="10:00:00", birth_place_name="서울", gender="male",
)
_WINTER_F = BirthInput(  # 1975-01-01 丑월(겨울)
    birth_date=date(1975, 1, 1), birth_time="07:30:00", birth_place_name="서울", gender="female",
)


def _useful(result):
    from saju_engines.event_scoring import favorability_map
    from saju_shared_types.llm_input import UsefulGods

    fav = favorability_map(result)
    by = {}
    for el, role in fav.items():
        by.setdefault(role, []).append(el)
    return UsefulGods(
        yongsin=by.get("용신", []), heesin=by.get("희신", []), gisin=by.get("기신", []),
        gusin=by.get("구신", []), hansin=by.get("한신", []),
    )


# ── P2-1 궁합 ──

def test_season_complement_summer_vs_winter_and_same_season_aux() -> None:
    w, s = calculate(_WINTER_M), calculate(_SUMMER_M)
    sig = _element_season_signals(w, s)
    season = [x for x in sig if x.kind is CompatSignalKind.SEASON_COMPLEMENT]
    assert season and season[0].direction is CompatDirection.HARMONY
    assert "겨울생 ↔ 상대 여름생" in season[0].detail
    w2 = calculate(_WINTER_F)
    same = [
        x for x in _element_season_signals(w, w2) if x.kind is CompatSignalKind.SEASON_COMPLEMENT
    ]
    assert same and same[0].auxiliary and same[0].direction is CompatDirection.NEUTRAL


def test_element_complement_follows_percent_rule_and_is_in_report() -> None:
    w, s = calculate(_WINTER_M), calculate(_SUMMER_M)
    sig = [
        x for x in _element_season_signals(w, s) if x.kind is CompatSignalKind.ELEMENT_COMPLEMENT
    ]
    wp = w.force_analysis.five_elements.effective_percent
    sp = s.force_analysis.five_elements.effective_percent
    expect = sum(1 for el in "木火土金水" if wp.get(el, 0) < 5 and sp.get(el, 0) >= 20) + sum(
        1 for el in "木火土金水" if sp.get(el, 0) < 5 and wp.get(el, 0) >= 20)
    assert len(sig) == expect
    report = analyze_compatibility(w, s, _useful(w), _useful(s))
    assert report is not None
    kinds = {x.kind for x in report.signals}
    assert CompatSignalKind.SEASON_COMPLEMENT in kinds


# ── P2-4 부성 대체 ──

def test_spouse_star_substitute_only_for_female_and_rule_consistent() -> None:
    m = analyze_marriage_resource(calculate(_WINTER_M))
    assert m.spouse_star_substitute is None
    r = calculate(_WINTER_F)
    f = analyze_marriage_resource(r)
    groups = r.force_analysis.ten_gods.groups
    officer = float(groups.get("officer", 0.0))
    if officer >= 30:
        assert f.spouse_star_substitute == "인성"
    elif f.spouse_star_absent or officer < 8:
        assert f.spouse_star_substitute == "재성"
    if f.spouse_star_substitute:
        assert f.spouse_star_substitute_basis
        assert any(line.startswith("부성 대체 후보") for line in marriage_resource_lines(f))
    else:
        assert not any(line.startswith("부성 대체 후보") for line in marriage_resource_lines(f))


# ── P2-5 이중 충·사생지 충 ──

def _months(birth, year, **kw):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    assert c2.luck_cycles is not None
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    return build_event_engine_v2(_DICTS, **kw).score(c2, levels={GanjiLevel.MONTH})


def test_double_clash_flag_only_changes_favorability_on_restruck_branch() -> None:
    """1980 명식 원국 巳亥충(월지 亥·시지 巳): 운 지지가 亥·巳를 다시 충하는 달에만 표지."""
    assert period_v2_config.DOUBLE_CLASH_FLAG_ENABLED is True
    on = _months(_WINTER_M, 2026)
    flagged = [c for c in on if any(r.startswith("沖_이중충_") for r in c.reason_codes)]
    assert flagged, "2026년 안에 巳 또는 亥 월운이 있어 이중 충 달이 있어야 한다"
    assert all(len(c.period) == 7 for c in flagged)
    # 점수·사건 종류는 불변 — 같은 달의 OFF 와 비교.
    period_v2_config.DOUBLE_CLASH_FLAG_ENABLED = False
    try:
        off = _months(_WINTER_M, 2026)
    finally:
        period_v2_config.DOUBLE_CLASH_FLAG_ENABLED = True
    on_map = {(c.event_key, c.period): c for c in on}
    for c in off:
        o = on_map[(c.event_key, c.period)]
        assert o.score == c.score
        if any(r.startswith("沖_이중충_") for r in o.reason_codes):
            # fav_adj 는 뒤 모디파이어(시험 결과 등)가 덮어쓸 수 있어 적용 기록 키로 확인한다.
            expected = -period_v2_config.STRUCTURE_PILLAR_PENALTY / 2
            assert o.contributions.get("double_clash") == expected
            assert "double_clash" not in c.contributions


def test_life_branch_clash_amplifier_registered() -> None:
    d = json.loads((_DICTS / "risk_auxiliary_amplifiers.json").read_text("utf-8"))
    it = next(x for x in d["items"] if x["id"] == "AUX_HLT_LIFE_BRANCH_CLASH")
    assert it["structureIn"] == ["life_branch_clash"] and it["strength"] <= 0.3
    assert "단정" not in it["labelKo"] and "사망" not in it["labelKo"]

"""비겁 용신 × 비겁 운 유입 → 직장·역할 이동 시드 (2026-10-14 데굴님 확정 규칙) 회귀 고정.

실사례: 1980-11-22 09:40 서울 남 — 용신 土(비겁), 2026-10 戊戌월(천간·지지 모두 겁재 = 운
간여지동)에 권고사직. 수정 전 엔진은 그 달 career_change 후보가 없었고 '강한 용신운 · 재물 변화
우세'로 읽었다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import period_v2_config
from saju_engines.chart_interpretation import incoming_ten_god_note
from saju_engines.dictionaries import PeerMobilityTextFile, _lint_peer_mobility_text
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.event_lexicon import derive_process_types
from saju_engines.event_scoring import favorability_map
from saju_engines.peer_mobility_seed import classify_inflow, load_peer_mobility_rule
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_CASE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
# 1990-03-03 07:30 서울 여 — 丁 일간, 비겁 오행 火=한신(용신 아님) — 음성 대조군.
_CONTROL = BirthInput(
    birth_date=date(1990, 3, 3), birth_time="07:30:00", birth_place_name="서울", gender="female",
)


def _month_candidates(birth: BirthInput, year: int, **overrides):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    return build_event_engine_v2(_DICTS, **overrides).score(c2, levels={GanjiLevel.MONTH})


def test_rule_loaded_from_dictionary():
    rule = load_peer_mobility_rule(_DICTS)
    assert rule is not None and rule.rule_id == "PEER_YONGSIN_MOBILITY"
    assert rule.base_by_inflow["same_god"] > rule.base_by_inflow["same_group"]
    assert rule.base_by_inflow["same_group"] > rule.base_by_inflow["stem_only"]
    assert rule.base_by_inflow["stem_only"] > rule.base_by_inflow["branch_only"]
    assert rule.base_by_inflow["same_god"] >= rule.event_candidate_threshold


def test_case_chart_yongsin_is_peer_element():
    fm = favorability_map(calculate(_CASE))
    assert fm.get("土") == "용신"  # 己 일간 — 비겁 오행 土가 용신


def test_october_2026_gets_career_change_with_same_god_inflow():
    """戊戌월(겁재 간여지동) — 수정 전엔 없던 career_change 후보가 가장 강한 유입 등급으로."""
    cands = [c for c in _month_candidates(_CASE, 2026) if c.period == "2026-10"]
    career = [c for c in cands if str(c.event_key) == "career_change"]
    assert career, sorted({str(c.event_key) for c in cands})
    c = career[0]
    assert "PEER_YONGSIN_MOBILITY" in c.reason_codes
    assert "PEER_INFLOW_SAME_GOD" in c.reason_codes
    assert c.score >= 55  # 6계층 보정 뒤에도 event_candidate 문턱 유지(용신운이라 깎이지 않는다)
    assert "이동·교체·재편" in derive_process_types(
        "career_change", c.reason_codes, [], c.favorability, dictionaries_dir=_DICTS,
    )


def test_weak_inflow_month_gets_lower_tier():
    """己亥월(천간 己 비견만) — 후보는 만들되 약한 유입 등급."""
    cands = [c for c in _month_candidates(_CASE, 2026) if c.period == "2026-11"]
    career = [c for c in cands if str(c.event_key) == "career_change"]
    assert career and "PEER_INFLOW_STEM" in career[0].reason_codes
    assert "PEER_INFLOW_SAME_GOD" not in career[0].reason_codes


def test_month_without_peer_inflow_has_no_seed():
    """丙申월(편인·상관) — 비겁 유입이 없으면 시드 코드가 붙지 않는다."""
    cands = [c for c in _month_candidates(_CASE, 2026) if c.period == "2026-08"]
    assert not any("PEER_YONGSIN_MOBILITY" in c.reason_codes for c in cands)


def test_no_seed_when_peer_element_is_not_yongsin():
    fm = favorability_map(calculate(_CONTROL))
    assert fm.get("火") != "용신"
    cands = _month_candidates(_CONTROL, 2026)
    assert not any("PEER_YONGSIN_MOBILITY" in c.reason_codes for c in cands)


def test_flag_off_restores_previous_output():
    cands = [
        c for c in _month_candidates(_CASE, 2026, enable_peer_mobility=False)
        if c.period == "2026-10"
    ]
    assert not any(str(c.event_key) == "career_change" for c in cands)


def test_config_flag_defaults_on(monkeypatch):
    assert period_v2_config.PEER_YONGSIN_MOBILITY_ENABLED is True
    monkeypatch.setattr(period_v2_config, "PEER_YONGSIN_MOBILITY_ENABLED", False)
    cands = [c for c in _month_candidates(_CASE, 2026) if c.period == "2026-10"]
    assert not any(str(c.event_key) == "career_change" for c in cands)


@pytest.mark.parametrize(
    ("ganji", "same_pillar", "mobility", "weak"),
    [
        ("戊戌", True, True, False),   # 겁재 간여지동 — 강한 유입
        ("己亥", False, True, True),   # 비견 천간만 — 약한 유입(관성 충 등 다른 작용 안내)
        ("丙申", False, False, False),  # 비겁 아님
        ("丙午", False, False, False),  # 丙 정인·午 편인 — 같은 군이나 십성이 다르면 간여지동 아님
    ],
)
def test_incoming_note_marks_same_pillar_and_mobility(ganji, same_pillar, mobility, weak):
    note = incoming_ten_god_note("己", ganji, {"土": "용신", "火": "희신"})
    assert ("운 간여지동" in note) is same_pillar
    assert ("직장·역할의 이동이 걸릴 수 있다" in note) is mobility
    assert ("한쪽으로만 들어와" in note) is weak


def test_note_silent_when_peer_is_neither_yongsin_nor_gisin():
    """한신·희신·구신 비겁은 이동 문구 없음(용신·기신만 — 기신 대칭 2026-10-15)."""
    for role in ("한신", "희신", "구신"):
        note = incoming_ten_god_note("己", "戊戌", {"土": role})
        assert "운 간여지동" in note and "직장·역할의 이동" not in note, role


def test_classify_inflow_order():
    from saju_engines.ten_god_brancher import TransitSignal
    from saju_shared_types.event_engine import LuckLayer, TenGod

    w = LuckLayer.WOLWOON
    assert classify_inflow([]) is None
    assert classify_inflow([TransitSignal(TenGod.JIECAI, w, "branch_main")]) == "branch_only"
    assert classify_inflow([TransitSignal(TenGod.BIJIAN, w, "stem")]) == "stem_only"
    assert classify_inflow([
        TransitSignal(TenGod.BIJIAN, w, "stem", same_group=True),
        TransitSignal(TenGod.JIECAI, w, "branch_main", same_group=True),
    ]) == "same_group"
    assert classify_inflow([
        TransitSignal(TenGod.JIECAI, w, "stem", same_group=True, same_god=True),
    ]) == "same_god"


def test_text_dictionary_valid_and_linted():
    import json

    data = json.loads(
        (_DICTS / "interpretations" / "transit_peer_mobility_text.json").read_text("utf-8")
    )
    parsed = PeerMobilityTextFile.model_validate(data)
    assert _lint_peer_mobility_text(parsed) == []


# ── 기신 대칭 시드(2026-10-15 데굴님 확정) ───────────────────────────────────

# 1985-05-20 10:00 서울 남 — 己未 일주, 비겁 오행 土=기신. 2026-10 戊戌월은 겁재·겁재(운 간여지동)로
# 실사례(용신 土)와 같은 달·같은 유입 강도라 대칭 비교에 적합하다.
_GISIN_CASE = BirthInput(
    birth_date=date(1985, 5, 20), birth_time="10:00:00", birth_place_name="서울", gender="male",
)


def test_gisin_rule_loads_as_mirror_of_yongsin_rule():
    from saju_engines.peer_mobility_seed import GISIN_SECTION

    y = load_peer_mobility_rule(_DICTS)
    g = load_peer_mobility_rule(_DICTS, GISIN_SECTION)
    assert y is not None and g is not None
    assert g.rule_id == "PEER_GISIN_MOBILITY" and g.favorability_any == {"기신"}
    assert g.base_by_inflow == y.base_by_inflow and g.layers == y.layers and g.event is y.event


def test_gisin_chart_gets_mobility_seed_with_pressure_quality():
    fm = favorability_map(calculate(_GISIN_CASE))
    assert fm.get("土") == "기신"
    cands = _month_candidates(_GISIN_CASE, 2026)
    cc = [c for c in cands if c.period == "2026-10" and c.event_key.value == "career_change"]
    assert cc, "2026-10 戊戌(겁재·겁재)에 이동 시드가 있어야 한다"
    c = cc[0]
    assert "PEER_GISIN_MOBILITY" in c.reason_codes and "PEER_INFLOW_SAME_GOD" in c.reason_codes
    assert "PEER_YONGSIN_MOBILITY" not in c.reason_codes
    assert c.quality is not None and c.quality.value in ("pressure", "loss", "conflict", "mixed")


def test_gisin_seed_absent_when_flag_off_and_on_yongsin_chart():
    off = _month_candidates(_GISIN_CASE, 2026, enable_peer_gisin_mobility=False)
    assert not [
        c for c in off if c.period == "2026-10" and "PEER_GISIN_MOBILITY" in c.reason_codes
    ]
    # 용신 명식(실사례)에는 기신 시드가 붙지 않는다.
    y = _month_candidates(_CASE, 2026)
    assert not [c for c in y if "PEER_GISIN_MOBILITY" in c.reason_codes]
    assert [c for c in y if "PEER_YONGSIN_MOBILITY" in c.reason_codes]


def test_incoming_note_uses_gisin_text_for_gisin_chart():
    r = calculate(_GISIN_CASE)
    fm = favorability_map(r)
    note = incoming_ten_god_note(r.pillars.day_master, "戊戌", fm)
    assert "비겁이 기신인 명식" in note and "비겁이 용신인 명식" not in note
    assert "운 간여지동" in note

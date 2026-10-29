"""외부 강의 「직장을 그만두거나 이직해야 할 때」 번역층 회귀 고정 (2026-10-29 데굴님 결정).

점수층(`career_exit_seed`, 플래그 기본 OFF — 85사례·생애 원장 적중률로 ON)과 문구층(항상 노출)을
함께 고정한다. 픽스처는 2026년 월운에서 조건이 성립하는 명식을 탐색해 잡았다(2026-10-29).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate, luck_months
from saju_engines.career_exit_seed import (
    CareerExitConfig,
    load_career_exit_config,
    natal_all_ten_gods,
    natal_stem_ten_gods,
    produce_career_exit_seeds,
)
from saju_engines.career_field import build_career_field_facts, render_career_field_lines
from saju_engines.chart_interpretation import career_exit_lecture_block, incoming_ten_god_note
from saju_engines.dictionaries import CareerExitTextFile, _lint_career_exit_text
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.event_scoring import favorability_map
from saju_engines.ten_god_brancher import TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2, LuckLayer, TenGod
from saju_shared_types.event_taxonomy_v2 import EVENT_KO, EVENT_WORDS
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth(d: str, g: str = "male") -> BirthInput:
    return BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울", gender=g,
    )


# 원국 천간 정관 + 2026-06 甲午(상관 천간), 원국 정인 없음 → 환경형(구응 없음).
_ENV = _birth("1978-03-02")
# 원국 천간 정관 + 2026-02 庚寅(상관 천간), 원국 정인 있음 → 환경형 + 구응 감쇠.
_ENV_RESCUE = _birth("1979-01-02")
# 원국 천간 상관 + 2026-03 辛卯(정관 천간) → 자기형. 같은 명식: 2026-07 乙未(겁재 천간, 비겁 구신)
# → 역할 무관 겁재 시드, 2026-04 壬辰(편인 천간) → 휴직 시드.
_SELF = _birth("1978-01-02")


def _month_candidates(birth: BirthInput, period: str, **overrides):
    year = int(period[:4])
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    cands = build_event_engine_v2(_DICTS, **overrides).score(c2, levels={GanjiLevel.MONTH})
    return [c for c in cands if c.period == period]


def _codes(cands, event: str) -> set[str]:
    return {code for c in cands if str(c.event_key) == event for code in c.reason_codes}


def test_config_loads_four_rules_from_dictionary() -> None:
    cfg = load_career_exit_config(_DICTS)
    assert cfg is not None and cfg.section_id == "CAREER_EXIT_LECTURE"
    assert [r.rule_id for r in cfg.rules] == [
        "CXL_NATAL_OFFICER_LUCK_OUTPUT", "CXL_NATAL_OUTPUT_LUCK_OFFICER",
        "CXL_PEER_NEUTRAL_MOBILITY", "CXL_PIANYIN_LEAVE",
    ]
    env, me, peer, leave = cfg.rules
    assert env.natal_stem is TenGod.ZHENGGUAN and env.incoming is TenGod.SHANGGUAN
    assert me.natal_stem is TenGod.SHANGGUAN and me.incoming is TenGod.ZHENGGUAN
    assert env.rescue_by == {TenGod.ZHENGYIN} and env.cause == "environment" and me.cause == "self"
    # 역할 무관 겁재: 용신·기신은 기존 비겁 시드 몫 — 희신·한신·구신만, 기준점은 한 단계 낮다.
    assert peer.favorability_any == {"희신", "한신", "구신"} and peer.incoming is TenGod.JIECAI
    assert peer.base_by_inflow["stem_only"] < env.base_by_inflow["stem_only"]
    assert leave.event is EventKeyV2.CAREER_LEAVE and leave.incoming is TenGod.PIANYIN
    assert 0 < cfg.resource_rescue_ratio < 1


def test_fixture_natal_conditions() -> None:
    """픽스처의 원국 천간 조건(일간 제외)과 구응 유무를 고정한다."""
    assert TenGod.ZHENGGUAN in natal_stem_ten_gods(calculate(_ENV))
    assert TenGod.ZHENGYIN not in natal_all_ten_gods(calculate(_ENV))
    assert TenGod.ZHENGGUAN in natal_stem_ten_gods(calculate(_ENV_RESCUE))
    assert TenGod.ZHENGYIN in natal_all_ten_gods(calculate(_ENV_RESCUE))
    assert TenGod.SHANGGUAN in natal_stem_ten_gods(calculate(_SELF))


def test_flag_off_leaves_candidates_untouched() -> None:
    """기본(OFF)에서는 강의 시드 근거 코드가 어디에도 없다 — 회귀 기준선 불변."""
    probes = ((_ENV, "2026-06"), (_SELF, "2026-03"), (_SELF, "2026-07"), (_SELF, "2026-04"))
    for birth, period in probes:
        cands = _month_candidates(birth, period)
        assert not any(code.startswith("CXL_") for c in cands for code in c.reason_codes)
    # 비겁 구신 명식의 겁재 달 — 기존 용신·기신 시드는 서지 않는다(역할 무관 시드의 존재 이유).
    peer_codes = _codes(_month_candidates(_SELF, "2026-07"), "career_change")
    assert not any(code.startswith("PEER_") for code in peer_codes)


def test_environment_rule_seeds_career_change_with_cause_code() -> None:
    cands = _month_candidates(_ENV, "2026-06", enable_career_exit_seed=True)
    codes = _codes(cands, "career_change")
    assert {"CXL_NATAL_OFFICER_LUCK_OUTPUT", "CXL_CAUSE_ENVIRONMENT", "CXL_INFLOW_STEM"} <= codes
    assert not any(code.startswith("CXL_RESCUE_") for code in codes)


def test_resource_rescue_dampens_but_keeps_seed() -> None:
    cfg = load_career_exit_config(_DICTS)
    assert cfg is not None
    chart = calculate(_ENV_RESCUE)
    fav = favorability_map(chart)
    signals = [TransitSignal(TenGod.SHANGGUAN, LuckLayer.WOLWOON, "stem")]
    seeds = produce_career_exit_seeds(
        signals, LuckLayer.WOLWOON, chart, fav, "2026-02", cfg,
        rule_ids=["CXL_NATAL_OFFICER_LUCK_OUTPUT"],
    )
    assert len(seeds) == 1
    base = cfg.rules[0].base_by_inflow["stem_only"]
    assert seeds[0].score == round(base * cfg.resource_rescue_ratio)
    assert "CXL_RESCUE_ZHENGYIN" in seeds[0].reason_codes
    assert seeds[0].contributions == {"base": float(seeds[0].score)}


def test_self_rule_and_rule_ids_filter() -> None:
    on = _month_candidates(_SELF, "2026-03", enable_career_exit_seed=True)
    assert {"CXL_NATAL_OUTPUT_LUCK_OFFICER", "CXL_CAUSE_SELF"} <= _codes(on, "career_change")
    only_leave = _month_candidates(
        _SELF, "2026-03", enable_career_exit_seed=True, career_exit_rule_ids=["CXL_PIANYIN_LEAVE"],
    )
    assert not any(code.startswith("CXL_") for c in only_leave for code in c.reason_codes)


def test_peer_neutral_rule_seeds_career_change_for_non_yongsin_gisin_peer() -> None:
    on = _month_candidates(_SELF, "2026-07", enable_career_exit_seed=True)
    assert "CXL_PEER_NEUTRAL_MOBILITY" in _codes(on, "career_change")


def test_pianyin_rule_seeds_career_leave_event() -> None:
    on = _month_candidates(_SELF, "2026-04", enable_career_exit_seed=True)
    leave = [c for c in on if c.event_key is EventKeyV2.CAREER_LEAVE]
    assert leave and "CXL_PIANYIN_LEAVE" in leave[0].reason_codes
    assert EVENT_KO[EventKeyV2.CAREER_LEAVE].startswith("휴직")
    assert "휴직" in EVENT_WORDS[EventKeyV2.CAREER_LEAVE]


def test_config_none_or_wrong_layer_is_noop() -> None:
    chart = calculate(_SELF)
    sig = [TransitSignal(TenGod.PIANYIN, LuckLayer.ILWOON, "stem")]
    cfg = load_career_exit_config(_DICTS)
    assert produce_career_exit_seeds(sig, LuckLayer.ILWOON, chart, {}, "2026-04-01", cfg) == []
    assert produce_career_exit_seeds(sig, LuckLayer.WOLWOON, chart, {}, "2026-04", None) == []
    assert isinstance(cfg, CareerExitConfig)


# ── 문구층(항상 노출) ──────────────────────────────────────────────────────


def _note(birth: BirthInput, ganji: str) -> str:
    chart = calculate(birth)
    return incoming_ten_god_note(
        chart.pillars.day_master, ganji, favorability_map(chart), natal=chart,
    )


def test_text_dictionary_lint_and_ids() -> None:
    import json

    path = _DICTS / "interpretations" / "career_exit_lecture_text.json"
    raw = json.loads(path.read_text("utf-8"))
    parsed = CareerExitTextFile.model_validate(raw)
    assert _lint_career_exit_text(parsed) == []
    assert len(parsed.items) == 6


def test_note_attaches_environment_text_without_rescue() -> None:
    note = _note(_ENV, "甲午")
    assert "원인은 나보다 환경 쪽" in note
    assert "정인이 있어" not in note


def test_note_attaches_rescue_text_when_resource_present() -> None:
    note = _note(_ENV_RESCUE, "庚寅")
    assert "원인은 나보다 환경 쪽" in note and "정인이 있어" in note


def test_note_attaches_self_peer_and_leave_texts() -> None:
    assert "원인은 회사보다 나에게" in _note(_SELF, "辛卯")
    assert "경쟁자가 생길 수 있고" in _note(_SELF, "乙未")
    leave = _note(_SELF, "壬辰")
    assert "복귀를 전제로" in leave and "출산·육아" not in leave  # 남성 명식 — 여성 분기 없음
    female = _birth("1978-01-02", "female")
    assert "출산·육아" in _note(female, "壬辰")


def test_note_without_natal_keeps_natal_rules_silent() -> None:
    chart = calculate(_ENV)
    note = incoming_ten_god_note(chart.pillars.day_master, "甲午", favorability_map(chart))
    assert "원인은 나보다 환경 쪽" not in note
    # 원국 없이도 붙는 문구(편인 휴직·겁재 역할 무관)는 그대로 — 리팩터링 회귀 고정(2026-10-29).
    me = calculate(_SELF)
    fav = favorability_map(me)
    assert "복귀를 전제로" in incoming_ten_god_note(me.pillars.day_master, "壬辰", fav)
    assert "경쟁자가 생길 수 있고" in incoming_ten_god_note(me.pillars.day_master, "乙未", fav)


# ── career_field 연·월 천간 겁재 성향(P1-3) ──────────────────────────────────


def test_career_field_peer_stem_lines_branch_on_officer() -> None:
    without = build_career_field_facts(
        calculate(_birth("1976-01-03", "female")), dictionaries_dir=_DICTS,
    )
    assert without.peer_lines and "겁재 천간(년간 乙)" in without.peer_lines[0]
    assert "붙드는 규범이 약하다" in without.peer_lines[1]
    with_officer = build_career_field_facts(
        calculate(_birth("1977-01-13", "female")), dictionaries_dir=_DICTS,
    )
    assert with_officer.peer_lines and "규범·조직이 그 결을 붙들어" in with_officer.peer_lines[1]
    rendered = "\n".join(render_career_field_lines(with_officer))
    assert "비겁 천간(이동·겸업 성향)" in rendered
    none = build_career_field_facts(calculate(_ENV), dictionaries_dir=_DICTS)
    assert none.peer_lines == [] or all("겁재 천간" in x for x in none.peer_lines)


def test_lecture_block_emits_once_per_ganji_for_career_questions() -> None:
    """직업 질문 블록 — 같은 간지의 후보가 여럿이어도 1줄, 조건 없는 간지는 생략, 없으면 빈 목록."""
    chart = calculate(_ENV)
    block = career_exit_lecture_block(
        chart, [("2026-06", "甲午"), ("2026-06", "甲午"), ("2026-05", "癸巳")],
    )
    assert block and block[0].startswith("[직장 운 결 — 강의 번역층")
    body = [x for x in block[1:] if x.startswith("- ")]
    assert len(body) == 1 and body[0].startswith("- 2026-06 甲午: ") and "환경 쪽" in body[0]
    assert career_exit_lecture_block(chart, [("2026-05", "癸巳")]) == []


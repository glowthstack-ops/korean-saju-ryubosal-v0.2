"""역할별 사건 전환 시드(2026-10-16 데굴님 확정 6규칙) 회귀 고정.

사흉신(상관·편관·편인)이 용신인 명식의 그 십성 운, 사길신(정관·정인·식신)이 기신인 명식의 그 운 —
브랜처 기본 가지(충돌·이탈 / 압박 / 보류 · 취업 / 문서 / 성과)는 불변이고 역할별 사건 후보를 시드로
더해 순위로 전환한다. 점수층은 플래그 OFF 기본(85사례 적중률로 ON), 문구층은 항상 노출.

픽스처(2026-10 戊戌월 = 土 간여지동, 2026-10-16 탐색): 일간별로 土 가 해당 십성이고 그 오행이
용신/기신인 명식.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import period_v2_config
from saju_engines.chart_interpretation import incoming_ten_god_note
from saju_engines.dictionaries import RoleEventTextFile, _lint_role_event_text
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.event_scoring import favorability_map
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.role_event_seed import (
    incoming_element,
    load_role_event_seed_config,
    merge_role_event_seeds,
    produce_role_event_seeds,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import TenGod
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth(d: str, t: str = "10:00:00", g: str = "male") -> BirthInput:
    return BirthInput(
        birth_date=date.fromisoformat(d), birth_time=t, birth_place_name="서울", gender=g,
    )


# (규칙 id, 명식, 일간, 2026-10 戊戌 의 십성, 역할, 시드 사건 순서)
_FIXTURES = [
    ("ROLE_SEED_SHANGGUAN_YONG", _birth("1978-09-02"), "丁", "상관", "용신",
     ("creative_output", "public_exposure")),
    ("ROLE_SEED_QISHA_YONG", _birth("1978-10-27"), "壬", "편관", "용신",
     ("job_gain", "promotion")),
    ("ROLE_SEED_PIANYIN_YONG", _birth("1978-06-17"), "庚", "편인", "용신",
     ("education_admission", "creative_output")),
    ("ROLE_SEED_ZHENGGUAN_GI", _birth("1979-02-25"), "癸", "정관", "기신",
     ("career_change",)),
    ("ROLE_SEED_ZHENGYIN_GI", _birth("1978-10-16"), "辛", "정인", "기신",
     ("preparation_delay",)),
    ("ROLE_SEED_SHISHEN_GI", _birth("1978-01-14", "14:30:00", "female"), "丙", "식신", "기신",
     ("health_attention", "wealth_change")),
]


def _month_candidates(birth: BirthInput, year: int, **overrides):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    return build_event_engine_v2(_DICTS, **overrides).score(c2, levels={GanjiLevel.MONTH})


def _october(birth: BirthInput, **overrides):
    return [c for c in _month_candidates(birth, 2026, **overrides) if c.period == "2026-10"]


# ── 사전 ────────────────────────────────────────────────────────────────────


def test_config_loads_six_rules_with_peer_seed_base_points():
    cfg = load_role_event_seed_config(_DICTS)
    assert cfg is not None
    assert [r.rule_id for r in cfg.rules] == [f[0] for f in _FIXTURES]
    assert all(r.enabled for r in cfg.rules)
    b = cfg.base_by_inflow
    assert b["same_god"] > b["same_group"] > b["stem_only"] > b["branch_only"]
    assert b["same_god"] >= cfg.event_candidate_threshold
    assert 0 < cfg.secondary_ratio < 1
    yong = [r for r in cfg.rules if "용신" in r.favorability_any]
    gi = [r for r in cfg.rules if "기신" in r.favorability_any]
    assert {r.incoming for r in yong} == {TenGod.SHANGGUAN, TenGod.QISHA, TenGod.PIANYIN}
    assert {r.incoming for r in gi} == {TenGod.ZHENGGUAN, TenGod.ZHENGYIN, TenGod.SHISHEN}


def test_text_dictionary_valid_and_linted():
    data = json.loads(
        (_DICTS / "interpretations" / "transit_role_event_text.json").read_text("utf-8")
    )
    parsed = RoleEventTextFile.model_validate(data)
    assert _lint_role_event_text(parsed) == []
    assert {(it.ten_god, it.role) for it in parsed.items} == {
        ("상관", "용신"), ("편관", "용신"), ("편인", "용신"),
        ("정관", "기신"), ("정인", "기신"), ("식신", "기신"),
    }


def test_incoming_element_follows_day_master():
    assert incoming_element(Stem("丁"), TenGod.SHANGGUAN) == "土"  # 丁 → 식상 土
    assert incoming_element(Stem("壬"), TenGod.QISHA) == "土"      # 壬 → 관성 土
    assert incoming_element(Stem("庚"), TenGod.PIANYIN) == "土"    # 庚 → 인성 土
    assert incoming_element(Stem("甲"), TenGod.ZHENGCAI) == "土"   # 甲 → 재성 土


# ── 시드 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("rule_id", "birth", "dm", "tg", "role", "events"), _FIXTURES)
def test_fixture_chart_matches_rule_condition(rule_id, birth, dm, tg, role, events):
    chart = calculate(birth)
    assert chart.pillars.day.stem == dm
    assert favorability_map(chart).get("土") == role
    oct_ = [m for m in luck_months(birth, 2026) if m.ganji == "戊戌"]
    assert oct_ and oct_[0].stem_ten_god == tg and oct_[0].branch_ten_god == tg


@pytest.mark.parametrize(("rule_id", "birth", "dm", "tg", "role", "events"), _FIXTURES)
def test_seed_added_with_same_god_inflow_and_role_quality(rule_id, birth, dm, tg, role, events):
    cands = _october(birth, enable_role_event_seed=True)
    seeded = {
        c.event_key.value: c for c in cands if rule_id in c.reason_codes
    }
    assert set(seeded) == set(events), sorted(seeded)  # 후보 순서는 브랜처 자리라 집합 비교
    for c in seeded.values():
        assert "ROLE_INFLOW_SAME_GOD" in c.reason_codes
        assert c.score >= 55  # 6계층 보정 뒤에도 event_candidate 문턱
        assert c.quality is not None
        if role == "기신":
            assert c.quality.value in ("pressure", "loss", "conflict", "mixed")
        else:
            assert c.quality.value not in ("pressure", "loss", "conflict")
    # 다른 규칙 코드는 붙지 않는다.
    assert not any(
        r.startswith("ROLE_SEED_") and r != rule_id for c in cands for r in c.reason_codes
    )


def test_secondary_event_scores_below_primary_in_raw_seed():
    cfg = load_role_event_seed_config(_DICTS)
    assert cfg is not None
    from saju_engines.ten_god_brancher import TransitSignal
    from saju_shared_types.event_engine import LuckLayer

    chart = calculate(_FIXTURES[0][1])  # 丁 일간, 土=용신
    w = LuckLayer.WOLWOON
    signals = [
        TransitSignal(TenGod.SHANGGUAN, w, "stem", same_group=True, same_god=True),
        TransitSignal(TenGod.SHANGGUAN, w, "branch_main", same_group=True, same_god=True),
    ]
    seeds = produce_role_event_seeds(
        signals, w, chart, favorability_map(chart), "2026-10", cfg,
    )
    assert [s.event_key.value for s in seeds] == ["creative_output", "public_exposure"]
    assert seeds[0].score == cfg.base_by_inflow["same_god"]
    assert seeds[1].score == round(cfg.base_by_inflow["same_god"] * cfg.secondary_ratio)
    assert seeds[0].contributions == {"base": float(seeds[0].score)}


def test_weak_inflow_gets_lower_tier_and_branch_code():
    """丁 일간 2026-04 壬辰 — 천간 정관·지지 辰(戊) 상관: 지지만 유입(약한 유입)."""
    cands = [
        c for c in _month_candidates(_FIXTURES[0][1], 2026, enable_role_event_seed=True)
        if c.period == "2026-04"
    ]
    seeded = [c for c in cands if "ROLE_SEED_SHANGGUAN_YONG" in c.reason_codes]
    assert seeded and all("ROLE_INFLOW_BRANCH" in c.reason_codes for c in seeded)
    assert not any("ROLE_INFLOW_SAME_GOD" in c.reason_codes for c in seeded)


def test_no_seed_when_role_does_not_match():
    """1980-11-22 남(己 일간, 土=용신=비겁) — 2026-10 戊戌 은 겁재라 역할 규칙 대상이 아니다."""
    cands = _october(_birth("1980-11-22", "09:40:00"), enable_role_event_seed=True)
    assert not any(r.startswith("ROLE_SEED_") for c in cands for r in c.reason_codes)
    # 비겁 시드는 그대로 산다.
    assert any("PEER_YONGSIN_MOBILITY" in c.reason_codes for c in cands)


def test_flag_off_is_byte_identical_default():
    assert period_v2_config.ROLE_EVENT_SEED_ENABLED is False
    birth = _FIXTURES[4][1]
    off = _october(birth)
    explicit_off = _october(birth, enable_role_event_seed=False)
    assert [c.model_dump() for c in off] == [c.model_dump() for c in explicit_off]
    assert not any(r.startswith("ROLE_") for c in off for r in c.reason_codes)
    on = _october(birth, enable_role_event_seed=True)
    assert any("ROLE_SEED_ZHENGYIN_GI" in c.reason_codes for c in on)


def test_config_flag_feeds_engine(monkeypatch):
    monkeypatch.setattr(period_v2_config, "ROLE_EVENT_SEED_ENABLED", True)
    on = _october(_FIXTURES[3][1])
    assert any("ROLE_SEED_ZHENGGUAN_GI" in c.reason_codes for c in on)
    assert period_v2_config.active_versions()["role_event_seed_enabled"] is True


def test_rule_ids_filter_isolates_one_rule():
    birth = _FIXTURES[5][1]  # 丙 일간, 土=기신 — 식신 규칙 대상
    only_other = _october(
        birth, enable_role_event_seed=True, role_event_seed_rule_ids=["ROLE_SEED_ZHENGYIN_GI"],
    )
    assert not any(r.startswith("ROLE_SEED_") for c in only_other for r in c.reason_codes)
    only_self = _october(
        birth, enable_role_event_seed=True, role_event_seed_rule_ids=["ROLE_SEED_SHISHEN_GI"],
    )
    assert any("ROLE_SEED_SHISHEN_GI" in c.reason_codes for c in only_self)


def test_merge_keeps_existing_candidate_and_records_delta():
    from saju_shared_types.event_engine import (
        ConfidenceLevel,
        EventCandidateV2,
        EventKeyV2,
        LuckLayer,
        PolarityRole,
    )

    def cand(key: str, score: int, **kw) -> EventCandidateV2:
        return EventCandidateV2(
            event_key=EventKeyV2(key), period="2026-10", score=score,
            confidence_level=ConfidenceLevel.THEME_ONLY, polarity_role=PolarityRole.NEUTRAL,
            source_layers=[LuckLayer.WOLWOON], reason_codes=kw.get("reasons", ["SINGLE_X"]),
            contributions={"base": float(score)},
        )

    existing = cand("career_change", 41)
    existing.contributions["peer_mobility_seed"] = 5.0
    seed = cand("career_change", 68, reasons=["ROLE_SEED_ZHENGGUAN_GI", "ROLE_INFLOW_SAME_GOD"])
    seed.confidence_level = ConfidenceLevel.EVENT_CANDIDATE
    out = merge_role_event_seeds([existing], [seed])
    assert len(out) == 1 and out[0] is existing
    assert existing.score == 68 and existing.contributions["role_event_seed"] == 27.0
    assert existing.contributions["peer_mobility_seed"] == 5.0  # 비겁 시드 기여 보존
    assert existing.confidence_level is ConfidenceLevel.EVENT_CANDIDATE
    assert "ROLE_SEED_ZHENGGUAN_GI" in existing.reason_codes
    # 낮은 시드는 점수를 올리지 않는다(근거만 합집합).
    low = cand("career_change", 30, reasons=["ROLE_SEED_ZHENGGUAN_GI"])
    merge_role_event_seeds([existing], [low])
    assert existing.score == 68 and existing.contributions["role_event_seed"] == 27.0


# ── 문구층(항상 노출)·라벨 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("dm", "fav", "needle"),
    [
        ("丁", "용신", "재능 발휘·표현·발표"),   # 상관 용신
        ("壬", "용신", "책임 있는 역할·직책"),   # 편관 용신
        ("庚", "용신", "전문 연구"),             # 편인 용신
        ("癸", "기신", "구속과 부담"),           # 정관 기신
        ("辛", "기신", "정체·결정 지연"),        # 정인 기신
        ("丙", "기신", "소모·과로·지출"),        # 식신 기신
    ],
)
def test_incoming_note_attaches_role_text(dm, fav, needle):
    note = incoming_ten_god_note(dm, "戊戌", {"土": fav})
    assert needle in note
    assert note.count(needle) == 1  # 간여지동이라도 1회


@pytest.mark.parametrize("fav", ["한신", "희신", "구신"])
def test_incoming_note_silent_for_other_roles(fav):
    note = incoming_ten_god_note("丁", "戊戌", {"土": fav})
    assert "재능 발휘·표현·발표" not in note


def test_incoming_note_silent_for_gilsin_yongsin_and_hyungsin_gisin():
    """사길신 용신(정관 용신)·사흉신 기신(상관 기신)은 전환 대상이 아니다 — 기본 가지가 맞다."""
    assert "구속과 부담" not in incoming_ten_god_note("癸", "戊戌", {"土": "용신"})
    assert "재능 발휘·표현·발표" not in incoming_ten_god_note("丁", "戊戌", {"土": "기신"})


def test_reason_codes_have_korean_labels():
    ko = reason_codes_ko([
        "ROLE_SEED_SHISHEN_GI", "ROLE_INFLOW_SAME_GOD", "ROLE_UPPER_SUPPORT_daewoon",
    ])
    assert any("식신 기신 운" in x for x in ko)
    assert any("간여지동" in x for x in ko)
    assert any("상위 운" in x for x in ko)

"""충 강의 대조 층(2026-11-07, 데굴님 "바로 진행하자") — 사전 보강·완화 글자·강충 방향 측정 규칙.

doc/v2_2/EXTERNAL_TEXT_GAP_CLASH_LECTURE.md. 서술층은 기본 ON(실답 감수), 점수 규칙(강충 방향)은
shadow 기본·apply 는 85사례 측정 후 데굴님 결정.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.clash_relief import (
    PAIR_NAME_KO,
    RELIEF_BLOCK_HEADER,
    load_clash_relief_text,
    luck_clash_relief_block,
    natal_clash_relief_by_name,
    next_year_with_branch,
)
from saju_engines.dictionaries import (
    ClashReliefTextFile,
    _lint_clash_relief_text,
    lint_dictionaries,
)
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput

_DICT = Path(__file__).resolve().parents[2] / "dictionaries"
# 庚申·丁亥·己亥·己巳 — 월지·일지 亥(구신 水) × 시지 巳(희신 火) 사해충.
_CASE_SAHAE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
# 己巳·丁丑·庚辰·癸未 — 월지 丑 × 시지 未 축미충(둘 다 土 기신 → 완화 서술 없음), 연지 巳 용신 火.
_CASE_CHUKMI = BirthInput(
    birth_date=date(1990, 1, 15), birth_time="14:00:00", birth_place_name="서울", gender="male",
)


# ── 사전 ─────────────────────────────────────────────────────────────────────

def test_relations_text_all_six_clashes_have_natal_trait() -> None:
    """丑未·辰戌에도 성향 문장이 있다(강의 대조로 빈칸 보강)."""
    d = json.loads((_DICT / "interpretations/relations_text.json").read_text("utf-8"))
    by_id = {it["id"]: it for it in d["items"]}
    for pair in ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"):
        it = by_id[f"rel_{pair}沖"]
        assert it.get("natalTrait"), pair
        # 쌍 결(水火/木金/土)이 첫 문장에 들어간다 — 운 줄은 첫 문장만 렌더되기 때문.
        first = it["fromLuck"].split("다.")[0]
        assert any(k in first for k in ("水火충", "木金충", "土충")), (pair, first)


def test_clash_relief_dictionary_lint_clean() -> None:
    assert not [e for e in lint_dictionaries(_DICT) if "clash_relief" in e]


def test_clash_relief_lint_rejects_wrong_mechanism_and_assertive_text() -> None:
    raw = load_clash_relief_text()
    bad = json.loads(json.dumps(raw))
    bad["items"][0]["glyph"] = "寅"  # 子寅 은 육합이 아니다
    bad["items"][1]["text"] = "午를 未가 묶어 충이 반드시 해소된다"
    errors = _lint_clash_relief_text(ClashReliefTextFile.model_validate(bad))
    assert any("육합이 아님" in e for e in errors)
    assert any("단정 어휘" in e for e in errors)


def test_clash_relief_covers_twelve_branches_once() -> None:
    items = load_clash_relief_text()["items"]
    assert sorted(it["target"] for it in items) == sorted("子丑寅卯辰巳午未申酉戌亥")
    assert {it["pair"] for it in items} == {"子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"}
    # 합이 아닌 상생 논리(巳←寅·亥←申)와 방합 짝이면서 해인 글자는 병기 메모가 있다.
    co = {(it["target"], it["glyph"]): it.get("coRelation", "") for it in items}
    assert "형" in co[("巳", "寅")] and "해" in co[("亥", "申")]
    assert "해" in co[("卯", "辰")] and "해" in co[("酉", "戌")]
    assert co[("子", "丑")] == "" and co[("寅", "辰")] == ""


# ── 원국 완화 글자 ────────────────────────────────────────────────────────────

def test_natal_relief_only_for_useful_glyph_and_pairs_co_relation() -> None:
    result = calculate(_CASE_SAHAE)
    fav = favorability_map(result)
    assert fav["火"] == "희신" and fav["水"] == "구신"
    relief = natal_clash_relief_by_name(result, 2026)
    assert set(relief) == {"사해충"}
    text = relief["사해충"]
    assert text.startswith("완화 글자: 巳(희신 火)를 살리는 寅(상생)")
    assert "亥(" not in text  # 구신 글자는 완화를 찾지 않는다
    assert "원국에 없음" in text and "寅 세운 2034년" in text and "寅월" in text
    assert "寅巳 형(刑)·해(害)도 함께 서므로 완화와 자극을 병기" in text


def test_natal_relief_absent_when_both_glyphs_adverse() -> None:
    result = calculate(_CASE_CHUKMI)
    assert favorability_map(result)["土"] == "기신"
    assert natal_clash_relief_by_name(result, 2026) == {}


def test_relation_excerpt_carries_relief_sentence() -> None:
    """원국 관계 발췌(고정 prefix)의 충 항목 끝에 '완화 글자:' 가 붙는다."""
    ci = build_chart_interpretation(calculate(_CASE_SAHAE))
    assert ci is not None
    ex = [e for e in ci.excerpts if e.kind == "relation" and e.key == "사해충"]
    assert len(ex) == 1 and "완화 글자: 巳(희신 火)를 살리는 寅(상생)" in ex[0].text
    assert "성향:" in ex[0].text  # 기존 성향 문장 보존


def test_next_year_with_branch() -> None:
    assert next_year_with_branch("寅", 2026) == 2034
    assert next_year_with_branch("午", 2026) == 2026
    assert next_year_with_branch("子", 2026) == 2032


# ── 운 완화 글자 블록 ─────────────────────────────────────────────────────────

def test_luck_relief_block_lists_struck_useful_glyph_once() -> None:
    result = calculate(_CASE_CHUKMI)  # 연지 巳(용신 火)
    periods = [("2031", "辛亥"), ("2031-05", "癸巳"), ("2031-11", "己亥"), ("2033", "癸丑")]
    block = luck_clash_relief_block(result, periods, 2026)
    assert block and block[0] == RELIEF_BLOCK_HEADER
    body = block[1:]
    # 亥 운이 巳를 치는 줄은 같은 운 지지에 대해 한 번만(2031·2031-11 중복 아님).
    assert len(body) == 1
    assert body[0].startswith(
        "- 2031 辛亥 사해충(운 亥 → 원국 연지 巳): 巳(용신 火)를 살리는 寅(상생)"
    )
    assert "완화와 자극을 병기" in body[0]
    # 丑 운 × 未(기신 土) 는 완화 대상이 아니다.
    assert not any("축미충" in ln for ln in body)


def test_luck_relief_block_adds_year_pillar_for_monthly_candidates() -> None:
    """연 단위 질문의 월 후보만 넘겨도 그 연도 세운(2031 辛亥)의 충을 잡는다(dry-run 실측 공백)."""
    result = calculate(_CASE_CHUKMI)
    block = luck_clash_relief_block(result, [("2031-03", "辛卯"), ("2031-08", "丙申")], 2026)
    assert len(block) == 2 and block[1].startswith("- 2031 辛亥 사해충(운 亥 → 원국 연지 巳)")


def test_luck_relief_block_empty_without_clash_or_without_fav() -> None:
    result = calculate(_CASE_CHUKMI)
    assert luck_clash_relief_block(result, [("2027", "丁未"), ("2028", "戊申")], 2026) == []
    assert luck_clash_relief_block(result, [], 2026) == []
    assert PAIR_NAME_KO[frozenset("子午")] == "자오충"


# ── 강충 방향 점수 규칙(측정용) ───────────────────────────────────────────────

# 癸亥·丙辰·辛卯·癸巳 — 일지 卯가 원국 유일한 木(고립). 2029 己酉 세운이 卯를 극충(金→木).
_CASE_ISOLATED_MYO = BirthInput(
    birth_date=date(1983, 5, 3), birth_time="10:00:00", birth_place_name="서울", gender="female",
)


@pytest.fixture(scope="module")
def engine_pair():
    from saju_api.services.chat_service import _DICTS
    from saju_engines.event_engine_v2 import EventEngineV2

    return (
        EventEngineV2(_DICTS, risk_mode="off", clash_direction_mode="shadow"),
        EventEngineV2(_DICTS, risk_mode="off", clash_direction_mode="apply"),
    )


def test_clash_direction_shadow_records_and_apply_scales_only_target_events(engine_pair) -> None:
    """shadow 는 기록만(점수 불변), apply 는 강의 사건 계열만 ×1.15 — 판정은 두 모드가 공유."""
    shadow, apply = engine_pair
    result = calculate(_CASE_ISOLATED_MYO)
    base = shadow.score_years(result, [2029])
    rec = shadow.take_clash_direction_shadow()
    assert rec and rec[0]["luck_branch"] == "酉" and rec[0]["struck"] == ["day:卯"]
    assert all(e in {"health_attention", "relationship_change", "career_change"}
               for r in rec for e in r["events"])
    assert not any("clash_direction" in c.contributions for c in base)
    applied = apply.score_years(result, [2029])
    rec_apply = apply.take_clash_direction_shadow()
    assert [(r["period"], r["struck"]) for r in rec] == [
        (r["period"], r["struck"]) for r in rec_apply
    ]
    by_key = {(c.period, str(c.event_key)): c for c in base}
    scaled = 0
    for c in applied:
        b = by_key[(c.period, str(c.event_key))]
        if any(code.startswith("沖_강충_酉→卯") for code in c.reason_codes):
            scaled += 1
            assert c.contributions.get("clash_direction") == 0.15
            assert c.score == round(b.score * 1.15)
        else:
            assert c.score == b.score and "clash_direction" not in c.contributions
    assert scaled >= 1


def test_clash_direction_not_isolated_or_wrong_direction_records_nothing(engine_pair) -> None:
    """월간 丁이 있어 巳(火)가 고립이 아니면 亥 운이 와도 기록 없음(1980 명식 2031 辛亥)."""
    shadow, _ = engine_pair
    shadow.score_years(calculate(_CASE_SAHAE), [2031])
    assert shadow.take_clash_direction_shadow() == []


def test_clash_direction_off_mode_records_nothing() -> None:
    from saju_api.services.chat_service import _DICTS
    from saju_engines.event_engine_v2 import EventEngineV2

    off = EventEngineV2(_DICTS, risk_mode="off", clash_direction_mode="off")
    off.score_years(calculate(_CASE_ISOLATED_MYO), [2029])
    assert off.take_clash_direction_shadow() == []
    with pytest.raises(ValueError):
        EventEngineV2(_DICTS, risk_mode="off", clash_direction_mode="loud")

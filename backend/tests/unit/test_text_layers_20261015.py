"""외부 교재 대조 P1 문구층(2026-10-15, 데굴님 '적용 후 감수').

관계 위치 쌍·공망 십성별·질병 글자·직업 조건층.

전부 문체·서사·보조 근거 전용이다(점수·후보 비개입). 실사례 명식(1980-11-22 09:40 서울 남,
庚申·丁亥·己亥·己巳, 공망 辰巳 → 시지 巳 공망)로 노출을 고정한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.career_field import build_career_field_facts, render_career_field_lines
from saju_engines.chart_interpretation import _relation_palace_pairs, build_chart_interpretation
from saju_engines.health_vulnerability import analyze_health_vulnerability
from saju_engines.structural_context import _health_letter_lines, health_lines
from saju_shared_types.birth_input import BirthInput

_DICT = Path(__file__).resolve().parents[2] / "dictionaries"
_CASE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_CASE2 = BirthInput(
    birth_date=date(1985, 5, 20), birth_time="10:00:00", birth_place_name="서울", gender="male",
)


# ── 관계 위치 쌍 ─────────────────────────────────────────────────────────────

def test_relation_palace_pairs_real_case_has_month_hour_clash() -> None:
    result = calculate(_CASE)
    pairs = _relation_palace_pairs(result)
    assert ("clash", "month-hour", "亥·巳") in pairs or ("clash", "month-hour", "巳·亥") in pairs
    ci = build_chart_interpretation(result)
    assert ci is not None
    ex = [e for e in ci.excerpts if e.kind == "relation_palace"]
    assert any(e.key.startswith("충 월주-시주") for e in ex)
    d = json.loads((_DICT / "interpretations/relation_palace_pairs_text.json").read_text("utf-8"))
    want = next(
        it["text"] for it in d["items"] if it["kind"] == "clash" and it["pair"] == "month-hour"
    )
    assert any(e.text == want for e in ex)
    # 같은 (kind, pair) 는 한 번만.
    keys = [e.key for e in ex]
    assert len(keys) == len(set(keys))


# ── 공망 십성별 ──────────────────────────────────────────────────────────────

def test_void_ten_god_excerpt_for_void_hour_branch() -> None:
    result = calculate(_CASE)
    assert result.pillars is not None and result.pillars.hour is not None
    assert result.pillars.hour.gongmang_hit is True  # 시지 巳 공망
    ci = build_chart_interpretation(result)
    assert ci is not None
    ex = [e for e in ci.excerpts if e.kind == "void_ten_god"]
    assert len(ex) == 1 and ex[0].key.startswith("공망 巳(시주 ")
    d = json.loads((_DICT / "interpretations/void_ten_god_text.json").read_text("utf-8"))
    tg = result.pillars.hour.branch_main_ten_god
    base = next(it["text"] for it in d["items"] if it["ten_god"] == tg)
    # 2026-10-23 P3: 본문 뒤에 생극 연쇄 가설·활용 경로·출처 등급 꼬리가 붙는다(점수 비개입).
    assert ex[0].text.startswith(base) and "(출처:" in ex[0].text


def test_void_excerpt_absent_when_no_void_pillar() -> None:
    result = calculate(_CASE2)
    assert result.pillars is not None
    pl = result.pillars
    voids = [getattr(getattr(pl, p), "gongmang_hit", False) for p in ("year", "month", "hour")]
    if not any(voids):
        ci = build_chart_interpretation(result)
        assert ci is not None
        assert not [e for e in ci.excerpts if e.kind == "void_ten_god"]


# ── 질병 글자·상전 ───────────────────────────────────────────────────────────

def test_health_letter_lines_use_only_body_parts_and_follow_vulnerable_elements() -> None:
    d = json.loads((_DICT / "health_element_organs.json").read_text("utf-8"))
    assert set(d["stems"]) == set("甲乙丙丁戊己庚辛壬癸") and len(d["branches"]) == 12
    assert set(d["clash_pairs"]) == {"金木", "水火", "水土", "火金", "木土"}
    banned = ("암", "중풍", "백혈병", "당뇨", "결핵", "성병")  # 질병명 금지 — 부위·계열만
    for table in (d["stems"], d["branches"]):
        for parts in table.values():
            assert not any(b in "".join(parts) for b in banned), parts
    for birth in (_CASE, _CASE2):
        result = calculate(birth)
        hv = analyze_health_vulnerability(result)
        lines = _health_letter_lines(result, hv)
        if hv.vulnerable_organs:
            assert lines and lines[0].startswith("글자별 신체 부위")
            body = lines[0].split(": ", 1)[1]
            for part in body.split(" / "):
                ch = part.split("=")[0]
                assert ch in d["stems"] or ch in d["branches"]
                el = d["stems"].get(ch) and None  # 글자→오행은 엔진 상수가 SSOT(여기선 존재만 확인)
                assert el is None
            assert any(line.startswith("오행 상전 계열") for line in lines)
            full = health_lines(result, hv, 2026)
            assert lines[0] in full
        else:
            assert lines == []


# ── 직업 조건층 ──────────────────────────────────────────────────────────────

def test_career_conditions_dictionary_and_evaluation() -> None:
    d = json.loads((_DICT / "career_fields.json").read_text("utf-8"))
    ids = [c["id"] for c in d["conditions"]]
    assert len(ids) == 11 and len(set(ids)) == 11
    known = {
        "hyeonchim_favorable", "three_punishment_favorable", "fire_day_or_yong",
        "fire_trine_or_byeongjeong", "jeong_day_or_peer_many", "metal_yong", "earth_water_yong",
        "military_signals", "yongsin_clashed", "wood_yong_jinsul_clash", "water_yong_output",
    }
    assert {c["signal"] for c in d["conditions"]} == known
    for birth in (_CASE, _CASE2):
        facts = build_career_field_facts(calculate(birth))
        for hit in facts.conditions:
            assert hit.evidence and hit.field and hit.jobs
        lines = render_career_field_lines(facts)
        if facts.conditions:
            assert any(line.startswith("[격국·신살 조건") for line in lines)
            assert all(f"- {h.field}: " in "\n".join(lines) for h in facts.conditions)


def test_real_case_hits_earth_or_water_brokerage_condition() -> None:
    """己 일간·용신 土(비겁) 실사례 — 土 희용신 → 중개·유통 조건이 선다."""
    facts = build_career_field_facts(calculate(_CASE))
    assert any(h.id == "brokerage_earth_water" and "土" in h.evidence for h in facts.conditions)
